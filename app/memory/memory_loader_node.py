"""MemoryLoaderNode — session-start top-k memory loading.

Reusable across any workflow (block OR.S design decision 1: a standalone
module, no coupling to any one workflow) — this is the node a session-start
loader (or any node that needs "what do we know about peer X") attaches to
its own DAG.

Two query modes (Honcho pattern, D25):

- **Cosine mode**: a caller-supplied query embedding is compared against
  every in-scope ``SemanticMemory.fact`` embedding via cosine similarity;
  results are ranked by similarity alone.
- **NL-question mode**: a natural-language question is embedded via
  ``EmbeddingService`` and facts are ranked by
  ``similarity * effective_confidence`` — so a stale, decayed fact that's
  still semantically close ranks below a fresher one of similar relevance
  (``app/memory/decay.py``).

Both modes are always scoped by ``workspace_id`` (D47 workspace-contract name
semantics — a verbatim string match, never fuzzy) and optionally narrowed to
one ``peer_id``. Optionally also returns the peer's most recent
``AgentEpisode`` summaries (by recency, not similarity) when
``include_episodes=True``.

Context budget: the block OR.S target is to keep injected representations to
5-10% of the context window. This node estimates the token cost of what it
loaded and logs a warning (never raises) when that estimate exceeds the
configured budget — a soft guard, not a hard failure.

DB access goes through the same mockable ``_session_scope``/``_embed`` seam
pattern as ``EpisodeWriteService``/``UpsertMemoryNode``; the cosine-similarity
and token-estimate math are pure, isolated static/module-level functions.
"""

import logging
import math
from datetime import datetime

from core.nodes.base import Node
from core.task import TaskContext
from database.agent_episode import AgentEpisode
from database.peer import Peer
from database.semantic_memory import SemanticMemory

from memory.decay import effective_confidence, weeks_between
from memory.seams import DbSeamMixin

logger = logging.getLogger(__name__)

# Default number of top-ranked facts returned when the caller doesn't
# override `top_k`.
DEFAULT_TOP_K = 5

# Default number of recent episode summaries returned when
# `include_episodes=True` and the caller doesn't override `episode_limit`.
DEFAULT_EPISODE_LIMIT = 5

# Assumed context-window size (tokens) used to translate the 5-10% target
# context-injection band from the spec into an absolute token budget.
DEFAULT_CONTEXT_WINDOW_TOKENS = 8000

# Upper bound of the 5-10% context-injection target band. Loaded content
# whose estimated token cost exceeds `budget_ratio * context_window_tokens`
# triggers a logged warning (soft guard — never raises).
DEFAULT_BUDGET_RATIO = 0.10

# Rough chars-per-token estimate (no live tokenizer dependency needed for a
# soft budget guard).
_CHARS_PER_TOKEN_ESTIMATE = 4


