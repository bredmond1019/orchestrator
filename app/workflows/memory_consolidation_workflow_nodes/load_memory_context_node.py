"""LoadMemoryContextNode — dream-time context gather for consolidation.

Loads the raw material ``ConsolidationNode`` reasons over: for every peer in
scope (either the single ``event.peer_id``, or every ``Peer`` row in
``event.workspace_id`` when ``peer_id`` is omitted — the nightly-batch case),
gathers its recent ``AgentEpisode`` rows (optionally filtered by
``event.since``), its current ``SemanticMemory`` facts, and its prior
``representation`` text.

Persistence goes only through the shared ``db_session`` factory (CLAUDE.md
standing rule 7). ``_session_scope`` is an isolated seam, mockable the same
way ``EpisodeWriteService._session_scope`` is: tests monkeypatch it to yield
a real (SQLite) test session.
"""

from core.nodes.base import Node
from core.task import TaskContext
from database.agent_episode import AgentEpisode
from database.peer import Peer
from database.semantic_memory import SemanticMemory
from memory.seams import DbSeamMixin


class LoadMemoryContextNode(Node, DbSeamMixin):
    """Load per-peer episodes, facts, and representation for consolidation.

    ``_session_scope`` comes from ``DbSeamMixin`` (``app/memory/seams.py``) —
    see that module's docstring for why a mixin (not composition) preserves
    the per-instance test monkeypatches.
    """

    def _peers_in_scope(self, session, *, workspace_id: str, peer_id: str | None) -> list[Peer]:
        """Return the peer(s) this consolidation pass reasons over.

        A single peer when ``peer_id`` is set (still scoped by
        ``workspace_id``, per D47 name semantics); every peer in the
        workspace otherwise.
        """
        query = session.query(Peer).filter_by(workspace_id=workspace_id)
        if peer_id is not None:
            query = query.filter_by(peer_id=peer_id)
        return query.all()

    def _load_peer_context(self, session, peer: Peer, since) -> dict:
        """Gather one peer's episodes + current facts + representation."""
        episode_query = session.query(AgentEpisode).filter_by(peer_id=peer.peer_id)
        if since is not None:
            episode_query = episode_query.filter(AgentEpisode.occurred_at >= since)
        episodes = episode_query.order_by(AgentEpisode.occurred_at.asc()).all()

        facts = session.query(SemanticMemory).filter_by(peer_id=peer.peer_id).all()

        return {
            "peer_id": peer.peer_id,
            "peer_type": peer.peer_type,
            "representation": peer.representation,
            "episodes": [
                {
                    "id": str(episode.id),
                    "summary": episode.summary,
                    "outcome": episode.outcome,
                    "tags": list(episode.tags or []),
                    "occurred_at": episode.occurred_at.isoformat()
                    if episode.occurred_at
                    else None,
                }
                for episode in episodes
            ],
            "facts": [
                {
                    "id": str(fact.id),
                    "fact": fact.fact,
                    "confidence": fact.confidence,
                    "decay_factor": fact.decay_factor,
                }
                for fact in facts
            ],
        }

    def process(self, task_context: TaskContext) -> TaskContext:
        """Load the consolidation context for every peer in scope.

        Reads: ``task_context.event`` — ``MemoryConsolidationEventSchema``
        (``workspace_id``, optional ``peer_id``, optional ``since``).

        Writes: ``{"workspace_id": <str>, "peers": [<per-peer context dict>,
        ...]}`` — one entry per peer in scope (possibly empty when no peers
        match).
        """
        event = task_context.event
        with self._session_scope() as session:
            peers = self._peers_in_scope(
                session, workspace_id=event.workspace_id, peer_id=event.peer_id
            )
            peer_contexts = [
                self._load_peer_context(session, peer, event.since) for peer in peers
            ]

        task_context.update_node(
            node_name=self.node_name,
            result={
                "workspace_id": event.workspace_id,
                "peers": peer_contexts,
            },
        )
        return task_context
