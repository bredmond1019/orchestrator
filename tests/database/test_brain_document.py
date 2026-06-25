"""Tests for the BrainDocument model: schema shape and GenericRepository round-trip."""

import uuid

import pytest
from database.brain_document import EMBEDDING_DIM, BrainDocument
from database.repository import GenericRepository
from database.session import Base
from sqlalchemy import DateTime, String, Text, create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session():
    """Provide a fresh in-memory SQLite session with the brain_documents table.

    SQLite does not support PostgreSQL's ARRAY type (used by workflow_patterns),
    so round-trip tests are skipped when table creation fails.
    """
    engine = create_engine("sqlite:///:memory:")
    try:
        Base.metadata.create_all(engine, tables=[BrainDocument.__table__])
    except Exception as exc:
        pytest.skip(
            f"SQLite does not support all BrainDocument column types (ARRAY): {exc}"
        )
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture
def repo(session):
    """Return a GenericRepository bound to the BrainDocument model."""
    return GenericRepository(session, BrainDocument)


def _make_brain_doc(**overrides):
    """Build a fully-populated BrainDocument, allowing per-test overrides."""
    defaults = dict(
        file_path="docs/career.md",
        doc_type="career",
        section="## Experience",
        content="This section covers professional experience.",
        embedding=[0.01] * EMBEDDING_DIM,
    )
    defaults.update(overrides)
    return BrainDocument(**defaults)


class TestSchema:
    """The model declares the table name and every required column with its type."""

    def test_table_name(self):
        assert BrainDocument.__tablename__ == "brain_documents"

    def test_embedding_dim_is_1024(self):
        assert EMBEDDING_DIM == 1024

    def test_expected_columns_present(self):
        columns = set(BrainDocument.__table__.columns.keys())
        expected = {
            "id",
            "file_path",
            "doc_type",
            "section",
            "content",
            "embedding",
            "indexed_at",
            "client_slug",
            "workflow_patterns",
            "doc_id",
            "layer",
            "project",
            "status",
            "keywords",
            "related",
        }
        assert expected <= columns

    def test_id_is_primary_key(self):
        assert BrainDocument.__table__.columns["id"].primary_key is True

    def test_file_path_not_nullable(self):
        col = BrainDocument.__table__.columns["file_path"]
        assert isinstance(col.type, String)
        assert col.nullable is False

    def test_doc_type_not_nullable(self):
        col = BrainDocument.__table__.columns["doc_type"]
        assert isinstance(col.type, String)
        assert col.nullable is False

    def test_content_is_text(self):
        assert isinstance(BrainDocument.__table__.columns["content"].type, Text)

    def test_content_not_nullable(self):
        assert BrainDocument.__table__.columns["content"].nullable is False

    def test_section_is_nullable(self):
        assert BrainDocument.__table__.columns["section"].nullable is True

    def test_client_slug_is_nullable(self):
        assert BrainDocument.__table__.columns["client_slug"].nullable is True

    def test_workflow_patterns_is_nullable(self):
        assert BrainDocument.__table__.columns["workflow_patterns"].nullable is True

    def test_doc_id_is_nullable(self):
        assert BrainDocument.__table__.columns["doc_id"].nullable is True

    def test_layer_is_nullable(self):
        assert BrainDocument.__table__.columns["layer"].nullable is True

    def test_project_is_nullable(self):
        assert BrainDocument.__table__.columns["project"].nullable is True

    def test_status_frontmatter_is_nullable(self):
        assert BrainDocument.__table__.columns["status"].nullable is True

    def test_keywords_is_nullable(self):
        assert BrainDocument.__table__.columns["keywords"].nullable is True

    def test_related_is_nullable(self):
        assert BrainDocument.__table__.columns["related"].nullable is True

    def test_doc_id_is_string_type(self):
        col = BrainDocument.__table__.columns["doc_id"]
        assert isinstance(col.type, String)

    def test_project_is_string_type(self):
        col = BrainDocument.__table__.columns["project"]
        assert isinstance(col.type, String)

    def test_status_frontmatter_is_string_type(self):
        col = BrainDocument.__table__.columns["status"]
        assert isinstance(col.type, String)

    def test_indexed_at_is_datetime(self):
        assert isinstance(BrainDocument.__table__.columns["indexed_at"].type, DateTime)

    def test_embedding_column_has_1024_dim(self):
        assert BrainDocument.__table__.columns["embedding"].type.dim == EMBEDDING_DIM


class TestRoundTrip:
    """Instantiation persists and reads back through GenericRepository."""

    def test_create_assigns_uuid_id(self, repo):
        doc = _make_brain_doc()
        created = repo.create(doc)
        assert isinstance(created.id, uuid.UUID)

    def test_round_trip_preserves_required_fields(self, repo):
        doc = _make_brain_doc(file_path="docs/brand.md", doc_type="brand")
        repo.create(doc)
        fetched = repo.get(doc.id)
        assert fetched is not None
        assert fetched.file_path == "docs/brand.md"
        assert fetched.doc_type == "brand"
        assert fetched.content == "This section covers professional experience."

    def test_round_trip_preserves_section(self, repo):
        doc = _make_brain_doc(section="## Standing Rules")
        repo.create(doc)
        fetched = repo.get(doc.id)
        assert fetched.section == "## Standing Rules"

    def test_round_trip_nullable_fields_default_to_none(self, repo):
        doc = _make_brain_doc()
        repo.create(doc)
        fetched = repo.get(doc.id)
        assert fetched.client_slug is None
        assert fetched.workflow_patterns is None
        assert fetched.doc_id is None
        assert fetched.layer is None
        assert fetched.project is None
        assert fetched.status is None
        assert fetched.keywords is None
        assert fetched.related is None

    def test_round_trip_preserves_embedding_length(self, repo):
        doc = _make_brain_doc()
        repo.create(doc)
        fetched = repo.get(doc.id)
        assert len(fetched.embedding) == EMBEDDING_DIM

    def test_count_reflects_created_rows(self, repo):
        assert repo.count() == 0
        repo.create(_make_brain_doc())
        repo.create(_make_brain_doc(file_path="docs/brand.md", doc_type="brand"))
        assert repo.count() == 2

    def test_no_section_is_empty_string(self, repo):
        doc = _make_brain_doc(section="")
        repo.create(doc)
        fetched = repo.get(doc.id)
        assert fetched.section == ""