def _estimate_tokens(text: str) -> int:
    """Rough token-count estimate for a piece of text (chars // 4, min 0)."""
    if not text:
        return 0
    return max(1, len(text) // _CHARS_PER_TOKEN_ESTIMATE)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Pure cosine similarity between two equal-length vectors.

    Returns 0.0 (rather than raising) when either vector has zero magnitude
    or the vectors are missing/empty, so a row with no embedding never
    crashes ranking — it simply sorts last.
    """
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class MemoryLoaderNode(Node, DbSeamMixin):
    """Load top-k relevant memory (facts, optionally recent episodes) for a
    peer/workspace, by cosine similarity or NL-question ranking.

    ``_session_scope``/``_embed`` come from ``DbSeamMixin``
    (``app/memory/seams.py``) — see that module's docstring for why a mixin
    (not composition) preserves the per-instance test monkeypatches.
    """

    def __init__(
        self,
        top_k: int = DEFAULT_TOP_K,
        episode_limit: int = DEFAULT_EPISODE_LIMIT,
        context_window_tokens: int = DEFAULT_CONTEXT_WINDOW_TOKENS,
        budget_ratio: float = DEFAULT_BUDGET_RATIO,
    ):
        self.top_k = top_k
        self.episode_limit = episode_limit
        self.context_window_tokens = context_window_tokens
        self.budget_ratio = budget_ratio

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def retrieve(  # pylint: disable=too-many-arguments
        self,
        *,
        workspace_id: str,
        peer_id: str | None = None,
        query_embedding: list[float] | None = None,
        question: str | None = None,
        top_k: int | None = None,
        include_episodes: bool = False,
        episode_limit: int | None = None,
    ) -> dict:
        """Load top-k ranked ``SemanticMemory`` facts (+ optionally recent
        ``AgentEpisode`` summaries) scoped to ``workspace_id`` and,
        optionally, ``peer_id``.

        Exactly one of ``query_embedding`` (cosine mode) or ``question``
        (NL-question mode) must be supplied; a caller supplying neither (or
        both) gets a ``ValueError``.

        - **Cosine mode** (``query_embedding``): facts are ranked by cosine
          similarity to the supplied vector alone.
        - **NL-question mode** (``question``): the question is embedded and
          facts are ranked by ``similarity * effective_confidence`` — decay
          is applied on read (``app/memory/decay.py``), never mutating the
          stored ``confidence`` column.

        Returns ``{"facts": [...], "episodes": [...]}`` (``"episodes"`` only
        populated when ``include_episodes=True``). Each fact dict carries
        ``{"id", "peer_id", "fact", "confidence", "effective_confidence",
        "score", "evidence_episode_ids"}`` for downstream citation.
        """
        if bool(query_embedding) == bool(question):
            raise ValueError(
                "MemoryLoaderNode.retrieve requires exactly one of "
                "query_embedding (cosine mode) or question (NL-question mode)"
            )

        resolved_top_k = top_k if top_k is not None else self.top_k
        resolved_episode_limit = (
            episode_limit if episode_limit is not None else self.episode_limit
        )

        vector = query_embedding if query_embedding else self._embed(question)
        use_decay_weighting = question is not None

        facts = self._rank_facts(
            workspace_id=workspace_id,
            peer_id=peer_id,
            vector=vector,
            top_k=resolved_top_k,
            use_decay_weighting=use_decay_weighting,
        )
        episodes = (
            self._recent_episodes(
                workspace_id=workspace_id,
                peer_id=peer_id,
                limit=resolved_episode_limit,
            )
            if include_episodes
            else []
        )

        self._check_context_budget(facts, episodes)

        return {"facts": facts, "episodes": episodes}

    def _rank_facts(
        self,
        *,
        workspace_id: str,
        peer_id: str | None,
        vector: list[float],
        top_k: int,
        use_decay_weighting: bool,
    ) -> list[dict]:
        """Fetch in-scope ``SemanticMemory`` rows and return the top-k ranked
        as fact dicts."""
        scored: list[dict] = []
        with self._session_scope() as session:
            query = (
                session.query(SemanticMemory)
                .join(Peer, SemanticMemory.peer_id == Peer.peer_id)
                .filter(Peer.workspace_id == workspace_id)
            )
            if peer_id is not None:
                query = query.filter(SemanticMemory.peer_id == peer_id)
            scored = [
                self._score_fact(row, vector, use_decay_weighting) for row in query.all()
            ]
        scored.sort(key=lambda f: f["score"], reverse=True)
        return scored[:top_k]

    @staticmethod
    def _score_fact(row: SemanticMemory, vector: list[float], use_decay_weighting: bool) -> dict:
        """Score one ``SemanticMemory`` row against ``vector`` and return its
        fact dict, applying decay weighting to the score when requested."""
        embedding = list(row.embedding) if row.embedding is not None else []
        similarity = _cosine_similarity(vector, embedding)
        now = datetime.now()
        reference_time = row.updated_at or row.created_at or now
        decayed = effective_confidence(
            row.confidence, row.decay_factor, weeks_between(reference_time, now)
        )
        score = similarity * decayed if use_decay_weighting else similarity
        return {
            "id": str(row.id),
            "peer_id": row.peer_id,
            "fact": row.fact,
            "confidence": row.confidence,
            "effective_confidence": decayed,
            "score": score,
            "evidence_episode_ids": list(row.evidence_episode_ids or []),
        }

    def _recent_episodes(
        self, *, workspace_id: str, peer_id: str | None, limit: int
    ) -> list[dict]:
        """Fetch the ``limit`` most recent in-scope ``AgentEpisode`` rows,
        ordered by ``occurred_at`` descending (recency, not similarity)."""
        with self._session_scope() as session:
            query = (
                session.query(AgentEpisode)
                .join(Peer, AgentEpisode.peer_id == Peer.peer_id)
                .filter(Peer.workspace_id == workspace_id)
            )
            if peer_id is not None:
                query = query.filter(AgentEpisode.peer_id == peer_id)
            rows = query.order_by(AgentEpisode.occurred_at.desc()).limit(limit).all()
            return [
                {
                    "id": str(row.id),
                    "peer_id": row.peer_id,
                    "summary": row.summary,
                    "outcome": row.outcome,
                    "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                }
                for row in rows
            ]

    def _check_context_budget(self, facts: list[dict], episodes: list[dict]) -> None:
        """Log a warning (never raise) when the estimated token cost of the
        loaded facts + episode summaries exceeds the configured budget."""
        estimated_tokens = sum(_estimate_tokens(f["fact"]) for f in facts) + sum(
            _estimate_tokens(e["summary"]) for e in episodes
        )
        budget = self.context_window_tokens * self.budget_ratio
        if estimated_tokens > budget:
            logger.warning(
                "MemoryLoaderNode: loaded content estimated at %d tokens exceeds the "
                "%.0f%% context-injection budget (%d tokens of a %d-token window)",
                estimated_tokens,
                self.budget_ratio * 100,
                budget,
                self.context_window_tokens,
            )

    # ------------------------------------------------------------------
    # Node interface
    # ------------------------------------------------------------------

    def process(self, task_context: TaskContext) -> TaskContext:
        """Read loader params from the workflow event and load memory.

        Reads ``workspace_id`` (required), and optionally ``peer_id``,
        ``question``, ``query_embedding``, ``top_k``, ``include_episodes``,
        ``episode_limit`` off ``task_context.event`` — so this node attaches
        directly to any workflow's DAG without depending on a specific
        upstream node's output (design decision 1: no coupling to any one
        workflow).

        Writes ``{"facts": [...], "episodes": [...]}`` per ``retrieve()``.
        """
        event = task_context.event
        result = self.retrieve(
            workspace_id=event.workspace_id,
            peer_id=getattr(event, "peer_id", None),
            query_embedding=getattr(event, "query_embedding", None),
            question=getattr(event, "question", None),
            top_k=getattr(event, "top_k", None),
            include_episodes=getattr(event, "include_episodes", False),
            episode_limit=getattr(event, "episode_limit", None),
        )
        task_context.update_node(node_name=self.node_name, result=result)
        return task_context
