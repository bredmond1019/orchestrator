"""Tests for the eval slice runner: persistence, per-model aggregation, and
regression history (Bastion Program Block OR.U, Task 4).

Note: ``db_session`` (from ``tests/conftest.py``) is backed by a
session-scoped in-memory engine, and ``GenericRepository.create`` commits, so
rows persisted by one test remain visible to later tests sharing the engine.
Every fixture slice below gets a fresh, uuid-suffixed ``name`` so tests can't
see each other's rows through ``get_run_history``'s filter.
"""

import time
import uuid

import pytest
from database.eval_record import EvalResult, EvalRun
from evals.runner import compare_runs, get_run_history, run_slice
from evals.scorers import ScoreResult
from evals.slice import EvalCase, EvalSlice


def _fixture_slice(models=None, name=None) -> EvalSlice:
    """A tiny slice: 2 cases, deterministic-flavored stub scorer."""

    def stub_scorer(output, case):  # noqa: ANN001 - test stub
        del case
        return ScoreResult(passed=bool(output.get("ok")), score=1.0 if output.get("ok") else 0.0)

    return EvalSlice(
        name=name or f"fixture-slice-{uuid.uuid4().hex[:8]}",
        domain="coding",
        cases=[
            EvalCase(case_id="case-1", input={"n": 1}),
            EvalCase(case_id="case-2", input={"n": 2}),
        ],
        scorer=stub_scorer,
        scorer_name="stub",
        models=models or ["model-a"],
    )


def _stub_executor(pass_map):
    """Build an executor whose output['ok'] is looked up per (model, case_id)."""

    def _executor(case, model_name):
        return {"ok": pass_map.get((model_name, case.case_id), True)}

    return _executor


class TestRunSlice:
    def test_persists_one_run_per_model_with_correct_aggregation(self, db_session):
        eval_slice = _fixture_slice(models=["model-a", "model-b"])
        pass_map = {
            ("model-a", "case-1"): True,
            ("model-a", "case-2"): True,
            ("model-b", "case-1"): True,
            ("model-b", "case-2"): False,
        }
        executor = _stub_executor(pass_map)

        runs = run_slice(eval_slice, db_session, executor)

        assert len(runs) == 2
        by_model = {run.model_name: run for run in runs}

        run_a = by_model["model-a"]
        assert run_a.slice_name == eval_slice.name
        assert run_a.domain == "coding"
        assert run_a.case_count == 2
        assert run_a.passed_count == 2
        assert run_a.pass_rate == pytest.approx(1.0)

        run_b = by_model["model-b"]
        assert run_b.case_count == 2
        assert run_b.passed_count == 1
        assert run_b.pass_rate == pytest.approx(0.5)

        # Runs are actually persisted, not just returned in memory.
        persisted_runs = db_session.query(EvalRun).filter_by(slice_name=eval_slice.name).all()
        assert len(persisted_runs) == 2

    def test_persists_linked_eval_result_rows(self, db_session):
        eval_slice = _fixture_slice(models=["model-a"])
        executor = _stub_executor({})

        (run,) = run_slice(eval_slice, db_session, executor)

        results = (
            db_session.query(EvalResult).filter_by(run_id=run.id).order_by(EvalResult.case_id).all()
        )
        assert len(results) == 2
        assert {r.case_id for r in results} == {"case-1", "case-2"}
        assert all(r.scorer == "stub" for r in results)
        assert all(r.passed is True for r in results)

    def test_zero_cases_yields_zero_pass_rate(self, db_session):
        eval_slice = EvalSlice(
            name="empty-slice",
            domain="coding",
            cases=[],
            scorer=lambda output, case: ScoreResult(passed=True),
            models=["model-a"],
        )
        (run,) = run_slice(eval_slice, db_session, lambda case, model_name: {})

        assert run.case_count == 0
        assert run.passed_count == 0
        assert run.pass_rate == 0.0


class TestRegressionHistory:
    def test_get_run_history_returns_successive_runs_in_order(self, db_session):
        eval_slice = _fixture_slice(models=["model-a"])
        executor = _stub_executor({})

        run_slice(eval_slice, db_session, executor)
        # Force a distinguishable created_at ordering across successive runs.
        time.sleep(0.01)
        run_slice(eval_slice, db_session, executor)

        history = get_run_history(db_session, eval_slice.name, "model-a")

        assert len(history) == 2
        assert history[0].created_at <= history[1].created_at
        assert all(run.slice_name == eval_slice.name for run in history)
        assert all(run.model_name == "model-a" for run in history)

    def test_get_run_history_filters_by_slice_and_model(self, db_session):
        slice_a = _fixture_slice(models=["model-a"])
        slice_b = _fixture_slice(models=["model-b"])
        run_slice(slice_a, db_session, _stub_executor({}))
        run_slice(slice_b, db_session, _stub_executor({}))

        history_a = get_run_history(db_session, slice_a.name, "model-a")
        history_b = get_run_history(db_session, slice_b.name, "model-b")

        assert len(history_a) == 1
        assert history_a[0].model_name == "model-a"
        assert len(history_b) == 1
        assert history_b[0].model_name == "model-b"


class TestCompareRuns:
    def test_returns_signed_pass_rate_delta(self, db_session):
        eval_slice = _fixture_slice(models=["model-a"])

        (baseline,) = run_slice(
            eval_slice,
            db_session,
            _stub_executor({("model-a", "case-1"): False, ("model-a", "case-2"): False}),
        )
        (candidate,) = run_slice(eval_slice, db_session, _stub_executor({}))

        delta = compare_runs(baseline, candidate)

        assert delta == pytest.approx(candidate.pass_rate - baseline.pass_rate)
        assert delta > 0

    def test_regression_is_negative(self, db_session):
        eval_slice = _fixture_slice(models=["model-a"])

        (baseline,) = run_slice(eval_slice, db_session, _stub_executor({}))
        (candidate,) = run_slice(
            eval_slice,
            db_session,
            _stub_executor({("model-a", "case-1"): False}),
        )

        assert compare_runs(baseline, candidate) < 0
