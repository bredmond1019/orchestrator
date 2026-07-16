"""ConsolidationWriteNode — terminal write step of dream-time consolidation.

For each peer in ``ConsolidationNode``'s output, in isolation from every
other peer in the same run:

1. ``UpsertMemoryNode.upsert_facts(...)`` — write the consolidated facts as
   ``SemanticMemory`` rows, applying the never-overwrite contradiction rule
   for any fact whose ``contradicts_fact_id`` names an existing row (block
   OR.S design decision 1: this is the same reusable ``app/memory/`` seam
   ``MemoryIngestWorkflow`` uses, so contradiction handling has exactly one
   implementation).
2. Refresh the owning ``Peer.representation`` with the consolidated summary.

This node does not talk to the database for fact writes directly — it
delegates to ``UpsertMemoryNode`` (the seam tests monkeypatch). Updating
``Peer.representation`` is a plain, single-column write local to this node,
scoped by the shared ``db_session`` factory (CLAUDE.md standing rule 7:
persistence only via ``GenericRepository``/the shared session seam, never ad
hoc elsewhere in a node).
"""

import uuid

from core.nodes.base import Node
from core.task import TaskContext
from database.peer import Peer
from memory.seams import DbSeamMixin
from memory.upsert_memory_node import UpsertMemoryNode


class ConsolidationWriteNode(Node, DbSeamMixin):
    """Terminal node: write consolidated facts + refreshed representations.

    ``_session_scope`` comes from ``DbSeamMixin`` (``app/memory/seams.py``) —
    see that module's docstring for why a mixin (not composition) preserves
    the per-instance test monkeypatches.
    """

    def __init__(
        self,
        source_node_name: str = "ConsolidationNode",
        upsert_memory_node: UpsertMemoryNode | None = None,
    ):
        """``source_node_name`` is the upstream node whose ``result`` carries
        the per-peer consolidation output. ``upsert_memory_node`` defaults to
        a fresh instance but is injectable so tests can supply a double."""
        self.source_node_name = source_node_name
        self.upsert_memory_node = upsert_memory_node or UpsertMemoryNode()

    def _update_representation(self, peer_id: str, representation: str) -> None:
        """Refresh ``Peer.representation`` for ``peer_id``.

        Silently a no-op if the peer row does not exist (a dangling peer_id
        from a malformed consolidation output must never raise and abort the
        rest of the batch — each peer is written in isolation).
        """
        with self._session_scope() as session:
            peer = session.query(Peer).filter_by(peer_id=peer_id).first()
            if peer is None:
                return
            peer.representation = representation
            session.add(peer)
            session.commit()

    @staticmethod
    def _coerce_fact_id(raw_id: str | None) -> uuid.UUID | None:
        """Parse ``raw_id`` (the string id ``ConsolidationNode`` proposed) into a
        ``uuid.UUID`` the ``SemanticMemory.id`` UUID column can compare against.

        ``None`` or an id the LLM hallucinated in a non-UUID shape both fall
        through to ``None`` (no contradiction resolved) rather than raising —
        a malformed ``contradicts_fact_id`` must never abort the whole peer's
        write.
        """
        if not raw_id:
            return None
        try:
            return uuid.UUID(str(raw_id))
        except (ValueError, AttributeError, TypeError):
            return None

    def _write_one_peer(self, peer_result: dict) -> dict:
        """Write one peer's consolidated facts + representation, in isolation
        from every other peer in the same consolidation run."""
        peer_id = peer_result["peer_id"]
        facts = [
            {
                "fact": fact["fact"],
                "confidence": fact.get("confidence"),
                "contradicts_fact_id": self._coerce_fact_id(fact.get("contradicts_fact_id")),
                "evidence_episode_ids": fact.get("evidence_episode_ids") or [],
            }
            for fact in peer_result.get("facts", [])
        ]
        # Drop null confidence so UpsertMemoryNode's default kicks in rather
        # than writing an explicit `None` confidence.
        for fact in facts:
            if fact["confidence"] is None:
                fact.pop("confidence")

        upserted = self.upsert_memory_node.upsert_facts(
            peer_id=peer_id, facts=facts, evidence_episode_ids=[]
        )
        self._update_representation(peer_id, peer_result["representation"])

        return {
            "peer_id": peer_id,
            "representation": peer_result["representation"],
            "upserted_fact_ids": [str(row.id) for row in upserted],
        }

    def process(self, task_context: TaskContext) -> TaskContext:
        """Write every peer's consolidated facts + representation.

        Reads ``task_context.get_node_output(self.source_node_name)["result"]``
        for ``{"workspace_id", "peers": [{"peer_id", "representation",
        "facts": [...]}, ...]}`` (CLAUDE.md standing rule 9 storage
        contract).

        Writes: ``{"workspace_id": <str>, "peers": [{"peer_id",
        "representation", "upserted_fact_ids"}, ...]}``.
        """
        source = task_context.get_node_output(self.source_node_name)["result"]
        written = [self._write_one_peer(peer_result) for peer_result in source.get("peers", [])]

        task_context.update_node(
            node_name=self.node_name,
            result={
                "workspace_id": source["workspace_id"],
                "peers": written,
            },
        )
        return task_context
