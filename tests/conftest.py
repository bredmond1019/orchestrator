import pytest
from database.session import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def _disable_query_log(monkeypatch):
    """Force the OR.K1 retrieval query log off for the whole suite.

    `app/brain/query_log.py::log_retrieval` defaults to enabled (so
    production entry points log without extra configuration); this autouse
    fixture keeps the test suite inert by default so a plain `recall()` call
    in an unrelated test never writes a `retrieval_queries` row. Tests that
    actually exercise logging opt back in via the `enable_query_log`
    fixture (`tests/brain/conftest.py`).
    """
    monkeypatch.setenv("BRAIN_QUERY_LOG_ENABLED", "0")


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine("sqlite:///:memory:")
    # Some tables use PostgreSQL-specific types (e.g. ARRAY in brain_documents,
    # TSVECTOR in brain_documents and code_chunks) that SQLite cannot compile.
    # Exclude them from the in-memory SQLite setup; those models are tested
    # separately against a real PostgreSQL connection.
    _POSTGRES_ONLY_TABLES = {"brain_documents", "code_chunks"}
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
