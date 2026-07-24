"""Pure derivation of a run's read-side status from its `task_context`.

This module is intentionally side-effect-free: no DB access, no I/O, and no
import from `api.endpoint` (or any other route module) — it exists so both
the `GET /events/{event_id}` response model and the test suite share one
source of truth for the status vocabulary and its derivation rule.

The `metadata.failure` / `metadata.cancellation` / `metadata.budget` keys
follow the run-level annotation precedent documented in
`docs/data-contract.md` §5; `NodeRun.status` (`pending|running|success|failed`)
is documented in §6 and is not widened by this module.
"""

from enum import StrEnum
from typing import Any


class EventStatus(StrEnum):
    """The read-side status vocabulary for `GET /events/{event_id}`.

    Distinct from (and derived from) `app.core.task.NodeStatus` — this is a
    run-level status, not a per-node one.
    """

    QUEUED = "queued"
    RUNNING = "running"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"
    HALTED = "halted"


_TERMINAL_NODE_STATUSES = {"success", "failed"}


def derive_status(task_context: dict[str, Any] | None) -> EventStatus:
    """Derive a run-level `EventStatus` from a `task_context` dict.

    Precedence (evaluated in this order so a cancelled/halted run is never
    mislabelled `running`):

    1. `queued` — `task_context` is `None` or empty.
    2. `cancelled` — `metadata.cancellation.cancelled` is truthy.
    3. `halted` — `metadata.budget.halted` is truthy.
    4. `failed` — `metadata.failure.failed` is truthy, or any `node_runs[*]`
       entry has `status == "failed"`.
    5. `running` — any `node_runs[*]` entry is non-terminal (`pending` or
       `running`).
    6. `succeeded` — every `node_runs[*]` entry is `success`.

    A `task_context` that is present but whose `node_runs` map is empty or
    absent derives to `running`: the row was written by a `persist_progress`
    flush before any node had started (and therefore before any `node_runs`
    entry existed), so it is an in-progress run, not a queued or terminal
    one.
    """
    if not task_context:
        return EventStatus.QUEUED

    metadata = task_context.get("metadata") or {}

    cancellation = metadata.get("cancellation") or {}
    if cancellation.get("cancelled"):
        return EventStatus.CANCELLED

    budget = metadata.get("budget") or {}
    if budget.get("halted"):
        return EventStatus.HALTED

    failure = metadata.get("failure") or {}
    node_runs = task_context.get("node_runs") or {}
    node_statuses = [run.get("status") for run in node_runs.values()]

    if failure.get("failed") or "failed" in node_statuses:
        return EventStatus.FAILED

    if not node_runs:
        return EventStatus.RUNNING

    if any(status not in _TERMINAL_NODE_STATUSES for status in node_statuses):
        return EventStatus.RUNNING

    if all(status == "success" for status in node_statuses):
        return EventStatus.SUCCEEDED

    return EventStatus.RUNNING
