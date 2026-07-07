"""Docker-gated pgvector integration fixtures.

Provides a session-scoped, real ``postgresql://`` engine backed by a pinned
``pgvector/pgvector:pg16`` Testcontainers container. The ``vector`` extension is
enabled and the ``brain_documents`` + ``content_chunks`` schema (the two models
the in-memory SQLite suite in ``tests/conftest.py`` cannot fully exercise) is
created against the real database.

Container startup only happens lazily, inside the ``pgvector_engine`` fixture,
so a plain collection pass (e.g. ``pytest -m "not integration"``) never spins
up Docker. When Docker is unavailable the fixture ``pytest.skip``s, which
skips every test that depends on it without affecting the rest of the suite.
The container is torn down at the end of the test session.
"""

from collections.abc import Generator

import pytest
from database.brain_document import BrainDocument
from database.content_chunk import ContentChunk
from database.session import Base
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

PGVECTOR_IMAGE = "pgvector/pgvector:pg16"


@pytest.fixture(scope="session")
def pgvector_engine() -> Generator:
    """Yield a live ``postgresql://`` engine with the pgvector schema applied.

    Starts a pinned ``pgvector/pgvector:pg16`` container via Testcontainers,
    enables the ``vector`` extension, then creates the ``brain_documents`` and
    ``content_chunks`` tables against the real Postgres database using the ORM
    metadata (the same models production code writes through). Skips cleanly
    when Docker is unavailable, and removes the container at session end.
    """
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        pytest.skip(f"testcontainers[postgres] is not installed: {exc}")

    try:
        container = PostgresContainer(PGVECTOR_IMAGE)
        container.start()
    except Exception as exc:  # noqa: BLE001 - any Docker-unavailable failure
        pytest.skip(f"Docker is unavailable, skipping pgvector integration suite: {exc}")
        return

    try:
        engine = create_engine(container.get_connection_url())

        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        tables = [BrainDocument.__table__, ContentChunk.__table__]
        Base.metadata.create_all(engine, tables=tables)

        yield engine

        Base.metadata.drop_all(engine, tables=tables)
        engine.dispose()
    finally:
        container.stop()


@pytest.fixture
def pgvector_session(pgvector_engine) -> Generator[Session, None, None]:
    """Provide a transactional session bound to the live pgvector engine.

    Each test runs inside its own transaction that is rolled back afterward,
    so rows inserted by one test never leak into the next.
    """
    connection = pgvector_engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(bind=connection)
    session = session_factory()

    yield session

    session.close()
    transaction.rollback()
    connection.close()
