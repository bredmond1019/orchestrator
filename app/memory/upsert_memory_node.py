"""UpsertMemoryNode — write extracted facts into ``SemanticMemory``, with
never-overwrite contradiction handling.

Reusable across both memory workflows (block OR.S design decision 1: a
standalone module, no coupling to any one workflow): ``MemoryIngestWorkflow``
attaches it after fast, per-interaction extraction; ``MemoryConsolidationWorkflow``
attaches it after the deep, dream-time consolidation pass.

Contradiction rule (never overwrite): when an incoming fact contradicts an
existing ``SemanticMemory`` row (identified by ``contradicts_fact_id``), the
existing row's *stored* ``confidence`` is lowered — after first applying decay
so the comparison is against its true current confidence, not its stale
written value — and a **new** row is inserted for the incoming fact. The old
row is never mutated in any other way and never deleted, so the full
evidentiary history survives.

Persistence goes only through the shared ``db_session`` factory (CLAUDE.md
standing rule 7). ``_session_scope`` and ``_embed`` are mockable seams,
following the same pattern as ``EpisodeWriteService``.
"""

from contextlib import contextmanager
from datetime import datetime

from core.nodes.base import Node
from core.task import TaskContext
from database.semantic_memory import DEFAULT_DECAY_FACTOR, SemanticMemory
from database.session import db_session
from services.embedding_service import EmbeddingService

from memory.decay import effective_confidence, weeks_between

# How much a contradicted fact's (decayed) confidence is multiplied by when a
# new, contradicting fact is written. A row is never overwritten or deleted —
# only its confidence is lowered — so the full evidentiary history survives.
CONTRADICTION_PENALTY = 0.5

# Default confidence assigned to an incoming fact that doesn't specify one.
DEFAULT_FACT_CONFIDENCE = 0.9


