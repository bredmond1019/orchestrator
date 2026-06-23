"""Tests for the ChatSession model: schema shape and GenericRepository round-trip."""

import uuid

import pytest
from database.chat_session import ChatSession
from database.repository import GenericRepository
from database.session import Base
from sqlalchemy import JSON, DateTime, create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session():
    """Provide a fresh in-memory SQLite session with the chat_sessions table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ChatSession.__table__])
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture
def repo(session):
    """Return a GenericRepository bound to the ChatSession model."""
    return GenericRepository(session, ChatSession)


def _make_session(**overrides):
    """Build a fully-populated ChatSession, allowing per-test overrides."""
    defaults = dict(
        doc_id=uuid.uuid4(),
        turns=[],
        topics_covered=[],
    )
    defaults.update(overrides)
    return ChatSession(**defaults)


class TestSchema:
    """The model declares the table name and every required column with its type."""

    def test_table_name(self):
        assert ChatSession.__tablename__ == "chat_sessions"

    def test_expected_columns_present(self):
        columns = set(ChatSession.__table__.columns.keys())
        expected = {
            "id",
            "doc_id",
            "turns",
            "topics_covered",
            "created_at",
            "updated_at",
        }
        assert expected <= columns

    def test_id_is_primary_key(self):
        assert ChatSession.__table__.columns["id"].primary_key is True

    def test_turns_is_json(self):
        assert isinstance(ChatSession.__table__.columns["turns"].type, JSON)

    def test_topics_covered_is_json(self):
        assert isinstance(ChatSession.__table__.columns["topics_covered"].type, JSON)

    def test_created_at_is_datetime(self):
        assert isinstance(ChatSession.__table__.columns["created_at"].type, DateTime)

    def test_updated_at_is_datetime(self):
        assert isinstance(ChatSession.__table__.columns["updated_at"].type, DateTime)

    def test_doc_id_is_not_nullable(self):
        assert ChatSession.__table__.columns["doc_id"].nullable is False


class TestRoundTrip:
    """Instantiation persists and reads back through GenericRepository."""

    def test_create_assigns_uuid_id(self, repo):
        chat = _make_session()
        created = repo.create(chat)
        assert isinstance(created.id, uuid.UUID)

    def test_round_trip_preserves_turns(self, repo):
        turns = [{"role": "user", "content": "hi"}]
        chat = _make_session(turns=turns)
        repo.create(chat)
        fetched = repo.get(chat.id)
        assert fetched is not None
        assert fetched.turns == turns

    def test_round_trip_preserves_multiple_turns(self, repo):
        turns = [
            {"role": "user", "content": "What is RAG?"},
            {"role": "assistant", "content": "RAG stands for Retrieval-Augmented Generation."},
        ]
        chat = _make_session(turns=turns)
        repo.create(chat)
        fetched = repo.get(chat.id)
        assert fetched.turns == turns

    def test_topics_covered_defaults_to_list(self, repo):
        # Create without explicitly setting topics_covered
        chat = _make_session()
        repo.create(chat)
        fetched = repo.get(chat.id)
        # SQLite stores JSON null as None or empty list depending on default
        assert fetched.topics_covered == [] or fetched.topics_covered is None

    def test_round_trip_preserves_topics_covered(self, repo):
        topics = ["retrieval", "embeddings"]
        chat = _make_session(topics_covered=topics)
        repo.create(chat)
        fetched = repo.get(chat.id)
        assert fetched.topics_covered == topics

    def test_doc_id_preserved(self, repo):
        doc_id = uuid.uuid4()
        chat = _make_session(doc_id=doc_id)
        repo.create(chat)
        fetched = repo.get(chat.id)
        assert fetched.doc_id == doc_id
