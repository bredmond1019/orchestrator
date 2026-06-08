import pytest
from sqlalchemy import Column, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from database.repository import GenericRepository

_TestBase = declarative_base()


class _SimpleModel(_TestBase):
    __tablename__ = "simple"
    id = Column(String(36), primary_key=True)
    name = Column(String(100))


@pytest.fixture(scope="module")
def _engine():
    engine = create_engine("sqlite:///:memory:")
    _TestBase.metadata.create_all(engine)
    yield engine
    _TestBase.metadata.drop_all(engine)


@pytest.fixture
def session(_engine):
    Session = sessionmaker(bind=_engine)
    s = Session()
    yield s
    s.rollback()
    s.close()


class TestExists:
    def test_returns_true_when_row_present(self, session):
        session.add(_SimpleModel(id="abc", name="alice"))
        session.commit()
        repo = GenericRepository(session, _SimpleModel)
        assert repo.exists(id="abc") is True

    def test_returns_false_when_no_row(self, session):
        repo = GenericRepository(session, _SimpleModel)
        assert repo.exists(id="does-not-exist") is False

    def test_no_attribute_error_raised(self, session):
        repo = GenericRepository(session, _SimpleModel)
        try:
            repo.exists(id="any")
        except AttributeError:
            pytest.fail("exists() raised AttributeError — SQLAlchemy 2.x regression")
