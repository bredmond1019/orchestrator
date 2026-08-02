"""Tests for the RetrievalQuery model (OR.K1 task 1): schema shape,
GenericRepository round-trip on SQLite, and the real Alembic migration
up/down against a Docker-gated pgvector container.
"""

import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest
from database.repository import GenericRepository
from database.retrieval_query import RetrievalQuery
from database.session import Base
from sqlalchemy import Boolean, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker

APP_DIR = Path(__file__).resolve().parents[2] / "app"


@pytest.fixture
def session():
    """Provide a fresh in-memory SQLite session with the retrieval_queries table."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[RetrievalQuery.__table__])
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture
def repo(session):
    """Return a GenericRepository bound to the RetrievalQuery model."""
    return GenericRepository(session, RetrievalQuery)


def _make_query(**overrides):
    """Build a fully-populated RetrievalQuery, allowing per-test overrides."""
    defaults = dict(
        query="what changed in OR.K2?",
        surface="cli",
        workspace_id="orchestrator",
        hybrid=True,
        via_mix={"semantic": 3, "keyword": 2},
        result_count=5,
        top_score=0.91,
        retrieval_confidence=0.82,
        abstained=False,
        top_doc_ids=["doc-1", "doc-2"],
        latency_ms=42,
    )
    defaults.update(overrides)
    return RetrievalQuery(**defaults)


class TestSchema:
    """The model declares the table name and every required column with its type."""

    def test_table_name(self):
        assert RetrievalQuery.__tablename__ == "retrieval_queries"

    def test_expected_columns_present(self):
        columns = set(RetrievalQuery.__table__.columns.keys())
        expected = {
            "id",
            "query",
            "surface",
            "workspace_id",
            "hybrid",
            "via_mix",
            "result_count",
            "top_score",
            "retrieval_confidence",
            "abstained",
            "top_doc_ids",
            "latency_ms",
            "created_at",
        }
        assert expected <= columns

    def test_id_is_primary_key(self):
        assert RetrievalQuery.__table__.columns["id"].primary_key is True

    def test_query_is_string_and_not_nullable(self):
        col = RetrievalQuery.__table__.columns["query"]
        assert isinstance(col.type, String)
        assert col.nullable is False

    def test_surface_is_string_not_nullable_with_default(self):
        col = RetrievalQuery.__table__.columns["surface"]
        assert isinstance(col.type, String)
        assert col.nullable is False
        assert col.default.arg == "unknown"

    def test_hybrid_is_boolean_not_nullable(self):
        col = RetrievalQuery.__table__.columns["hybrid"]
        assert isinstance(col.type, Boolean)
        assert col.nullable is False

    def test_result_count_is_integer_not_nullable(self):
        col = RetrievalQuery.__table__.columns["result_count"]
        assert isinstance(col.type, Integer)
        assert col.nullable is False

    def test_abstained_is_boolean_not_nullable(self):
        col = RetrievalQuery.__table__.columns["abstained"]
        assert isinstance(col.type, Boolean)
        assert col.nullable is False

    def test_top_score_is_nullable_float(self):
        col = RetrievalQuery.__table__.columns["top_score"]
        assert isinstance(col.type, Float)
        assert col.nullable is True

    def test_created_at_is_datetime_and_indexed(self):
        col = RetrievalQuery.__table__.columns["created_at"]
        assert isinstance(col.type, DateTime)
        assert col.index is True


class TestRoundTrip:
    """Instantiation persists and reads back through GenericRepository."""

    def test_create_assigns_uuid_id(self, repo):
        created = repo.create(_make_query())
        assert isinstance(created.id, uuid.UUID)

    def test_round_trip_preserves_scalar_fields(self, repo):
        q = _make_query(query="second query", surface="http", result_count=3)
        repo.create(q)
        fetched = repo.get(q.id)
        assert fetched is not None
        assert fetched.query == "second query"
        assert fetched.surface == "http"
        assert fetched.result_count == 3

    def test_round_trip_preserves_json_via_mix(self, repo):
        q = _make_query(via_mix={"exact-id": 1})
        repo.create(q)
        fetched = repo.get(q.id)
        assert fetched.via_mix == {"exact-id": 1}

    def test_round_trip_preserves_json_top_doc_ids(self, repo):
        q = _make_query(top_doc_ids=["a", "b", "c"])
        repo.create(q)
        fetched = repo.get(q.id)
        assert fetched.top_doc_ids == ["a", "b", "c"]

    def test_defaults_populate_id_and_created_at(self, repo):
        created = repo.create(_make_query())
        assert created.id is not None
        assert created.created_at is not None

    def test_abstained_query_round_trips(self, repo):
        q = _make_query(abstained=True, retrieval_confidence=0.2, result_count=0)
        repo.create(q)
        fetched = repo.get(q.id)
        assert fetched.abstained is True
        assert fetched.retrieval_confidence == 0.2

    def test_nullable_workspace_id_allows_none(self, repo):
        q = _make_query(workspace_id=None)
        repo.create(q)
        fetched = repo.get(q.id)
        assert fetched.workspace_id is None

    def test_count_reflects_created_rows(self, repo):
        assert repo.count() == 0
        repo.create(_make_query())
        repo.create(_make_query())
        assert repo.count() == 2


def _alembic_config(monkeypatch, connection_url: str):
    """Build an Alembic Config pointed at ``connection_url`` via env vars.

    ``alembic/env.py`` always overwrites ``sqlalchemy.url`` from
    ``DatabaseUtils.get_connection_string()``, which reads these same env
    vars — so pointing them at the test container is the supported way to
    redirect Alembic without touching production code.
    """
    from alembic.config import Config

    parsed = urlparse(connection_url)
    monkeypatch.setenv("DATABASE_HOST", parsed.hostname or "localhost")
    monkeypatch.setenv("DATABASE_PORT", str(parsed.port or 5432))
    monkeypatch.setenv("DATABASE_NAME", (parsed.path or "/postgres").lstrip("/"))
    monkeypatch.setenv("DATABASE_USER", parsed.username or "postgres")
    monkeypatch.setenv("DATABASE_PASSWORD", parsed.password or "postgres")

    cfg = Config(str(APP_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(APP_DIR / "alembic"))
    return cfg


@pytest.mark.integration
class TestRetrievalQueriesMigration:
    """Up/down assertions for revision b8c9d0e1f2a3 on a fresh container."""

    @pytest.fixture()
    def fresh_pg_container(self):
        try:
            from testcontainers.postgres import PostgresContainer
        except ImportError as exc:
            pytest.skip(f"testcontainers[postgres] is not installed: {exc}")

        try:
            container = PostgresContainer("pgvector/pgvector:pg16")
            container.start()
        except Exception as exc:  # noqa: BLE001 - any Docker-unavailable failure
            pytest.skip(f"Docker is unavailable, skipping migration test: {exc}")
            return

        try:
            from sqlalchemy import text

            engine = create_engine(container.get_connection_url())
            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            engine.dispose()
            yield container
        finally:
            container.stop()

    def test_upgrade_creates_table_downgrade_removes_it(
        self, fresh_pg_container, monkeypatch
    ):
        from alembic import command
        from sqlalchemy import inspect

        # alembic/env.py calls logging.config.fileConfig(alembic.ini) on every
        # run, which reconfigures the *global* root logger (disabling
        # propagation) and breaks unrelated tests' caplog assertions later in
        # the same session. Neutralize it — we don't need Alembic's own
        # logging output here.
        monkeypatch.setattr("logging.config.fileConfig", lambda *a, **k: None)

        cfg = _alembic_config(monkeypatch, fresh_pg_container.get_connection_url())

        # Build the schema up to (and including) the previous head, so the
        # target migration runs against the real prior state, not a vacuum.
        command.upgrade(cfg, "a4b5c6d7e8f9")

        engine = create_engine(fresh_pg_container.get_connection_url())
        inspector = inspect(engine)
        assert "retrieval_queries" not in inspector.get_table_names()

        # Upgrade to this migration.
        command.upgrade(cfg, "b8c9d0e1f2a3")
        inspector = inspect(engine)
        assert "retrieval_queries" in inspector.get_table_names()
        indexes = {ix["name"] for ix in inspector.get_indexes("retrieval_queries")}
        assert "ix_retrieval_queries_created_at" in indexes

        # Downgrade removes the table cleanly.
        command.downgrade(cfg, "a4b5c6d7e8f9")
        inspector = inspect(engine)
        assert "retrieval_queries" not in inspector.get_table_names()

        engine.dispose()
