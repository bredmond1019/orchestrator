"""Coding domain eval slice — Block Z's SDLC runs as the eval harness's first
domain (Bastion Program Block OR.U, Task 5).

A "record" here is the persisted per-run telemetry ``SDLCFlowWorkflow``
(``workflows/sdlc_flow_workflow.py``) actually produces: the relevant slice
of a serialized ``TaskContext`` (see ``core/task.py``), i.e. a
``{"nodes": {...}}`` mapping keyed by node class name, each node's own output
stored under a ``"result"`` key exactly as ``TaskContext.update_node``
writes it (standing rule 9). The two node outputs this slice reads:

- ``UpdateTaskStatusNode`` (falling back to ``LoadTaskStateNode`` for a spec
  that bailed before any task mutation): ``result`` is
  ``schemas.sdlc_schema.SDLCState.model_dump()`` — the authoritative,
  cumulative source for every task's ``status``/``attempt_count`` and the
  run's aggregate ``telemetry`` (see ``update_task_status_node.py``).
- ``ConsolidatedReviewNode``: ``result`` is
  ``{"verdict": str, "summary": str, "issues": list[str]}`` (see
  ``consolidated_review_node.py``). Because ``SDLCFlowWorkflow``'s task loop
  keys node output by node *name* only (not per task-id), a single run
  record only ever retains the *last* task iteration's review verdict —
  this is a real limitation of the current telemetry, not an artifact of
  this slice, and the ``review_pass_rate`` metric below documents it.

Three deterministic scorers compute the Block-Z metrics named in the block
contract, composed by ``coding_scorer`` into one ``ScoreResult`` per run
record (``evals.slice.EvalSlice`` binds exactly one scorer per slice):

- ``spec_shipped_pass_rate``: fraction of the spec's tasks that reached
  ``DONE`` (a task that hit ``MAJOR_BAIL`` is mutated to ``FAILED`` by
  ``UpdateTaskStatusNode`` and so is excluded, per the block contract's
  "tasks DONE without MAJOR_BAIL" phrasing).
- ``retry_rate``: fraction of tasks whose ``attempt_count > 1`` (i.e. that
  needed at least one retry before resolving).
- ``review_pass_rate``: 1.0 if the record's ``ConsolidatedReviewNode``
  verdict is ``PASS``, 0.0 for ``FAIL``/``PARTIAL``, ``None`` when the run
  never reached review (e.g. it bailed straight to ``WrapUpNode``).

The overall ``passed`` flag on ``coding_scorer``'s ``ScoreResult`` is the
primary block-contract criterion: every task reached ``DONE`` and none
failed (a clean run passes; a bailed run fails).
"""

from typing import Any

from schemas.sdlc_schema import SDLCReviewVerdict, SDLCState, SDLCTaskStatus

from evals.scorers import ScoreResult
from evals.slice import EvalCase, EvalSlice

CODING_DOMAIN = "coding"


def _extract_state(record: dict[str, Any]) -> SDLCState:
    """Pull the authoritative ``SDLCState`` out of a run record's node outputs.

    Prefers ``UpdateTaskStatusNode`` (the cumulative, mutated state written
    on every task-loop iteration); falls back to ``LoadTaskStateNode`` for a
    run that never completed a single task iteration.
    """
    nodes = record.get("nodes", {})
    if "UpdateTaskStatusNode" in nodes:
        state_dict = nodes["UpdateTaskStatusNode"]["result"]
    else:
        state_dict = nodes["LoadTaskStateNode"]["result"]
    return SDLCState.model_validate(state_dict)


def _extract_review_verdict(record: dict[str, Any]) -> str | None:
    """Return the record's ``ConsolidatedReviewNode`` verdict, if it ran."""
    nodes = record.get("nodes", {})
    review = nodes.get("ConsolidatedReviewNode")
    if review is None:
        return None
    return review["result"]["verdict"]


def spec_shipped_pass_rate_scorer(output: Any, case: EvalCase) -> ScoreResult:
    """Fraction of the spec's tasks that reached DONE (not MAJOR_BAIL/FAILED)."""
    del case
    state = _extract_state(output)
    tasks = state.tasks
    if not tasks:
        return ScoreResult(passed=False, score=0.0, detail={"reason": "no tasks in record"})

    done_count = sum(1 for task in tasks if task.status == SDLCTaskStatus.DONE)
    pass_rate = done_count / len(tasks)
    return ScoreResult(
        passed=pass_rate == 1.0,
        score=pass_rate,
        detail={"done_count": done_count, "task_count": len(tasks)},
    )


