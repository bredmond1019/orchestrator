"""Eval slice runner with persistence and regression history (Bastion Program
Block OR.U, Task 4).

``run_slice`` is the primitive the offline eval CLI (``scripts/run_eval.py``,
Task 7) drives: it executes an ``EvalSlice`` (Task 4's ``evals.slice``)
against every model under test, applies the slice's bound scorer per case,
aggregates pass-rate by (domain, model), and persists one ``EvalRun`` row per
model plus one ``EvalResult`` row per case via ``GenericRepository``
(standing rule 7 — no raw session writes bypassing the repository).

``get_run_history`` and ``compare_runs`` are the regression-history
primitives: successive calls to ``run_slice`` for the same
(slice_name, model_name) accumulate a queryable history, and
``compare_runs`` computes the signed pass-rate delta the one-change
self-improvement gate (``evals.gate``, Task 6) builds on.
"""

import time

from database.eval_record import EvalResult, EvalRun
from database.repository import GenericRepository
from sqlalchemy.orm import Session

from evals.slice import EvalSlice, Executor


def _score_cases(
    eval_slice: EvalSlice,
    model_name: str,
    executor: Executor,
) -> tuple[list[tuple[str, object]], float]:
    """Score every case in ``eval_slice`` against ``model_name``.

    Returns ``(scored, duration_seconds)`` where ``scored`` is a list of
    ``(case_id, ScoreResult)`` pairs, in case order.
    """
    start = time.monotonic()
    scored: list[tuple[str, object]] = [
        (case.case_id, eval_slice.scorer(executor(case, model_name), case))
        for case in eval_slice.cases
    ]
    duration = time.monotonic() - start
    return scored, duration


def _persist_run(
    eval_slice: EvalSlice,
    model_name: str,
    scored: list[tuple[str, object]],
    duration: float,
    run_repo: GenericRepository,
    result_repo: GenericRepository,
) -> EvalRun:
    """Persist one aggregated ``EvalRun`` plus its per-case ``EvalResult`` rows."""
    case_count = len(scored)
    passed_count = sum(1 for _, result in scored if result.passed)
    pass_rate = passed_count / case_count if case_count else 0.0

    run = run_repo.create(
        EvalRun(
            slice_name=eval_slice.name,
            domain=eval_slice.domain,
            model_name=model_name,
            pass_rate=pass_rate,
            case_count=case_count,
            passed_count=passed_count,
            total_duration_seconds=duration,
        )
    )

    for case_id, score_result in scored:
        result_repo.create(
            EvalResult(
                run_id=run.id,
                case_id=case_id,
                scorer=eval_slice.scorer_name,
                passed=score_result.passed,
                score=score_result.score,
                detail=score_result.detail,
            )
        )

    return run


def run_slice(eval_slice: EvalSlice, session: Session, executor: Executor) -> list[EvalRun]:
    """Execute every case in ``eval_slice`` against every model under test.

    For each model in ``eval_slice.models``, calls ``executor(case, model_name)``
    to obtain that case's output, scores it with ``eval_slice.scorer``,
    aggregates pass-rate/case counts, and persists one ``EvalRun`` plus its
    per-case ``EvalResult`` rows via ``GenericRepository``.

    Args:
        eval_slice: the slice to execute (cases, scorer, models under test).
        session: an active SQLAlchemy session.
        executor: callable producing a model's output for one case, given
            ``(case, model_name)``. Injected so this module stays offline and
            unit-testable (tests use a stub; the CLI wires a real one).

    Returns:
        One ``EvalRun`` per model in ``eval_slice.models``, in that order.
        Each is already persisted (and so has an ``id`` and ``created_at``).
    """
    run_repo = GenericRepository(session, EvalRun)
    result_repo = GenericRepository(session, EvalResult)

    runs: list[EvalRun] = []
    for model_name in eval_slice.models:
        scored, duration = _score_cases(eval_slice, model_name, executor)
        runs.append(_persist_run(eval_slice, model_name, scored, duration, run_repo, result_repo))

    return runs


def get_run_history(session: Session, slice_name: str, model_name: str) -> list[EvalRun]:
    """Return every persisted run of ``slice_name`` against ``model_name``.

    Ordered chronologically by ``created_at`` so the first element is the
    earliest (baseline-eligible) run and the last is the most recent
    candidate — the ordering the one-change gate (``evals.gate``) relies on.
    """
    return (
        session.query(EvalRun)
        .filter_by(slice_name=slice_name, model_name=model_name)
        .order_by(EvalRun.created_at, EvalRun.id)
        .all()
    )


def compare_runs(baseline: EvalRun, candidate: EvalRun) -> float:
    """Return the signed pass-rate delta of ``candidate`` relative to ``baseline``.

    Positive means ``candidate`` improved over ``baseline``; negative means it
    regressed; zero means no change. This is the primitive
    ``evals.gate.gate_change`` (Task 6) compares against ``min_delta``.
    """
    return candidate.pass_rate - baseline.pass_rate
