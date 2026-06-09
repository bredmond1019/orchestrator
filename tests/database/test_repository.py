"""Tests for GenericRepository: exists() SQLAlchemy 2.x fix and full CRUD suite."""

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from database.repository import GenericRepository

# ── fixtures used by TestExists (Bug-fix regression, step 2) ─────────────────

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
    """Regression tests for the SQLAlchemy 2.x exists() fix (Bug 1)."""

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

    def test_partial_key_match_returns_true(self, session):
        """exists() with a non-primary-key column returns True when a row matches."""
        session.add(_SimpleModel(id="partial-key-test", name="unique-name-xyz"))
        session.commit()
        repo = GenericRepository(session, _SimpleModel)
        assert repo.exists(name="unique-name-xyz") is True

    def test_returns_false_after_row_deleted(self, session):
        """exists() returns False once the matching row has been deleted."""
        session.add(_SimpleModel(id="gone-row", name="ephemeral"))
        session.commit()
        repo = GenericRepository(session, _SimpleModel)
        assert repo.exists(name="ephemeral") is True
        repo.delete("gone-row")
        assert repo.exists(name="ephemeral") is False


# ── CRUD test suite (Task 12) ─────────────────────────────────────────────────

_CrudBase = declarative_base()


class _CrudModel(_CrudBase):
    __tablename__ = "crud_items"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100))


@pytest.fixture
def crud_session():
    """Provide a fresh in-memory SQLite session for each test function."""
    engine = create_engine("sqlite:///:memory:")
    _CrudBase.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture
def crud_repo(crud_session):
    """Return a GenericRepository bound to the fresh CRUD session."""
    return GenericRepository(crud_session, _CrudModel)


class TestCreate:
    """create() commits the object and returns it with an assigned id."""

    def test_create_returns_object_with_id(self, crud_repo):
        obj = _CrudModel(name="alice")
        result = crud_repo.create(obj)
        assert result.id is not None

    def test_create_returns_object_with_correct_name(self, crud_repo):
        obj = _CrudModel(name="bob")
        result = crud_repo.create(obj)
        assert result.name == "bob"

    def test_create_persists_to_db(self, crud_repo, crud_session):
        crud_repo.create(_CrudModel(name="carol"))
        assert crud_session.query(_CrudModel).filter_by(name="carol").first() is not None


class TestGet:
    """get() returns the row by id, or None when absent."""

    def test_get_returns_object_for_existing_id(self, crud_repo, crud_session):
        obj = _CrudModel(name="diana")
        crud_session.add(obj)
        crud_session.commit()
        result = crud_repo.get(obj.id)
        assert result is not None
        assert result.name == "diana"

    def test_get_returns_none_for_missing_id(self, crud_repo):
        result = crud_repo.get(99999)
        assert result is None


class TestGetAll:
    """get_all() returns every row, or [] when the table is empty."""

    def test_get_all_returns_empty_list_for_empty_table(self, crud_repo):
        assert crud_repo.get_all() == []

    def test_get_all_returns_all_rows(self, crud_repo, crud_session):
        crud_session.add_all([_CrudModel(name="x"), _CrudModel(name="y")])
        crud_session.commit()
        result = crud_repo.get_all()
        assert len(result) == 2

    def test_get_all_contains_inserted_names(self, crud_repo, crud_session):
        crud_session.add_all([_CrudModel(name="foo"), _CrudModel(name="bar")])
        crud_session.commit()
        names = {row.name for row in crud_repo.get_all()}
        assert names == {"foo", "bar"}


class TestUpdate:
    """update() persists field changes to the database."""

    def test_update_persists_field_change(self, crud_repo, crud_session):
        obj = _CrudModel(name="original")
        crud_session.add(obj)
        crud_session.commit()
        obj.name = "updated"
        crud_repo.update(obj)
        result = crud_repo.get(obj.id)
        assert result.name == "updated"

    def test_update_returns_object(self, crud_repo, crud_session):
        obj = _CrudModel(name="before")
        crud_session.add(obj)
        crud_session.commit()
        obj.name = "after"
        returned = crud_repo.update(obj)
        assert returned is obj


