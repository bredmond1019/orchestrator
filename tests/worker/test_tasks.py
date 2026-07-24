"""Unit tests for the worker persistence wiring in app/worker/tasks.py.

These exercise the Phase 1d behaviour: the worker builds an ``on_progress``
closure that persists the live ``TaskContext`` and flushes at each node
boundary inside the existing transaction, and still performs the terminal
authoritative write via the repository. The framework itself stays
deployment-agnostic; only the worker knows persistence exists.
"""

import logging
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import worker.tasks as worker_tasks
from core.task import NodeRun, NodeStatus, TaskContext


class StubEvent:
    """Stand-in for a persisted ``Event`` row."""

    def __init__(self) -> None:
        self.workflow_type = "stub"
        self.data = {"action": "go"}
        self.task_context: dict | None = None


def _make_task_context(status: NodeStatus) -> TaskContext:
    """Build a TaskContext carrying a single node in the given status."""
    ctx = TaskContext.model_construct(event=None, nodes={}, metadata={})
    ctx.node_runs = {"NodeA": NodeRun(status=status)}
    return ctx


@pytest.fixture
def wired_worker(monkeypatch):
    """Patch the worker's collaborators and return the captured doubles."""
    session = MagicMock(name="session")

    def fake_db_session():
        yield session

    db_event = StubEvent()
    repository = MagicMock(name="repository")
    repository.get.return_value = db_event

    monkeypatch.setattr(worker_tasks, "db_session", fake_db_session)
    monkeypatch.setattr(
        worker_tasks, "GenericRepository", MagicMock(return_value=repository)
    )

    # Progress snapshots fired by the workflow as it advances, plus the
    # terminal context returned by run().
    running = _make_task_context(NodeStatus.RUNNING)
    success = _make_task_context(NodeStatus.SUCCESS)

    seen_callback = {}

    def fake_run(event, on_progress=None):
        seen_callback["fn"] = on_progress
        on_progress(running)
        on_progress(success)
        return success

    workflow = MagicMock(name="workflow")
    workflow.run.side_effect = fake_run

    registry = MagicMock(name="WorkflowRegistry")
    registry.__getitem__.return_value.value.return_value = workflow
    monkeypatch.setattr(worker_tasks, "WorkflowRegistry", registry)

    return {
        "session": session,
        "db_event": db_event,
        "repository": repository,
        "workflow": workflow,
        "seen_callback": seen_callback,
        "success": success,
    }


def test_progress_persisted_and_flushed_per_boundary(wired_worker):
    """on_progress writes the live context and flushes at each boundary."""
    worker_tasks.process_incoming_event("evt-1")

    session = wired_worker["session"]
    # Two boundary snapshots were emitted by the stub workflow.
    assert session.flush.call_count == 2


def test_on_progress_closure_is_injected_into_run(wired_worker):
    """The worker passes a callable on_progress to workflow.run()."""
    worker_tasks.process_incoming_event("evt-1")

    callback = wired_worker["seen_callback"]["fn"]
    assert callable(callback)


def test_terminal_authoritative_write(wired_worker):
    """The terminal state is written and persisted via repository.update."""
    worker_tasks.process_incoming_event("evt-1")

    db_event = wired_worker["db_event"]
    repository = wired_worker["repository"]
    expected = wired_worker["success"].model_dump(mode="json")

    # Final db_event.task_context reflects the terminal run state.
    assert db_event.task_context == expected
    repository.update.assert_called_once_with(obj=db_event)


def test_missing_event_raises(wired_worker):
    """A missing event id raises ValueError before any workflow runs."""
    wired_worker["repository"].get.return_value = None

    with pytest.raises(ValueError):
        worker_tasks.process_incoming_event("missing")

    wired_worker["workflow"].run.assert_not_called()


def test_successful_run_writes_no_failure_marker(wired_worker):
    """A run that completes without raising carries no metadata.failure key."""
    worker_tasks.process_incoming_event("evt-1")

    db_event = wired_worker["db_event"]
    metadata = db_event.task_context.get("metadata") or {}
    assert "failure" not in metadata


@pytest.fixture
def failing_worker(monkeypatch):
    """Like ``wired_worker``, but the workflow raises and ``db_session`` is
    modelled with the real commit-on-success/rollback-on-exception contract
    across independent sessions, so the rollback-survival guarantee for the
    failure marker can actually be exercised and asserted.
    """
    sessions: list[MagicMock] = []

    def fake_db_session():
        session = MagicMock(name=f"session{len(sessions)}")
        sessions.append(session)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    db_event = StubEvent()
    repository = MagicMock(name="repository")
    repository.get.return_value = db_event

    monkeypatch.setattr(worker_tasks, "db_session", fake_db_session)
    monkeypatch.setattr(
        worker_tasks, "GenericRepository", MagicMock(return_value=repository)
    )

    error = RuntimeError("boom")

    def fake_run(event, on_progress=None):
        raise error

    workflow = MagicMock(name="workflow")
    workflow.run.side_effect = fake_run

    registry = MagicMock(name="WorkflowRegistry")
    registry.__getitem__.return_value.value.return_value = workflow
    monkeypatch.setattr(worker_tasks, "WorkflowRegistry", registry)

    return {
        "sessions": sessions,
        "db_event": db_event,
        "repository": repository,
        "error": error,
    }


def test_raising_workflow_writes_failure_marker(failing_worker):
    """A raising workflow produces a readable metadata.failure marker."""
    with pytest.raises(RuntimeError, match="boom"):
        worker_tasks.process_incoming_event("evt-1")

    db_event = failing_worker["db_event"]
    marker = db_event.task_context["metadata"]["failure"]
    assert marker["failed"] is True
    assert marker["error"] == "RuntimeError: boom"
    # `at` is a parseable ISO-8601 timestamp.
    datetime.fromisoformat(marker["at"])


def test_original_exception_reraised_unchanged(failing_worker):
    """The original exception instance propagates unchanged (Celery still
    sees the failure)."""
    with pytest.raises(RuntimeError) as excinfo:
        worker_tasks.process_incoming_event("evt-1")

    assert excinfo.value is failing_worker["error"]


def test_failure_marker_survives_outer_rollback(failing_worker):
    """Rollback-survival regression test: the marker is written on a second,
    separately committed session even though the outer session rolled back."""
    with pytest.raises(RuntimeError):
        worker_tasks.process_incoming_event("evt-1")

    sessions = failing_worker["sessions"]
    assert len(sessions) == 2, "expected two independent db_session() opens"
    outer_session, fresh_session = sessions

    outer_session.rollback.assert_called_once()
    outer_session.commit.assert_not_called()

    fresh_session.commit.assert_called_once()
    fresh_session.rollback.assert_not_called()


def test_marker_write_failure_does_not_mask_original_exception(
    failing_worker, caplog
):
    """A failure in the marker write itself is logged, not raised, and the
    original exception still propagates."""
    failing_worker["repository"].update.side_effect = RuntimeError(
        "marker write failed"
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError, match="boom"):
            worker_tasks.process_incoming_event("evt-1")

    assert any(
        "failed to write failure marker" in record.message.lower()
        for record in caplog.records
    )
