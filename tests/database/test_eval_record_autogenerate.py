"""Autogenerate dry-run guard for the ``eval_runs``/``eval_results`` tables (OR.X2 task 2).

``app/database/eval_record.py`` outlives its Python consumer (``app/evals/``,
deleted under OR.X2) solely so ``alembic revision --autogenerate`` never
proposes dropping these tables out from under engine-rs, which now owns them
in the shared Postgres. This test proves that on a fresh container built up
to head: comparing the live schema against ``Base.metadata`` produces no
``remove_table`` diff for ``eval_runs``/``eval_results``.

Mirrors ``tests/database/test_migration_embedding_model.py``'s Docker-gated
testcontainers pattern — skips cleanly when Docker is unavailable.
"""

from pathlib import Path
from urllib.parse import urlparse

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from database.session import Base
from sqlalchemy import create_engine, text

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
class TestEvalRecordAutogenerateGuard:
    """Guards that eval_runs/eval_results never appear as autogenerate DROPs."""

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

    def test_autogenerate_proposes_no_drop_of_eval_tables(
        self, fresh_pg_container, monkeypatch
    ):
        # alembic/env.py calls logging.config.fileConfig(alembic.ini) on every
        # run, which reconfigures the *global* root logger (disabling
        # propagation) and breaks unrelated tests' caplog assertions later in
        # the same session. Neutralize it — we don't need Alembic's own
        # logging output here.
        monkeypatch.setattr("logging.config.fileConfig", lambda *a, **k: None)

        cfg = _alembic_config(monkeypatch, fresh_pg_container.get_connection_url())

        # Build the schema up to head via the real migration chain (includes
        # f6a7b8c9d0e1, which creates eval_runs/eval_results).
        command.upgrade(cfg, "head")

        engine = create_engine(fresh_pg_container.get_connection_url())
        with engine.connect() as conn:
            migration_ctx = MigrationContext.configure(conn)
            diffs = compare_metadata(migration_ctx, Base.metadata)
        engine.dispose()

        dropped_tables = {
            diff[1].name
            for diff in diffs
            if diff[0] == "remove_table"
        }
        assert "eval_runs" not in dropped_tables
        assert "eval_results" not in dropped_tables
