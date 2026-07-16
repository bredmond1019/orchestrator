"""EpisodeWriteService — fast, ingest-time episode + peer-accumulation write path.

Writes one ``AgentEpisode`` per interaction and upserts the owning ``Peer``:
creates it on first sight of ``(workspace_id, peer_id)``, otherwise reuses the
existing row and bumps its ``updated_at`` (so a client entity *accumulates*
episodes across interactions instead of duplicating peer rows — the
foundation of the block OR.S accumulation acceptance criterion).

Persistence goes only through the shared ``db_session`` factory / SQLAlchemy
session (CLAUDE.md standing rule 7 — no deployment logic in nodes/services).
``_session_scope`` and ``_embed`` are isolated seams, mockable the same way
``AssembleContextNode._load_session`` is: tests monkeypatch ``_session_scope``
to yield a real (SQLite) test session and ``_embed`` to avoid a live
embedding provider call.
"""

from datetime import datetime

from database.agent_episode import AgentEpisode
from database.peer import Peer

from memory.seams import DbSeamMixin


class EpisodeWriteService(DbSeamMixin):
    """Write an episode and upsert its owning peer in a single transaction.

    ``_session_scope``/``_embed`` come from ``DbSeamMixin``
    (``app/memory/seams.py``) — see that module's docstring for why a mixin
    (not composition) preserves the per-instance test monkeypatches.
    """

    # ------------------------------------------------------------------
    # Core logic
    # ------------------------------------------------------------------

    def _load_or_create_peer(
        self, session, *, workspace_id: str, peer_id: str, peer_type: str
    ) -> Peer:
        """Load the existing ``(workspace_id, peer_id)`` peer, or create it.

        A peer is scoped by ``workspace_id`` per the D47 workspace-contract
        name semantics; matching is a verbatim string comparison. Reusing an
        existing peer (rather than creating a new one) is what lets a client
        entity accumulate episodes and facts across interactions.
        """
        peer = (
            session.query(Peer)
            .filter_by(workspace_id=workspace_id, peer_id=peer_id)
            .first()
        )
        if peer is None:
            peer = Peer(peer_id=peer_id, peer_type=peer_type, workspace_id=workspace_id)
            session.add(peer)
        else:
            peer.updated_at = datetime.now()
        return peer

    def write(  # pylint: disable=too-many-arguments
        self,
        *,
        workspace_id: str,
        peer_id: str,
        peer_type: str,
        summary: str,
        session_id: str | None = None,
        outcome: str | None = None,
        tags: list[str] | None = None,
        occurred_at: datetime | None = None,
    ) -> AgentEpisode:
        """Write one ``AgentEpisode`` for ``peer_id``, upserting its ``Peer``.

        Returns the persisted ``AgentEpisode`` (embedding + generated id
        populated).
        """
        embedding = self._embed(summary)
        with self._session_scope() as session:
            self._load_or_create_peer(
                session, workspace_id=workspace_id, peer_id=peer_id, peer_type=peer_type
            )
            episode = AgentEpisode(
                peer_id=peer_id,
                session_id=session_id,
                summary=summary,
                outcome=outcome,
                tags=list(tags or []),
                embedding=embedding,
                occurred_at=occurred_at or datetime.now(),
            )
            session.add(episode)
            session.commit()
            session.refresh(episode)
            return episode