class UpsertMemoryNode(Node):
    """Upsert extracted facts into ``SemanticMemory``, applying decay + the
    never-overwrite contradiction rule."""

    def __init__(self, source_node_name: str = "IngestTimeExtractionNode"):
        """``source_node_name`` is the upstream node whose ``result`` carries
        ``{"workspace_id", "peer_id", "facts": [...], "evidence_episode_ids": [...]}``
        when this node runs inside a workflow's ``process()`` chain. Both
        memory workflows (ingest and consolidation) point this at their own
        extraction/consolidation node — the node itself stays agnostic of
        which one produced its input."""
        self.source_node_name = source_node_name

    # ------------------------------------------------------------------
    # Seams — patched in tests
    # ------------------------------------------------------------------

    def _session_scope(self):
        """Return a context manager yielding a SQLAlchemy session.

        Isolated so tests can monkeypatch it to yield a real (e.g. in-memory
        SQLite) session without touching the deployment database.
        """
        return contextmanager(db_session)()

    def _embed(self, text: str) -> list[float]:
        """Embed ``text`` via the configured ``EmbeddingService``.

        Isolated so tests can monkeypatch it and avoid a live embedding
        provider call.
        """
        return EmbeddingService().embed_text(text)

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def upsert_facts(
        self,
        *,
        peer_id: str,
        facts: list[dict],
        evidence_episode_ids: list[str] | None = None,
    ) -> list[SemanticMemory]:
        """Upsert each fact dict in ``facts`` for ``peer_id``.

        Each fact dict may carry:
          - ``fact`` (required): the fact text.
          - ``confidence``: starting confidence (default
            ``DEFAULT_FACT_CONFIDENCE``).
          - ``decay_factor``: per-week decay multiplier (default
            ``DEFAULT_DECAY_FACTOR``, 0.95).
          - ``evidence_episode_ids``: overrides the top-level
            ``evidence_episode_ids`` default for this fact.
          - ``source_peer_id``: set when this fact about ``peer_id`` was
            derived from another peer's evidence.
          - ``contradicts_fact_id``: the id of an existing ``SemanticMemory``
            row this fact contradicts. When set, that row's confidence is
            lowered (decay applied first) and a new row is always inserted —
            the old row is never overwritten or deleted.

        Returns the list of newly inserted ``SemanticMemory`` rows (refreshed,
        with generated ids and embeddings populated).
        """
        default_evidence = list(evidence_episode_ids or [])
        created: list[SemanticMemory] = []
        with self._session_scope() as session:
            for fact_input in facts:
                created.append(
                    self._upsert_one_fact(session, peer_id, fact_input, default_evidence)
                )
            session.commit()
            for row in created:
                session.refresh(row)
        return created

    def _upsert_one_fact(
        self,
        session,
        peer_id: str,
        fact_input: dict,
        default_evidence_episode_ids: list[str],
    ) -> SemanticMemory:
        """Apply the contradiction rule (if any) and insert the new fact row."""
        contradicts_id = fact_input.get("contradicts_fact_id")
        if contradicts_id:
            self._lower_contradicted_confidence(session, contradicts_id)

        embedding = self._embed(fact_input["fact"])
        new_row = SemanticMemory(
            peer_id=peer_id,
            fact=fact_input["fact"],
            confidence=fact_input.get("confidence", DEFAULT_FACT_CONFIDENCE),
            evidence_episode_ids=list(
                fact_input.get("evidence_episode_ids") or default_evidence_episode_ids
            ),
            decay_factor=fact_input.get("decay_factor", DEFAULT_DECAY_FACTOR),
            source_peer_id=fact_input.get("source_peer_id"),
            embedding=embedding,
        )
        session.add(new_row)
        session.flush()
        return new_row

    @staticmethod
    def _lower_contradicted_confidence(session, contradicts_id) -> None:
        """Decay, then lower, the confidence of the row ``contradicts_id`` refers to.

        No-op (silently skipped) when the referenced row doesn't exist —
        a dangling contradiction hint must never raise and abort the whole
        upsert batch.
        """
        contradicted = (
            session.query(SemanticMemory).filter_by(id=contradicts_id).first()
        )
        if contradicted is None:
            return
        now = datetime.now()
        reference_time = contradicted.updated_at or contradicted.created_at or now
        weeks_elapsed = weeks_between(reference_time, now)
        decayed = effective_confidence(
            contradicted.confidence, contradicted.decay_factor, weeks_elapsed
        )
        contradicted.confidence = decayed * CONTRADICTION_PENALTY
        contradicted.updated_at = now
        session.add(contradicted)

    # ------------------------------------------------------------------
    # Node interface
    # ------------------------------------------------------------------

    def process(self, task_context: TaskContext) -> TaskContext:
        """Read facts from the upstream extraction/consolidation node's
        output and upsert them.

        Reads ``task_context.get_node_output(self.source_node_name)["result"]``
        for ``{"peer_id", "facts", "evidence_episode_ids"}`` (CLAUDE.md
        standing rule 9 storage contract).

        Writes: ``{"upserted": [<fact dict>, ...]}`` — one entry per newly
        inserted ``SemanticMemory`` row.
        """
        source = task_context.get_node_output(self.source_node_name)["result"]
        peer_id = source["peer_id"]
        facts = source.get("facts", [])
        evidence_episode_ids = source.get("evidence_episode_ids", [])

        upserted = self.upsert_facts(
            peer_id=peer_id,
            facts=facts,
            evidence_episode_ids=evidence_episode_ids,
        )

        task_context.update_node(
            node_name=self.node_name,
            result={
                "upserted": [
                    {
                        "id": str(row.id),
                        "peer_id": row.peer_id,
                        "fact": row.fact,
                        "confidence": row.confidence,
                        "decay_factor": row.decay_factor,
                        "evidence_episode_ids": row.evidence_episode_ids,
                    }
                    for row in upserted
                ]
            },
        )
        return task_context
