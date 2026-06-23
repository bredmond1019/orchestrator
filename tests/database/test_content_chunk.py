"""Tests for the ContentChunk model: schema shape and GenericRepository round-trip."""

import uuid

import pytest
from database.content_chunk import EMBEDDING_DIM, ContentChunk
from database.repository import GenericRepository
from database.session import Base
from sqlalchemy import Boolean, DateTime, Integer, String, Text, create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session():
    """Provide a fresh in-memory SQLite session with the content_chunks table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[ContentChunk.__table__])
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture
def repo(session):
    """Return a GenericRepository bound to the ContentChunk model."""
    return GenericRepository(session, ContentChunk)


def _make_chunk(**overrides):
    """Build a fully-populated ContentChunk, allowing per-test overrides."""
    defaults = dict(
        doc_id=uuid.uuid4(),
        position=0,
        section_title="Intro",
        is_section_title=False,
        content="hello world",
        embedding=[0.01] * EMBEDDING_DIM,
    )
    defaults.update(overrides)
    return ContentChunk(**defaults)


class TestSchema:
    """The model declares the table name and every required column with its type."""

    def test_table_name(self):
        assert ContentChunk.__tablename__ == "content_chunks"

    def test_embedding_dim_is_1024(self):
        assert EMBEDDING_DIM == 1024

    def test_expected_columns_present(self):
        columns = set(ContentChunk.__table__.columns.keys())
        expected = {
            "id",
            "doc_id",
            "position",
            "section_title",
            "is_section_title",
            "content",
            "embedding",
            "created_at",
        }
        assert expected <= columns

    def test_id_is_primary_key(self):
        assert ContentChunk.__table__.columns["id"].primary_key is True

    def test_embedding_column_has_1024_dim(self):
        # pgvector's Vector type exposes its dimensionality via .dim
        assert ContentChunk.__table__.columns["embedding"].type.dim == EMBEDDING_DIM

    def test_is_section_title_is_boolean(self):
        assert isinstance(
            ContentChunk.__table__.columns["is_section_title"].type, Boolean
        )

    def test_position_is_integer(self):
        assert isinstance(ContentChunk.__table__.columns["position"].type, Integer)

    def test_content_is_text(self):
        assert isinstance(ContentChunk.__table__.columns["content"].type, Text)

    def test_section_title_is_string(self):
        assert isinstance(ContentChunk.__table__.columns["section_title"].type, String)

    def test_created_at_is_datetime(self):
        assert isinstance(ContentChunk.__table__.columns["created_at"].type, DateTime)

    def test_doc_id_is_not_nullable(self):
        assert ContentChunk.__table__.columns["doc_id"].nullable is False

    def test_position_is_not_nullable(self):
        assert ContentChunk.__table__.columns["position"].nullable is False


class TestRoundTrip:
    """Instantiation persists and reads back through GenericRepository."""

    def test_create_assigns_uuid_id(self, repo):
        chunk = _make_chunk()
        created = repo.create(chunk)
        assert isinstance(created.id, uuid.UUID)

    def test_round_trip_preserves_position_and_section(self, repo):
        chunk = _make_chunk(position=3, section_title="Overview")
        repo.create(chunk)
        fetched = repo.get(chunk.id)
        assert fetched is not None
        assert fetched.position == 3
        assert fetched.section_title == "Overview"
        assert fetched.is_section_title is False

    def test_round_trip_preserves_embedding_length(self, repo):
        chunk = _make_chunk()
        repo.create(chunk)
        fetched = repo.get(chunk.id)
        assert len(fetched.embedding) == EMBEDDING_DIM

    def test_count_reflects_created_rows(self, repo):
        assert repo.count() == 0
        doc_id = uuid.uuid4()
        repo.create(_make_chunk(doc_id=doc_id, position=0))
        repo.create(_make_chunk(doc_id=doc_id, position=1))
        assert repo.count() == 2

    def test_section_title_nullable(self, repo):
        chunk = _make_chunk(section_title=None)
        repo.create(chunk)
        fetched = repo.get(chunk.id)
        assert fetched.section_title is None

    def test_is_section_title_true(self, repo):
        chunk = _make_chunk(is_section_title=True, section_title="# My Header")
        repo.create(chunk)
        fetched = repo.get(chunk.id)
        assert fetched.is_section_title is True
