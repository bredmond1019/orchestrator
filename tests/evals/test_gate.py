"""Tests for the one-change self-improvement gate (Bastion Program Block
OR.U, Task 6): keep-if-better / revert-if-worse against persisted fixture
runs.

Note: mirrors ``tests/evals/test_runner.py``'s pattern — the in-memory
``db_session`` engine is session-scoped and ``GenericRepository.create``
commits, so rows persist across tests. Every fixture slice gets a fresh,
uuid-suffixed ``name`` to keep each test's history isolated.
"""

import uuid

import pytest
from evals.gate import gate_change
from evals.runner import run_slice
from evals.scorers import ScoreResult
from evals.slice import EvalCase, EvalSlice


def _fixture_slice(name=None) -> EvalSlice:
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
        models=["model-a"],
    )


def _stub_executor(pass_map):
    """Build an executor whose output['ok'] is looked up per (model, case_id)."""

    def _executor(case, model_name):
        return {"ok": pass_map.get((model_name, case.case_id), True)}

    return _executor


def _run(eval_slice, db_session, pass_map):
    """Run the fixture slice once against the given pass/fail map, return the run."""
    (run,) = run_slice(eval_slice, db_session, _stub_executor(pass_map))
    return run


class TestGateChange:
    def test_better_candidate_keeps(self, db_session):
        eval_slice = _fixture_slice()
        # Baseline: 1/2 pass.
        _run(eval_slice, db_session, {("model-a", "case-1"): False})
        # Candidate: 2/2 pass.
        candidate = _run(eval_slice, db_session, {})

        decision = gate_change(db_session, eval_slice.name, "model-a")

        assert decision.decision == "keep"
        assert decision.candidate_run_id == candidate.id
        assert decision.delta == pytest.approx(0.5)
        assert decision.baseline_run_id is not None

    def test_worse_candidate_reverts(self, db_session):
        eval_slice = _fixture_slice()
        # Baseline: 2/2 pass.
        _run(eval_slice, db_session, {})
        # Candidate: 1/2 pass.
        candidate = _run(eval_slice, db_session, {("model-a", "case-1"): False})

        decision = gate_change(db_session, eval_slice.name, "model-a")

        assert decision.decision == "revert"
        assert decision.candidate_run_id == candidate.id
        assert decision.delta == pytest.approx(-0.5)

    def test_tie_keeps(self, db_session):
        eval_slice = _fixture_slice()
        _run(eval_slice, db_session, {("model-a", "case-1"): False})
        candidate = _run(eval_slice, db_session, {("model-a", "case-1"): False})

        decision = gate_change(db_session, eval_slice.name, "model-a")

        assert decision.decision == "keep"
        assert decision.delta == pytest.approx(0.0)
        assert decision.candidate_run_id == candidate.id

    def test_min_delta_flips_marginal_improvement_to_revert(self, db_session):
        eval_slice = _fixture_slice()
        # Baseline: 1/2 pass (0.5).
        _run(eval_slice, db_session, {("model-a", "case-1"): False})
        # Candidate: still 1/2 pass — no improvement at all under a positive
        # min_delta requirement of 0.1, should revert since delta (0.0) < 0.1.
        candidate = _run(eval_slice, db_session, {("model-a", "case-1"): False})

        decision = gate_change(db_session, eval_slice.name, "model-a", min_delta=0.1)

        assert decision.decision == "revert"
        assert decision.candidate_run_id == candidate.id
        assert decision.delta == pytest.approx(0.0)

    def test_no_baseline_first_run_keeps(self, db_session):
        eval_slice = _fixture_slice()
        candidate = _run(eval_slice, db_session, {})

        decision = gate_change(db_session, eval_slice.name, "model-a")

        assert decision.decision == "keep"
        assert decision.baseline_run_id is None
        assert decision.delta is None
        assert decision.candidate_run_id == candidate.id
        assert "no baseline" in decision.reason.lower()

    def test_explicit_baseline_run_id_is_used(self, db_session):
        eval_slice = _fixture_slice()
        first = _run(eval_slice, db_session, {("model-a", "case-1"): False})  # 0.5
        _run(eval_slice, db_session, {})  # 1.0 (would be the default baseline)
        candidate = _run(eval_slice, db_session, {("model-a", "case-1"): False})  # 0.5

        # Explicitly compare candidate against the very first run instead of
        # the default previous-run baseline.
        decision = gate_change(
            db_session, eval_slice.name, "model-a", baseline_run_id=first.id
        )

        assert decision.baseline_run_id == first.id
        assert decision.candidate_run_id == candidate.id
        assert decision.delta == pytest.approx(0.0)
        assert decision.decision == "keep"

    def test_unknown_slice_raises(self, db_session):
        with pytest.raises(ValueError, match="No runs found"):
            gate_change(db_session, "nonexistent-slice", "model-a")

    def test_unknown_baseline_run_id_raises(self, db_session):
        eval_slice = _fixture_slice()
        _run(eval_slice, db_session, {})

        with pytest.raises(ValueError, match="not found"):
            gate_change(
                db_session, eval_slice.name, "model-a", baseline_run_id=uuid.uuid4()
            )
