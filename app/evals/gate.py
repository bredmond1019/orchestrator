"""One-change self-improvement gate: keep-if-better / revert-if-worse
(Bastion Program Block OR.U, Task 6).

``gate_change`` is the primitive the one-change self-improvement loop uses to
decide whether a candidate change should be kept or reverted. It loads the
baseline run (explicit ``baseline_run_id``, else the previous run in
``evals.runner.get_run_history``) and the latest candidate run for the given
``(slice_name, model_name)``, compares their pass-rates via
``evals.runner.compare_runs``, and returns a ``GateDecision``.

Rule: keep if ``candidate.pass_rate >= baseline.pass_rate + min_delta``;
otherwise revert. With the default ``min_delta=0.0`` a tie (no change, no
regression) keeps — a no-worse change is not reverted. A positive
``min_delta`` raises the bar: an improvement smaller than the threshold is
treated as not worth the change and reverted.

If there is no baseline to compare against (first-ever run of this slice and
model), the gate always keeps, with a reason explaining there was nothing to
compare against.
"""

from database.eval_record import EvalRun
from pydantic import BaseModel
from sqlalchemy.orm import Session

from evals.runner import compare_runs, get_run_history


class GateDecision(BaseModel):
    """Outcome of the one-change self-improvement gate.

    Attributes:
        decision: ``"keep"`` or ``"revert"``.
        baseline_run_id: id of the baseline run compared against, or ``None``
            if there was no baseline (first-ever run).
        candidate_run_id: id of the candidate run being judged.
        delta: signed pass-rate delta (``candidate - baseline``), or ``None``
            if there was no baseline.
        reason: human-readable explanation of the decision.
    """

    model_config = {"arbitrary_types_allowed": True}

    decision: str
    baseline_run_id: object | None
    candidate_run_id: object
    delta: float | None
    reason: str


def gate_change(
    session: Session,
    slice_name: str,
    model_name: str,
    baseline_run_id: object | None = None,
    min_delta: float = 0.0,
) -> GateDecision:
    """Decide keep-vs-revert for the latest run of ``(slice_name, model_name)``.

    Args:
        session: an active SQLAlchemy session.
        slice_name: the eval slice name (``EvalRun.slice_name``).
        model_name: the model under test (``EvalRun.model_name``).
        baseline_run_id: explicit baseline run id to compare against. If
            ``None``, the previous run in the slice/model's history is used
            (the second-to-last entry, since the last entry is the
            candidate).
        min_delta: minimum pass-rate improvement required to keep the
            candidate. Ties (``delta == 0.0``) always keep regardless of
            ``min_delta`` sign convention — the comparison is
            ``candidate.pass_rate >= baseline.pass_rate + min_delta``, so a
            ``min_delta`` of ``0.0`` keeps ties and only a strictly positive
            ``min_delta`` can flip a marginal improvement to a revert.

    Returns:
        A ``GateDecision`` describing keep/revert, the run ids involved, the
        delta, and a human-readable reason.

    Raises:
        ValueError: if there is no persisted run at all for
            ``(slice_name, model_name)`` (nothing to gate), or if
            ``baseline_run_id`` was given but does not match any run in this
            slice/model's history.
    """
    history = get_run_history(session, slice_name, model_name)
    if not history:
        raise ValueError(
            f"No runs found for slice={slice_name!r}, model={model_name!r}; "
            "nothing to gate."
        )

    candidate = history[-1]

    baseline = _resolve_baseline(history, baseline_run_id)

    if baseline is None:
        return GateDecision(
            decision="keep",
            baseline_run_id=None,
            candidate_run_id=candidate.id,
            delta=None,
            reason="No baseline run available (first-ever run) — keeping candidate.",
        )

    delta = compare_runs(baseline, candidate)

    if delta >= min_delta:
        decision = "keep"
        reason = (
            f"Candidate pass_rate {candidate.pass_rate:.4f} >= baseline "
            f"{baseline.pass_rate:.4f} + min_delta {min_delta:.4f} "
            f"(delta={delta:.4f}) — keeping."
        )
    else:
        decision = "revert"
        reason = (
            f"Candidate pass_rate {candidate.pass_rate:.4f} < baseline "
            f"{baseline.pass_rate:.4f} + min_delta {min_delta:.4f} "
            f"(delta={delta:.4f}) — reverting."
        )

    return GateDecision(
        decision=decision,
        baseline_run_id=baseline.id,
        candidate_run_id=candidate.id,
        delta=delta,
        reason=reason,
    )


def _resolve_baseline(
    history: list[EvalRun],
    baseline_run_id: object | None,
) -> EvalRun | None:
    """Resolve the baseline run from ``history`` given an optional explicit id.

    If ``baseline_run_id`` is given, it must match a run in ``history`` other
    than the last (candidate) entry. If ``baseline_run_id`` is ``None``, the
    second-to-last entry in ``history`` is used (``None`` if there is only
    one run, i.e. no baseline exists yet).
    """
    if baseline_run_id is not None:
        for run in history:
            if run.id == baseline_run_id:
                return run
        raise ValueError(
            f"baseline_run_id={baseline_run_id!r} not found in history for this "
            "slice/model."
        )

    if len(history) < 2:
        return None

    return history[-2]
