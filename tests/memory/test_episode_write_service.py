"""Tests for app/memory/episode_write_service.py — EpisodeWriteService.

Uses an in-memory SQLite session (Peer + AgentEpisode tables only) injected
via the ``_session_scope`` seam, and a stubbed ``_embed`` seam so no live
embedding provider is touched — mirroring the ``AssembleContextNode``
DB-seam-patching pattern.
"""

from contextlib import contextmanager
from datetime import datetime

import pytest
from database.agent_episode import AgentEpisode
from database.peer import Peer, PeerType
from database.session import Base
from memory.episode_write_service import EpisodeWriteService
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

_STUB_EMBEDDING = [0.01] * 1024


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Peer.__table__, AgentEpisode.__table__])
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture
def service(session_factory):
    svc = EpisodeWriteService()

    @contextmanager
    def _session_scope():
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    svc._session_scope = _session_scope  # noqa: SLF001 -- test seam injection
    svc._embed = lambda text: _STUB_EMBEDDING  # noqa: SLF001 -- avoid live provider
    return svc


class TestEpisodeWriteServiceWrite:
    def test_first_write_creates_peer_and_episode(self, service, session_factory):
        episode = service.write(
            workspace_id="agentic-portfolio",
            peer_id="client-acme",
            peer_type=PeerType.CLIENT,
            summary="Discussed Q3 rate for the WhatsApp automation project.",
            outcome="quoted_rate",
            tags=["rate", "whatsapp"],
        )
        assert episode.id is not None
        assert list(episode.embedding) == _STUB_EMBEDDING

        with session_factory() as session:
            assert session.query(Peer).count() == 1
            peer = session.query(Peer).filter_by(peer_id="client-acme").one()
            assert peer.peer_type == PeerType.CLIENT
            assert peer.workspace_id == "agentic-portfolio"
            assert session.query(AgentEpisode).count() == 1

    def test_second_write_reuses_peer_not_duplicated(self, service, session_factory):
        service.write(
            workspace_id="agentic-portfolio",
            peer_id="client-acme",
            peer_type=PeerType.CLIENT,
            summary="Discussed Q3 rate.",
            session_id="session-1",
        )
        service.write(
            workspace_id="agentic-portfolio",
            peer_id="client-acme",
            peer_type=PeerType.CLIENT,
            summary="Follow-up: Acme confirmed the rate.",
            session_id="session-2",
        )

        with session_factory() as session:
            assert session.query(Peer).count() == 1
            assert session.query(AgentEpisode).count() == 2

    def test_second_write_bumps_peer_updated_at(self, service, session_factory):
        first = service.write(
            workspace_id="agentic-portfolio",
            peer_id="client-acme",
            peer_type=PeerType.CLIENT,
            summary="Discussed Q3 rate.",
            occurred_at=datetime(2026, 1, 1),
        )
        with session_factory() as session:
            peer_after_first = session.query(Peer).filter_by(peer_id="client-acme").one()
            first_updated_at = peer_after_first.updated_at

        service.write(
            workspace_id="agentic-portfolio",
            peer_id="client-acme",
            peer_type=PeerType.CLIENT,
            summary="Follow-up.",
            occurred_at=datetime(2026, 1, 8),
        )
        with session_factory() as session:
            peer_after_second = session.query(Peer).filter_by(peer_id="client-acme").one()
            assert peer_after_second.updated_at >= first_updated_at
        assert first.id is not None

    def test_tags_default_to_empty_list(self, service):
        episode = service.write(
            workspace_id="agentic-portfolio",
            peer_id="client-acme",
            peer_type=PeerType.CLIENT,
            summary="No tags supplied.",
        )
        assert episode.tags == []

    def test_occurred_at_defaults_to_now_when_not_supplied(self, service):
        before = datetime.now()
        episode = service.write(
            workspace_id="agentic-portfolio",
            peer_id="client-acme",
            peer_type=PeerType.CLIENT,
            summary="No occurred_at supplied.",
        )
        after = datetime.now()
        assert before <= episode.occurred_at <= after
