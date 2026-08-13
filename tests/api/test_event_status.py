"""Unit tests for `app.api.event_status.derive_status`."""

from app.api.event_status import EventStatus, derive_status


def _node_runs(*statuses: str) -> dict:
    return {f"Node{i}": {"status": status} for i, status in enumerate(statuses)}


def test_queued_when_task_context_is_none():
    assert derive_status(None) == EventStatus.QUEUED


def test_queued_when_task_context_is_empty_dict():
    assert derive_status({}) == EventStatus.QUEUED


def test_running_when_task_context_present_but_no_node_runs():
    # Written by a persist_progress flush before any node has started.
    assert derive_status({"event": {}, "nodes": {}, "metadata": {}, "node_runs": {}}) == (
        EventStatus.RUNNING
    )


def test_running_when_any_node_run_non_terminal():
    task_context = {"metadata": {}, "node_runs": _node_runs("success", "running")}
    assert derive_status(task_context) == EventStatus.RUNNING


def test_running_when_any_node_run_pending():
    task_context = {"metadata": {}, "node_runs": _node_runs("pending")}
    assert derive_status(task_context) == EventStatus.RUNNING


def test_succeeded_when_all_node_runs_success():
    task_context = {"metadata": {}, "node_runs": _node_runs("success", "success")}
    assert derive_status(task_context) == EventStatus.SUCCEEDED


def test_failed_when_any_node_run_failed():
    task_context = {"metadata": {}, "node_runs": _node_runs("success", "failed")}
    assert derive_status(task_context) == EventStatus.FAILED


def test_failed_when_metadata_failure_flag_set():
    task_context = {
        "metadata": {"failure": {"failed": True, "error": "ValueError: boom", "at": "2026-07-24T00:00:00Z"}},
        "node_runs": _node_runs("success", "success"),
    }
    assert derive_status(task_context) == EventStatus.FAILED


def test_cancelled_when_metadata_cancellation_flag_set():
    task_context = {
        "metadata": {"cancellation": {"cancelled": True, "at": "2026-07-24T00:00:00Z"}},
        "node_runs": _node_runs("success"),
    }
    assert derive_status(task_context) == EventStatus.CANCELLED


def test_halted_when_metadata_budget_halted_flag_set():
    task_context = {
        "metadata": {"budget": {"halted": True, "reason": {"cap": "max_cost_usd", "spent": 1, "limit": 1}}},
        "node_runs": {},
    }
    assert derive_status(task_context) == EventStatus.HALTED


def test_precedence_cancelled_beats_running_node():
    # A cancelled run also carries a non-terminal node — asserts `cancelled`, not `running`.
    task_context = {
        "metadata": {"cancellation": {"cancelled": True, "at": "2026-07-24T00:00:00Z"}},
        "node_runs": _node_runs("pending", "running"),
    }
    assert derive_status(task_context) == EventStatus.CANCELLED


def test_precedence_halted_beats_running_node():
    task_context = {
        "metadata": {"budget": {"halted": True, "reason": {}}},
        "node_runs": _node_runs("pending"),
    }
    assert derive_status(task_context) == EventStatus.HALTED


def test_precedence_failure_flag_beats_all_success_nodes():
    # metadata.failure.failed is set but every node is success -> failed.
    task_context = {
        "metadata": {"failure": {"failed": True, "error": "RuntimeError: oops", "at": "2026-07-24T00:00:00Z"}},
        "node_runs": _node_runs("success", "success"),
    }
    assert derive_status(task_context) == EventStatus.FAILED


def test_precedence_cancelled_beats_failure_flag():
    task_context = {
        "metadata": {
            "cancellation": {"cancelled": True, "at": "2026-07-24T00:00:00Z"},
            "failure": {"failed": True, "error": "RuntimeError: oops", "at": "2026-07-24T00:00:00Z"},
        },
        "node_runs": {},
    }
    assert derive_status(task_context) == EventStatus.CANCELLED


class TestDataContractSection4Agreement:
    """§4's active-run scan rule: rows whose `task_context.node_runs` values
    are not all terminal (`success`/`failed`) are active.

    Every case this rule calls active must derive to `running`; every case
    it calls inactive must not derive to `running`.
    """

    ACTIVE_CASES = [
        {"metadata": {}, "node_runs": {}},
        {"metadata": {}, "node_runs": _node_runs("pending")},
        {"metadata": {}, "node_runs": _node_runs("running")},
        {"metadata": {}, "node_runs": _node_runs("success", "pending")},
        {"metadata": {}, "node_runs": _node_runs("success", "running")},
    ]

    INACTIVE_CASES = [
        {"metadata": {}, "node_runs": _node_runs("success")},
        {"metadata": {}, "node_runs": _node_runs("success", "success")},
        {"metadata": {}, "node_runs": _node_runs("success", "failed")},
        {"metadata": {}, "node_runs": _node_runs("failed")},
    ]

    def test_active_cases_derive_to_running(self):
        for task_context in self.ACTIVE_CASES:
            assert derive_status(task_context) == EventStatus.RUNNING, task_context

    def test_inactive_cases_do_not_derive_to_running(self):
        for task_context in self.INACTIVE_CASES:
            assert derive_status(task_context) != EventStatus.RUNNING, task_context


# --------------------------------------------------------------------------
# metadata.completion — the untaken-branch case
# --------------------------------------------------------------------------
#
# `Workflow.run` seeds EVERY node in the DAG `pending` before the walk starts,
# so a branch the router never took is still `pending` when the run finishes
# and is indistinguishable by node status alone from work that has not started.
# The live symptom: an answered DOCUMENT_QA run left `AbstainNode` pending and
# reported `running` forever, so the cockpit's spinner never stopped on a query
# that had in fact produced a complete answer.


def test_succeeded_when_completion_marker_set_despite_pending_branch():
    task_context = {
        "metadata": {"completion": {"completed": True}},
        "node_runs": _node_runs("success", "success", "pending"),
    }
    assert derive_status(task_context) == EventStatus.SUCCEEDED


def test_running_when_pending_branch_but_no_completion_marker():
    # Same node_runs, no marker — a genuinely in-flight run must stay running.
    task_context = {
        "metadata": {},
        "node_runs": _node_runs("success", "success", "pending"),
    }
    assert derive_status(task_context) == EventStatus.RUNNING


def test_precedence_failure_beats_completion_marker():
    # A run can finish its walk and still have a failed node; failure wins.
    task_context = {
        "metadata": {"completion": {"completed": True}},
        "node_runs": _node_runs("success", "failed"),
    }
    assert derive_status(task_context) == EventStatus.FAILED


def test_precedence_cancelled_beats_completion_marker():
    task_context = {
        "metadata": {
            "completion": {"completed": True},
            "cancellation": {"cancelled": True, "at": "2026-08-13T00:00:00Z"},
        },
        "node_runs": _node_runs("success", "success"),
    }
    assert derive_status(task_context) == EventStatus.CANCELLED


def test_falsy_completion_marker_does_not_force_succeeded():
    task_context = {
        "metadata": {"completion": {"completed": False}},
        "node_runs": _node_runs("success", "pending"),
    }
    assert derive_status(task_context) == EventStatus.RUNNING
