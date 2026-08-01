"""Migration up/down test for the ``embedding_model`` column (OR.ticket.corpus-reconcile task 1).

Runs the real Alembic migration chain (base -> previous head -> this
migration -> downgrade one step) against a fresh, Docker-gated pgvector
container — never the ORM's own ``create_all`` (which would already carry the
column and mask a broken migration). Skips cleanly when Docker is
unavailable, mirroring ``tests/database/conftest.py::pgvector_engine``.
"""

from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

APP_DIR = Path(__file__).resolve().parents[2] / "app"


def _alembic_config(monkeypatch, connection_url: str) -> Config:
    """Build an Alembic Config pointed at ``connection_url`` via env vars.

    ``alembic/env.py`` always overwrites ``sqlalchemy.url`` from
    ``DatabaseUtils.get_connection_string()``, which reads these same env
    vars — so pointing them at the test container is the supported way to
    redirect Alembic without touching production code.
    """
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
class TestEmbeddingModelMigration:
    """Up/down assertions for revision a4b5c6d7e8f9 on a fresh container."""

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
            engine = create_engine(container.get_connection_url())
            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            engine.dispose()
            yield container
        finally:
            container.stop()

    def test_upgrade_adds_column_downgrade_removes_it(
        self, fresh_pg_container, monkeypatch
    ):
        # alembic/env.py calls logging.config.fileConfig(alembic.ini) on every
        # run, which reconfigures the *global* root logger (disabling
        # propagation) and breaks unrelated tests' caplog assertions later in
        # the same session. Neutralize it — we don't need Alembic's own
        # logging output here.
        monkeypatch.setattr("logging.config.fileConfig", lambda *a, **k: None)

        cfg = _alembic_config(monkeypatch, fresh_pg_container.get_connection_url())

        # Build the schema up to (and including) the previous head, so the
        # target migration runs against the real prior state, not a vacuum.
        command.upgrade(cfg, "f1a2b3c4d5e6")

        engine = create_engine(fresh_pg_container.get_connection_url())
        inspector = inspect(engine)

        def _has_column(table: str, column: str) -> bool:
            return any(c["name"] == column for c in inspector.get_columns(table))

        assert not _has_column("brain_documents", "embedding_model")
        assert not _has_column("content_chunks", "embedding_model")

        # Upgrade to this migration.
        command.upgrade(cfg, "a4b5c6d7e8f9")
        inspector = inspect(engine)
        assert _has_column("brain_documents", "embedding_model")
        assert _has_column("content_chunks", "embedding_model")

        # Downgrade removes both columns cleanly.
        command.downgrade(cfg, "f1a2b3c4d5e6")
        inspector = inspect(engine)
        assert not _has_column("brain_documents", "embedding_model")
        assert not _has_column("content_chunks", "embedding_model")

        engine.dispose()
