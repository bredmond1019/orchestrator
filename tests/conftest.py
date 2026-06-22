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
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()
