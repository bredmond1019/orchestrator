"""Tests for the EvalRun/EvalResult models: schema shape, GenericRepository
round-trip, and FK linkage between a run and its results."""

import uuid

import pytest
from database.eval_record import EvalResult, EvalRun
from database.repository import GenericRepository
from database.session import Base
from sqlalchemy import Boolean, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def session():
    """Provide a fresh in-memory SQLite session with the eval tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine, tables=[EvalRun.__table__, EvalResult.__table__]
    )
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture
def run_repo(session):
    """Return a GenericRepository bound to the EvalRun model."""
    return GenericRepository(session, EvalRun)


@pytest.fixture
def result_repo(session):
    """Return a GenericRepository bound to the EvalResult model."""
    return GenericRepository(session, EvalResult)


def _make_run(**overrides):
    """Build a fully-populated EvalRun, allowing per-test overrides."""
    defaults = dict(
        slice_name="coding",
        domain="coding",
        model_name="claude-sonnet",
        pass_rate=0.8,
        case_count=10,
        passed_count=8,
        total_cost=0.42,
        total_duration_seconds=12.5,
        meta={"note": "fixture run"},
    )
    defaults.update(overrides)
    return EvalRun(**defaults)


def _make_result(run_id, **overrides):
    """Build a fully-populated EvalResult tied to the given run_id."""
    defaults = dict(
        run_id=run_id,
        case_id="case-1",
        scorer="deterministic",
        passed=True,
        score=1.0,
        detail={"reason": "ok"},
    )
    defaults.update(overrides)
    return EvalResult(**defaults)


class TestSchema:
    """The models declare the table name and every required column with its type."""

    def test_eval_run_table_name(self):
        assert EvalRun.__tablename__ == "eval_runs"

    def test_eval_result_table_name(self):
        assert EvalResult.__tablename__ == "eval_results"

    def test_eval_run_expected_columns_present(self):
        columns = set(EvalRun.__table__.columns.keys())
        expected = {
            "id",
            "slice_name",
            "domain",
            "model_name",
            "pass_rate",
            "case_count",
            "passed_count",
            "total_cost",
            "total_duration_seconds",
            "meta",
            "created_at",
        }
        assert expected <= columns

    def test_eval_result_expected_columns_present(self):
        columns = set(EvalResult.__table__.columns.keys())
        expected = {
            "id",
            "run_id",
            "case_id",
            "scorer",
            "passed",
            "score",
            "detail",
            "created_at",
        }
        assert expected <= columns

    def test_eval_run_id_is_primary_key(self):
        assert EvalRun.__table__.columns["id"].primary_key is True

    def test_eval_result_run_id_is_foreign_key(self):
        fks = EvalResult.__table__.columns["run_id"].foreign_keys
        assert len(fks) == 1
        assert next(iter(fks)).target_fullname == "eval_runs.id"

    def test_pass_rate_is_float_column(self):
        assert isinstance(EvalRun.__table__.columns["pass_rate"].type, Float)

    def test_case_count_is_integer_column(self):
        assert isinstance(EvalRun.__table__.columns["case_count"].type, Integer)

    def test_passed_is_boolean_column(self):
        assert isinstance(EvalResult.__table__.columns["passed"].type, Boolean)

    def test_slice_name_is_string_and_not_nullable(self):
        col = EvalRun.__table__.columns["slice_name"]
        assert isinstance(col.type, String)
        assert col.nullable is False

    def test_created_at_is_datetime_column(self):
        assert isinstance(EvalRun.__table__.columns["created_at"].type, DateTime)


class TestRoundTrip:
    """Instantiation persists and reads back through GenericRepository."""

    def test_create_assigns_uuid_id(self, run_repo):
        run = _make_run()
        created = run_repo.create(run)
        assert isinstance(created.id, uuid.UUID)

    def test_round_trip_preserves_scalar_fields(self, run_repo):
        run = _make_run(model_name="gpt-5", pass_rate=0.95)
        run_repo.create(run)
        fetched = run_repo.get(run.id)
        assert fetched is not None
        assert fetched.model_name == "gpt-5"
        assert fetched.pass_rate == 0.95
        assert fetched.case_count == 10
        assert fetched.passed_count == 8

    def test_round_trip_preserves_json_meta(self, run_repo):
        run = _make_run(meta={"routing": "cheap"})
        run_repo.create(run)
        fetched = run_repo.get(run.id)
        assert fetched.meta == {"routing": "cheap"}

    def test_get_all_returns_all_runs(self, run_repo):
        run_repo.create(_make_run())
        run_repo.create(_make_run())
        assert len(run_repo.get_all()) == 2

    def test_result_round_trip_preserves_scalar_fields(self, run_repo, result_repo):
        run = run_repo.create(_make_run())
        result = _make_result(run.id, case_id="case-42", scorer="reference", passed=False)
        result_repo.create(result)
        fetched = result_repo.get(result.id)
        assert fetched is not None
        assert fetched.case_id == "case-42"
        assert fetched.scorer == "reference"
        assert fetched.passed is False

    def test_result_round_trip_preserves_json_detail(self, run_repo, result_repo):
        run = run_repo.create(_make_run())
        result = _make_result(run.id, detail={"missing_field": "title"})
        result_repo.create(result)
        fetched = result_repo.get(result.id)
        assert fetched.detail == {"missing_field": "title"}

    def test_fk_links_results_to_their_run(self, run_repo, result_repo, session):
        run = run_repo.create(_make_run())
        result_repo.create(_make_result(run.id, case_id="a"))
        result_repo.create(_make_result(run.id, case_id="b"))

        linked = (
            session.query(EvalResult)
            .filter_by(run_id=run.id)
            .all()
        )
        assert {r.case_id for r in linked} == {"a", "b"}
        assert all(r.run_id == run.id for r in linked)

    def test_defaults_populate_id_and_created_at(self, run_repo):
        run = run_repo.create(_make_run())
        assert run.id is not None
        assert run.created_at is not None

    def test_count_reflects_created_rows(self, run_repo):
        assert run_repo.count() == 0
        run_repo.create(_make_run())
        run_repo.create(_make_run())
        assert run_repo.count() == 2