def retry_rate_scorer(output: Any, case: EvalCase) -> ScoreResult:
    """Fraction of tasks that needed at least one retry (attempt_count > 1)."""
    del case
    state = _extract_state(output)
    tasks = state.tasks
    if not tasks:
        return ScoreResult(passed=True, score=0.0, detail={"reason": "no tasks in record"})

    retried_count = sum(1 for task in tasks if task.attempt_count > 1)
    retry_rate = retried_count / len(tasks)
    # A retry is not itself a failure signal — "passed" reports whether any
    # retries were needed at all, purely informational alongside the score.
    return ScoreResult(
        passed=retried_count == 0,
        score=retry_rate,
        detail={"retried_count": retried_count, "task_count": len(tasks)},
    )


def review_pass_rate_scorer(output: Any, case: EvalCase) -> ScoreResult:
    """Whether the record's (last-reached) review verdict was PASS.

    Returns ``score=None`` when the run never reached review (e.g. it bailed
    before ``ConsolidatedReviewNode`` ran) — silently treating that as either
    a pass or a fail would misrepresent an unreached check.
    """
    del case
    verdict = _extract_review_verdict(output)
    if verdict is None:
        return ScoreResult(passed=True, score=None, detail={"reason": "review not reached"})

    passed = verdict == SDLCReviewVerdict.PASS.value
    return ScoreResult(passed=passed, score=1.0 if passed else 0.0, detail={"verdict": verdict})


def coding_scorer(output: Any, case: EvalCase) -> ScoreResult:
    """Composite Block-Z scorer: pass-rate, retry rate, and review-pass rate.

    ``passed`` follows the primary block-contract criterion — every task in
    the record reached DONE and none failed. The other two metrics
    (``retry_rate``, ``review_pass_rate``) are informational, surfaced in
    ``detail`` for the eval CLI's per-domain/per-model table (Task 7).
    """
    pass_rate_result = spec_shipped_pass_rate_scorer(output, case)
    retry_result = retry_rate_scorer(output, case)
    review_result = review_pass_rate_scorer(output, case)

    return ScoreResult(
        passed=pass_rate_result.passed,
        score=pass_rate_result.score,
        detail={
            "pass_rate": pass_rate_result.score,
            "retry_rate": retry_result.score,
            "review_pass_rate": review_result.score,
            **(pass_rate_result.detail or {}),
        },
    )


def build_coding_slice(
    records: list[dict[str, Any]],
    models: list[str] | None = None,
    name: str = "coding",
) -> EvalSlice:
    """Build the coding-domain ``EvalSlice`` from already-loaded run records.

    Each record becomes one ``EvalCase`` whose ``input`` *is* the record —
    this slice scores recorded telemetry rather than invoking a model, so an
    offline identity executor (``lambda case, model_name: case.input``) is
    what the runner/CLI should pair it with (Task 7).

    Args:
        records: already-loaded run records (see module docstring for the
            expected ``{"nodes": {...}}`` shape); kept as a plain argument
            (not a live query) so this stays offline and unit-testable.
        models: models under test to attribute these records to; defaults to
            a single ``"recorded"`` placeholder since this slice scores
            historical telemetry rather than live per-model executions.
        name: slice name, used as the regression-history key.
    """
    cases = [
        EvalCase(case_id=f"{name}-{index}", input=record)
        for index, record in enumerate(records)
    ]
    return EvalSlice(
        name=name,
        domain=CODING_DOMAIN,
        cases=cases,
        scorer=coding_scorer,
        scorer_name="coding",
        models=models or ["recorded"],
    )


def load_coding_records(session: Any, workflow_type: str = "SDLC_FLOW") -> list[dict[str, Any]]:
    """Load coding-domain run records from the ``events`` table for live use.

    Queries ``Event`` rows for ``workflow_type`` and returns each row's
    ``task_context`` JSON blob — the same ``{"nodes": {...}}`` shape
    ``build_coding_slice`` expects. Kept separate from ``build_coding_slice``
    so the slice builder itself never talks to a database (offline,
    unit-testable with fixtures; this loader is the only live-query seam).
    """
    from database.event import Event  # pylint: disable=import-outside-toplevel

    rows = session.query(Event).filter_by(workflow_type=workflow_type).all()
    return [row.task_context for row in rows if row.task_context is not None]
