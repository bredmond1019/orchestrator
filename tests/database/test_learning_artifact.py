"""Tests for the LearningArtifact model: schema shape and GenericRepository round-trip."""

import uuid

import pytest
from database.learning_artifact import EMBEDDING_DIM, LearningArtifact
from database.repository import GenericRepository
from database.session import Base
from sqlalchemy import JSON, Boolean, DateTime, String, create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session():
    """Provide a fresh in-memory SQLite session with the learning_artifacts table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[LearningArtifact.__table__])
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture
def repo(session):
    """Return a GenericRepository bound to the LearningArtifact model."""
    return GenericRepository(session, LearningArtifact)


def _make_artifact(**overrides):
    """Build a fully-populated LearningArtifact, allowing per-test overrides."""
    defaults = dict(
        source_url="https://example.com/post",
        source_type="article",
        title="A Test Artifact",
        category="ai_engineering",
        tl_dr="One-line summary.",
        summary={"title": "A Test Artifact", "key_insights": ["x", "y"]},
        embedding=[0.01] * EMBEDDING_DIM,
        fetch_status="ok",
        make_blog=False,
    )
    defaults.update(overrides)
    return LearningArtifact(**defaults)


class TestSchema:
    """The model declares the table name and every required column with its type."""

    def test_table_name(self):
        assert LearningArtifact.__tablename__ == "learning_artifacts"

    def test_embedding_dim_is_1024(self):
        assert EMBEDDING_DIM == 1024

    def test_expected_columns_present(self):
        columns = set(LearningArtifact.__table__.columns.keys())
        expected = {
            "id",
            "source_url",
            "source_type",
            "title",
            "category",
            "tl_dr",
            "summary",
            "embedding",
            "fetch_status",
            "make_blog",
            "created_at",
        }
        assert expected <= columns

    def test_id_is_primary_key(self):
        assert LearningArtifact.__table__.columns["id"].primary_key is True

    def test_summary_is_json_column(self):
        assert isinstance(LearningArtifact.__table__.columns["summary"].type, JSON)

    def test_make_blog_is_boolean_column(self):
        assert isinstance(
            LearningArtifact.__table__.columns["make_blog"].type, Boolean
        )

    def test_created_at_is_datetime_column(self):
        assert isinstance(
            LearningArtifact.__table__.columns["created_at"].type, DateTime
        )

    def test_source_url_is_string_and_not_nullable(self):
        col = LearningArtifact.__table__.columns["source_url"]
        assert isinstance(col.type, String)
        assert col.nullable is False

    def test_embedding_column_has_1024_dim(self):
        # pgvector's Vector type exposes its dimensionality via .dim
        assert LearningArtifact.__table__.columns["embedding"].type.dim == EMBEDDING_DIM


class TestRoundTrip:
    """Instantiation persists and reads back through GenericRepository."""

    def test_create_assigns_uuid_id(self, repo):
        artifact = _make_artifact()
        created = repo.create(artifact)
        assert isinstance(created.id, uuid.UUID)

    def test_round_trip_preserves_scalar_fields(self, repo):
        artifact = _make_artifact(title="Roundtrip", category="physics_relativity")
        repo.create(artifact)
        fetched = repo.get(artifact.id)
        assert fetched is not None
        assert fetched.title == "Roundtrip"
        assert fetched.category == "physics_relativity"
        assert fetched.source_type == "article"
        assert fetched.fetch_status == "ok"
        assert fetched.make_blog is False

    def test_round_trip_preserves_json_summary(self, repo):
        artifact = _make_artifact(summary={"tl_dr": "hi", "core_concepts": ["a"]})
        repo.create(artifact)
        fetched = repo.get(artifact.id)
        assert fetched.summary == {"tl_dr": "hi", "core_concepts": ["a"]}

    def test_round_trip_preserves_embedding_length(self, repo):
        artifact = _make_artifact()
        repo.create(artifact)
        fetched = repo.get(artifact.id)
        assert len(fetched.embedding) == EMBEDDING_DIM

    def test_count_reflects_created_rows(self, repo):
        assert repo.count() == 0
        repo.create(_make_artifact())
        repo.create(_make_artifact())
        assert repo.count() == 2
