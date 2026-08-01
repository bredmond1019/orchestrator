import pytest
from database.session import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


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
