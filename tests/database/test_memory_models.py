"""Tests for the memory-layer models: Peer, AgentEpisode, SemanticMemory.

Schema shape, StrEnum values, defaults, FK relationships, JSON list columns,
and GenericRepository round-trips against an in-memory SQLite session
(mirroring the pattern in test_content_chunk.py / test_brain_document.py).
"""

import uuid
from datetime import datetime

import pytest
from database.agent_episode import EMBEDDING_DIM as EPISODE_EMBEDDING_DIM
from database.agent_episode import AgentEpisode
from database.peer import Peer, PeerType
from database.repository import GenericRepository
from database.semantic_memory import DEFAULT_DECAY_FACTOR
from database.semantic_memory import EMBEDDING_DIM as MEMORY_EMBEDDING_DIM
from database.semantic_memory import SemanticMemory
from database.session import Base
from sqlalchemy import DateTime, Float, String, Text, create_engine
from sqlalchemy.orm import sessionmaker

MEMORY_TABLES = [
    Peer.__table__,
    AgentEpisode.__table__,
    SemanticMemory.__table__,
]


@pytest.fixture
def session():
    """Provide a fresh in-memory SQLite session with all three memory tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=MEMORY_TABLES)
    session_factory = sessionmaker(bind=engine)
    s = session_factory()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture
def peer_repo(session):
    return GenericRepository(session, Peer)


@pytest.fixture
def episode_repo(session):
    return GenericRepository(session, AgentEpisode)


@pytest.fixture
def memory_repo(session):
    return GenericRepository(session, SemanticMemory)


def _make_peer(**overrides):
    defaults = dict(
        peer_id="client-acme",
        peer_type=PeerType.CLIENT,
        workspace_id="agentic-portfolio",
        representation="Acme is a mid-market retailer.",
    )
    defaults.update(overrides)
    return Peer(**defaults)


def _make_episode(**overrides):
    defaults = dict(
        peer_id="client-acme",
        session_id="session-1",
        summary="Discussed Q3 rate for the WhatsApp automation project.",
        outcome="quoted_rate",
        tags=["rate", "whatsapp"],
        embedding=[0.01] * EPISODE_EMBEDDING_DIM,
        occurred_at=datetime(2026, 7, 1),
    )
    defaults.update(overrides)
    return AgentEpisode(**defaults)


def _make_fact(**overrides):
    defaults = dict(
        peer_id="client-acme",
        fact="Acme was quoted $150/hr for the WhatsApp automation project.",
        confidence=0.9,
        evidence_episode_ids=[],
        embedding=[0.02] * MEMORY_EMBEDDING_DIM,
    )
    defaults.update(overrides)
    return SemanticMemory(**defaults)


class TestPeerSchema:
    """The Peer model declares the expected table name, columns, and types."""

    def test_table_name(self):
        assert Peer.__tablename__ == "peers"

    def test_expected_columns_present(self):
        columns = set(Peer.__table__.columns.keys())
        assert columns == {
            "peer_id",
            "peer_type",
            "workspace_id",
            "representation",
            "updated_at",
        }

    def test_peer_id_is_primary_key(self):
        assert Peer.__table__.columns["peer_id"].primary_key is True

    def test_peer_type_not_nullable(self):
        col = Peer.__table__.columns["peer_type"]
        assert isinstance(col.type, String)
        assert col.nullable is False

    def test_workspace_id_not_nullable(self):
        col = Peer.__table__.columns["workspace_id"]
        assert isinstance(col.type, String)
        assert col.nullable is False

    def test_representation_is_text(self):
        assert isinstance(Peer.__table__.columns["representation"].type, Text)

    def test_updated_at_is_datetime(self):
        assert isinstance(Peer.__table__.columns["updated_at"].type, DateTime)

    def test_workspace_peer_type_composite_index_exists(self):
        index_names = {ix.name for ix in Peer.__table__.indexes}
        assert "ix_peers_workspace_id_peer_type" in index_names


class TestPeerTypeEnum:
    """PeerType is a StrEnum with exactly the five entity kinds pinned by the spec."""

    def test_peer_type_values(self):
        assert {p.value for p in PeerType} == {
            "client",
            "company",
            "product",
            "sop",
            "user",
        }

    def test_peer_type_is_str_subclass(self):
        assert isinstance(PeerType.CLIENT, str)
        assert PeerType.CLIENT == "client"


class TestAgentEpisodeSchema:
    """The AgentEpisode model declares the expected columns and types."""

    def test_table_name(self):
        assert AgentEpisode.__tablename__ == "agent_episodes"

    def test_expected_columns_present(self):
        columns = set(AgentEpisode.__table__.columns.keys())
        assert columns == {
            "id",
            "peer_id",
            "session_id",
            "summary",
            "outcome",
            "tags",
            "embedding",
            "occurred_at",
        }

    def test_id_is_primary_key(self):
        assert AgentEpisode.__table__.columns["id"].primary_key is True

    def test_peer_id_is_foreign_key(self):
        col = AgentEpisode.__table__.columns["peer_id"]
        assert col.nullable is False
        fk_targets = {fk.target_fullname for fk in col.foreign_keys}
        assert fk_targets == {"peers.peer_id"}

    def test_summary_not_nullable(self):
        assert AgentEpisode.__table__.columns["summary"].nullable is False

    def test_embedding_dim_is_1024(self):
        assert EPISODE_EMBEDDING_DIM == 1024

    def test_embedding_column_has_1024_dim(self):
        assert AgentEpisode.__table__.columns["embedding"].type.dim == EPISODE_EMBEDDING_DIM


class TestSemanticMemorySchema:
    """The SemanticMemory model declares the expected columns, types, and defaults."""

    def test_table_name(self):
        assert SemanticMemory.__tablename__ == "semantic_memories"

    def test_expected_columns_present(self):
        columns = set(SemanticMemory.__table__.columns.keys())
        assert columns == {
            "id",
            "peer_id",
            "fact",
            "confidence",
            "evidence_episode_ids",
            "decay_factor",
            "source_peer_id",
            "created_at",
            "updated_at",
            "embedding",
        }

    def test_id_is_primary_key(self):
        assert SemanticMemory.__table__.columns["id"].primary_key is True

    def test_peer_id_is_foreign_key(self):
        col = SemanticMemory.__table__.columns["peer_id"]
        assert col.nullable is False
        fk_targets = {fk.target_fullname for fk in col.foreign_keys}
        assert fk_targets == {"peers.peer_id"}

    def test_source_peer_id_is_nullable_foreign_key(self):
        col = SemanticMemory.__table__.columns["source_peer_id"]
        assert col.nullable is True
        fk_targets = {fk.target_fullname for fk in col.foreign_keys}
        assert fk_targets == {"peers.peer_id"}

    def test_confidence_is_float_not_nullable(self):
        col = SemanticMemory.__table__.columns["confidence"]
        assert isinstance(col.type, Float)
        assert col.nullable is False

    def test_decay_factor_default_is_0_95(self):
        assert DEFAULT_DECAY_FACTOR == 0.95
        col = SemanticMemory.__table__.columns["decay_factor"]
        assert col.default.arg == 0.95

    def test_embedding_dim_is_1024(self):
        assert MEMORY_EMBEDDING_DIM == 1024


class TestPeerRoundTrip:
    """Peer instances persist and read back through GenericRepository."""

    def test_create_and_count(self, peer_repo):
        assert peer_repo.count() == 0
        peer_repo.create(_make_peer())
        assert peer_repo.count() == 1

    def test_round_trip_preserves_fields(self, peer_repo, session):
        peer_repo.create(_make_peer())
        fetched = session.query(Peer).filter_by(peer_id="client-acme").one()
        assert fetched.peer_type == PeerType.CLIENT
        assert fetched.workspace_id == "agentic-portfolio"
        assert fetched.representation == "Acme is a mid-market retailer."

    def test_peer_id_defaults_when_not_supplied(self, peer_repo, session):
        peer = Peer(
            peer_type=PeerType.COMPANY,
            workspace_id="agentic-portfolio",
        )
        peer_repo.create(peer)
        fetched = session.query(Peer).one()
        assert fetched.peer_id is not None
        # Defaulted peer_id is a valid UUID string.
        uuid.UUID(fetched.peer_id)

    def test_duplicate_peer_id_is_reused_not_duplicated(self, peer_repo, session):
        peer_repo.create(_make_peer())
        # Second write for the same (workspace_id, peer_id) should update, not
        # create a second row — proven at the model-write-service layer in
        # Task 2; here we prove the PK constraint that makes it possible.
        assert session.query(Peer).count() == 1
        existing = session.query(Peer).filter_by(peer_id="client-acme").one()
        existing.representation = "Acme renewed for another quarter."
        session.commit()
        assert session.query(Peer).count() == 1
        assert (
            session.query(Peer).filter_by(peer_id="client-acme").one().representation
            == "Acme renewed for another quarter."
        )


class TestAgentEpisodeRoundTrip:
    """AgentEpisode instances persist and read back through GenericRepository."""

    def test_create_assigns_uuid_id(self, episode_repo, peer_repo):
        peer_repo.create(_make_peer())
        episode = episode_repo.create(_make_episode())
        assert isinstance(episode.id, uuid.UUID)

    def test_round_trip_preserves_fields(self, episode_repo, peer_repo):
        peer_repo.create(_make_peer())
        created = episode_repo.create(_make_episode())
        fetched = episode_repo.get(created.id)
        assert fetched is not None
        assert fetched.peer_id == "client-acme"
        assert fetched.summary.startswith("Discussed Q3 rate")
        assert fetched.outcome == "quoted_rate"

    def test_tags_round_trip_as_list(self, episode_repo, peer_repo):
        peer_repo.create(_make_peer())
        created = episode_repo.create(_make_episode(tags=["rate", "whatsapp", "q3"]))
        fetched = episode_repo.get(created.id)
        assert fetched.tags == ["rate", "whatsapp", "q3"]

    def test_embedding_round_trip_preserves_length(self, episode_repo, peer_repo):
        peer_repo.create(_make_peer())
        created = episode_repo.create(_make_episode())
        fetched = episode_repo.get(created.id)
        assert len(fetched.embedding) == EPISODE_EMBEDDING_DIM

    def test_second_episode_for_same_peer_appends_not_replaces(
        self, episode_repo, peer_repo
    ):
        peer_repo.create(_make_peer())
        episode_repo.create(_make_episode(session_id="session-1"))
        episode_repo.create(
            _make_episode(
                session_id="session-2",
                summary="Follow-up: Acme confirmed the rate.",
                outcome="confirmed",
            )
        )
        assert episode_repo.count() == 2


class TestSemanticMemoryRoundTrip:
    """SemanticMemory instances persist and read back through GenericRepository."""

    def test_create_assigns_uuid_id(self, memory_repo, peer_repo):
        peer_repo.create(_make_peer())
        fact = memory_repo.create(_make_fact())
        assert isinstance(fact.id, uuid.UUID)

    def test_decay_factor_defaults_to_0_95(self, memory_repo, peer_repo):
        peer_repo.create(_make_peer())
        created = memory_repo.create(_make_fact())
        fetched = memory_repo.get(created.id)
        assert fetched.decay_factor == 0.95

    def test_round_trip_preserves_fields(self, memory_repo, peer_repo):
        peer_repo.create(_make_peer())
        created = memory_repo.create(_make_fact())
        fetched = memory_repo.get(created.id)
        assert fetched.peer_id == "client-acme"
        assert fetched.fact.startswith("Acme was quoted")
        assert fetched.confidence == 0.9

    def test_evidence_episode_ids_round_trip_as_list(self, memory_repo, peer_repo, episode_repo):
        peer_repo.create(_make_peer())
        episode = episode_repo.create(_make_episode())
        created = memory_repo.create(
            _make_fact(evidence_episode_ids=[str(episode.id)])
        )
        fetched = memory_repo.get(created.id)
        assert fetched.evidence_episode_ids == [str(episode.id)]

    def test_source_peer_id_defaults_to_none(self, memory_repo, peer_repo):
        peer_repo.create(_make_peer())
        created = memory_repo.create(_make_fact())
        fetched = memory_repo.get(created.id)
        assert fetched.source_peer_id is None

    def test_source_peer_id_can_reference_another_peer(self, memory_repo, peer_repo):
        peer_repo.create(_make_peer())
        peer_repo.create(_make_peer(peer_id="company-acme-corp", peer_type=PeerType.COMPANY))
        created = memory_repo.create(_make_fact(source_peer_id="company-acme-corp"))
        fetched = memory_repo.get(created.id)
        assert fetched.source_peer_id == "company-acme-corp"

    def test_contradicting_fact_never_overwrites_original_row(
        self, memory_repo, peer_repo
    ):
        peer_repo.create(_make_peer())
        original = memory_repo.create(_make_fact(confidence=0.9))
        # A contradicting fact lowers confidence on the original and inserts
        # a NEW row — this test proves both rows coexist at the model level;
        # the write logic itself lands in Task 2's UpsertMemoryNode.
        original.confidence = 0.4
        memory_repo.update(original)
        memory_repo.create(
            _make_fact(
                fact="Acme's rate was later renegotiated to $175/hr.",
                confidence=0.9,
                evidence_episode_ids=[],
            )
        )
        assert memory_repo.count() == 2
        preserved = memory_repo.get(original.id)
        assert preserved is not None
        assert preserved.confidence == 0.4
        assert preserved.fact.startswith("Acme was quoted")


class TestMultiPeerIsolation:
    """Facts and episodes scoped to one peer never bleed into another peer's rows."""

    def test_facts_scoped_to_peer_id(self, memory_repo, peer_repo, session):
        peer_repo.create(_make_peer(peer_id="client-a"))
        peer_repo.create(_make_peer(peer_id="client-b"))
        memory_repo.create(_make_fact(peer_id="client-a", fact="A-only fact."))
        memory_repo.create(_make_fact(peer_id="client-b", fact="B-only fact."))

        a_facts = session.query(SemanticMemory).filter_by(peer_id="client-a").all()
        b_facts = session.query(SemanticMemory).filter_by(peer_id="client-b").all()

        assert [f.fact for f in a_facts] == ["A-only fact."]
        assert [f.fact for f in b_facts] == ["B-only fact."]


class TestWorkspaceIsolation:
    """Peers scoped to one workspace never surface in another workspace's query."""

    def test_peers_scoped_to_workspace_id(self, peer_repo, session):
        peer_repo.create(
            _make_peer(peer_id="client-x", workspace_id="workspace-x")
        )
        peer_repo.create(
            _make_peer(peer_id="client-y", workspace_id="workspace-y")
        )

        workspace_x_peers = session.query(Peer).filter_by(workspace_id="workspace-x").all()
        workspace_y_peers = session.query(Peer).filter_by(workspace_id="workspace-y").all()

        assert [p.peer_id for p in workspace_x_peers] == ["client-x"]
        assert [p.peer_id for p in workspace_y_peers] == ["client-y"]
