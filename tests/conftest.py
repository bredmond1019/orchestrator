from pathlib import Path

import pytest
from database.session import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

TRANSCRIPT_FIXTURES = Path(__file__).parent / "fixtures" / "transcripts"


@pytest.fixture
def load_transcript():
    """Return a loader for real YouTube-transcript corpus fixtures.

    The files under ``tests/fixtures/transcripts/`` are real transcripts copied
    from the learn-ai corpus, so content_pipeline fetch/summarize tests can
    exercise realistic, large source text instead of short inline strings. They
    are vendored into this repo's test tree on purpose — no cross-repo path
    dependency.
    """

    def _load(name: str) -> str:
        return (TRANSCRIPT_FIXTURES / name).read_text(encoding="utf-8")

    return _load


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    # Some tables use PostgreSQL-specific types (e.g. ARRAY in brain_documents)
    # that SQLite cannot compile. Exclude them from the in-memory SQLite setup;
    # those models are tested separately against a real PostgreSQL connection.
    _POSTGRES_ONLY_TABLES = {"brain_documents"}
    sqlite_tables = [
        t
        for t in Base.metadata.sorted_tables
        if t.name not in _POSTGRES_ONLY_TABLES
    ]
    Base.metadata.create_all(engine, tables=sqlite_tables)
    yield engine
    Base.metadata.drop_all(engine, tables=sqlite_tables)


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