class TestDelete:
    """delete() removes the row; no-ops silently for a missing id."""

    def test_delete_removes_row(self, crud_repo, crud_session):
        obj = _CrudModel(name="to-delete")
        crud_session.add(obj)
        crud_session.commit()
        obj_id = obj.id
        crud_repo.delete(obj_id)
        assert crud_repo.get(obj_id) is None

    def test_delete_noop_for_missing_id(self, crud_repo):
        """delete() on an absent id must not raise."""
        crud_repo.delete(99999)  # should not raise

    def test_delete_reduces_count(self, crud_repo, crud_session):
        obj = _CrudModel(name="shrink")
        crud_session.add(obj)
        crud_session.commit()
        before = crud_repo.count()
        crud_repo.delete(obj.id)
        assert crud_repo.count() == before - 1


class TestGetLatest:
    """get_latest(n) returns the n most recently inserted rows, newest first."""

    def test_get_latest_returns_n_most_recent(self, crud_repo, crud_session):
        for label in ["first", "second", "third"]:
            crud_session.add(_CrudModel(name=label))
        crud_session.commit()
        result = crud_repo.get_latest(2)
        assert len(result) == 2
        # Descending by autoincrement id — highest id (most recent) comes first
        assert result[0].name == "third"
        assert result[1].name == "second"

    def test_get_latest_default_returns_one(self, crud_repo, crud_session):
        crud_session.add(_CrudModel(name="only"))
        crud_session.commit()
        result = crud_repo.get_latest()
        assert len(result) == 1

    def test_get_latest_returns_empty_list_when_table_empty(self, crud_repo):
        assert crud_repo.get_latest(3) == []

    def test_get_latest_clamps_to_available_rows(self, crud_repo, crud_session):
        crud_session.add(_CrudModel(name="sole"))
        crud_session.commit()
        result = crud_repo.get_latest(100)
        assert len(result) == 1


class TestCount:
    """count() reflects the correct row count before and after inserts."""

    def test_count_returns_zero_for_empty_table(self, crud_repo):
        assert crud_repo.count() == 0

    def test_count_increments_after_each_insert(self, crud_repo, crud_session):
        assert crud_repo.count() == 0
        crud_session.add(_CrudModel(name="a"))
        crud_session.commit()
        assert crud_repo.count() == 1
        crud_session.add(_CrudModel(name="b"))
        crud_session.commit()
        assert crud_repo.count() == 2

    def test_count_decrements_after_delete(self, crud_repo, crud_session):
        obj = _CrudModel(name="temp")
        crud_session.add(obj)
        crud_session.commit()
        before = crud_repo.count()
        crud_repo.delete(obj.id)
        assert crud_repo.count() == before - 1


class TestExistsFull:
    """Comprehensive exists() tests using the CRUD model (extending TestExists)."""

    def test_exists_true_for_matching_row(self, crud_repo, crud_session):
        crud_session.add(_CrudModel(name="present"))
        crud_session.commit()
        assert crud_repo.exists(name="present") is True

    def test_exists_false_when_no_match(self, crud_repo):
        assert crud_repo.exists(name="phantom") is False

    def test_exists_true_for_partial_key_match(self, crud_repo, crud_session):
        """exists() with only the name column (not the PK) finds the row."""
        crud_session.add(_CrudModel(name="partial-match"))
        crud_session.commit()
        assert crud_repo.exists(name="partial-match") is True

    def test_exists_false_after_deletion(self, crud_repo, crud_session):
        obj = _CrudModel(name="delete-me")
        crud_session.add(obj)
        crud_session.commit()
        crud_repo.delete(obj.id)
        assert crud_repo.exists(name="delete-me") is False
