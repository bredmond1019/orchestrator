"""Tests for the BrainEdge model: schema shape and GenericRepository round-trip."""

import uuid

import pytest
from database.brain_edge import BrainEdge
from database.repository import GenericRepository
from database.session import Base
from sqlalchemy import DateTime, String, create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session():
    """Provide a fresh in-memory SQLite session with the brain_edges table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[BrainEdge.__table__])
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture
def repo(session):
    """Return a GenericRepository bound to the BrainEdge model."""
    return GenericRepository(session, BrainEdge)


def _make_brain_edge(**overrides):
    """Build a fully-populated (resolved) BrainEdge, allowing per-test overrides."""
    defaults = dict(
        source_node_id="brain:alpha",
        source_doc_id="alpha",
        to_ref="beta",
        target_node_id="brain:beta",
        target_doc_id="beta",
    )
    defaults.update(overrides)
    return BrainEdge(**defaults)


class TestSchema:
    """The model declares the table name and every required column with its type."""

    def test_table_name(self):
        assert BrainEdge.__tablename__ == "brain_edges"

    def test_expected_columns_present(self):
        columns = set(BrainEdge.__table__.columns.keys())
        expected = {
            "id",
            "source_node_id",
            "source_doc_id",
            "to_ref",
            "target_node_id",
            "target_doc_id",
            "kind",
            "scope",
            "indexed_at",
        }
        assert expected <= columns

    def test_id_is_primary_key(self):
        assert BrainEdge.__table__.columns["id"].primary_key is True

    def test_source_node_id_not_nullable(self):
        col = BrainEdge.__table__.columns["source_node_id"]
        assert isinstance(col.type, String)
        assert col.nullable is False

    def test_source_doc_id_not_nullable(self):
        col = BrainEdge.__table__.columns["source_doc_id"]
        assert isinstance(col.type, String)
        assert col.nullable is False

    def test_to_ref_not_nullable(self):
        col = BrainEdge.__table__.columns["to_ref"]
        assert isinstance(col.type, String)
        assert col.nullable is False

    def test_target_node_id_is_nullable(self):
        assert BrainEdge.__table__.columns["target_node_id"].nullable is True

    def test_target_doc_id_is_nullable(self):
        assert BrainEdge.__table__.columns["target_doc_id"].nullable is True

    def test_scope_is_nullable(self):
        assert BrainEdge.__table__.columns["scope"].nullable is True

    def test_kind_not_nullable(self):
        assert BrainEdge.__table__.columns["kind"].nullable is False

    def test_indexed_at_is_datetime(self):
        assert isinstance(BrainEdge.__table__.columns["indexed_at"].type, DateTime)

    def test_unique_constraint_on_source_node_id_and_to_ref(self):
        constraint_columns = {
            frozenset(c.columns.keys())
            for c in BrainEdge.__table__.constraints
            if hasattr(c, "columns") and len(c.columns) > 1
        }
        assert frozenset({"source_node_id", "to_ref"}) in constraint_columns

    def test_indexes_on_source_and_target_doc_id(self):
        indexed_columns = {
            frozenset(col.name for col in idx.columns)
            for idx in BrainEdge.__table__.indexes
        }
        assert frozenset({"source_doc_id"}) in indexed_columns
        assert frozenset({"target_doc_id"}) in indexed_columns


class TestDefaults:
    """Column-level defaults, applied by SQLAlchemy on flush/create."""

    def test_kind_defaults_to_related(self, repo):
        edge = _make_brain_edge()
        assert edge.kind is None  # unset until the column default applies on flush
        created = repo.create(edge)
        assert created.kind == "related"

    def test_kind_can_be_overridden(self, repo):
        edge = _make_brain_edge(kind="mentions")
        created = repo.create(edge)
        assert created.kind == "mentions"


class TestRoundTrip:
    """Instantiation persists and reads back through GenericRepository."""

    def test_create_assigns_uuid_id(self, repo):
        edge = _make_brain_edge()
        created = repo.create(edge)
        assert isinstance(created.id, uuid.UUID)

    def test_round_trip_preserves_resolved_edge(self, repo):
        edge = _make_brain_edge()
        repo.create(edge)
        fetched = repo.get(edge.id)
        assert fetched is not None
        assert fetched.source_node_id == "brain:alpha"
        assert fetched.source_doc_id == "alpha"
        assert fetched.to_ref == "beta"
        assert fetched.target_node_id == "brain:beta"
        assert fetched.target_doc_id == "beta"
        assert fetched.kind == "related"

    def test_round_trip_accepts_dangling_edge(self, repo):
        """A dangling edge (unresolvable to_ref) stores NULL target columns, never dropped."""
        edge = _make_brain_edge(
            to_ref="nonexistent",
            target_node_id=None,
            target_doc_id=None,
        )
        repo.create(edge)
        fetched = repo.get(edge.id)
        assert fetched is not None
        assert fetched.to_ref == "nonexistent"
        assert fetched.target_node_id is None
        assert fetched.target_doc_id is None

    def test_scope_round_trips(self, repo):
        edge = _make_brain_edge(scope="brain")
        repo.create(edge)
        fetched = repo.get(edge.id)
        assert fetched.scope == "brain"

    def test_scope_defaults_to_none(self, repo):
        edge = _make_brain_edge()
        repo.create(edge)
        fetched = repo.get(edge.id)
        assert fetched.scope is None

    def test_count_reflects_created_rows(self, repo):
        assert repo.count() == 0
        repo.create(_make_brain_edge())
        repo.create(_make_brain_edge(source_node_id="brain:gamma", to_ref="delta"))
        assert repo.count() == 2
