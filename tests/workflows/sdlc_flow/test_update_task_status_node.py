"""Unit tests for UpdateTaskStatusNode."""

import pytest
from core.task import TaskContext
from schemas.sdlc_schema import SDLCFlowEventSchema, SDLCState, SDLCTask
from workflows.sdlc_flow_workflow_nodes.update_task_status_node import UpdateTaskStatusNode


def _make_state(n_tasks: int = 2) -> SDLCState:
    tasks = [
        SDLCTask(task_id=i, title=f"Task {i}", description=f"Desc {i}")
        for i in range(1, n_tasks + 1)
    ]
    return SDLCState(spec_slug="test-spec", tasks=tasks)


def _make_ctx(current_task_id: int, verdict: str, state: SDLCState) -> TaskContext:
    ctx = TaskContext(event=SDLCFlowEventSchema(spec_slug="test-spec"))
    ctx.nodes["LoadTaskStateNode"] = {"result": state.model_dump()}
    ctx.nodes["TaskQueueRouterNode"] = {"result": {"current_task_id": current_task_id}}
    ctx.nodes["TriageTaskNode"] = {"result": {"verdict": verdict}}
    return ctx


class TestUpdateTaskStatusNode:
    def test_status_pending_to_done(self):
        state = _make_state()
        ctx = _make_ctx(current_task_id=1, verdict="PASS", state=state)

        node = UpdateTaskStatusNode()
        result = node.process(ctx)

        assert result is ctx
        output = ctx.get_node_output("UpdateTaskStatusNode")["result"]
        updated = SDLCState.model_validate(output)
        task = next(t for t in updated.tasks if t.task_id == 1)
        assert task.status == "done"
        assert updated.telemetry.tasks_passed == 1
        assert updated.telemetry.tasks_failed == 0
        assert updated.telemetry.total_attempts == 1

    def test_status_pending_to_failed(self):
        state = _make_state()
        ctx = _make_ctx(current_task_id=2, verdict="MAJOR_BAIL", state=state)

        node = UpdateTaskStatusNode()
        node.process(ctx)

        output = ctx.get_node_output("UpdateTaskStatusNode")["result"]
        updated = SDLCState.model_validate(output)
        task = next(t for t in updated.tasks if t.task_id == 2)
        assert task.status == "failed"
        assert updated.telemetry.tasks_failed == 1
        assert updated.telemetry.tasks_passed == 0

    def test_attempt_count_incremented(self):
        state = _make_state()
        ctx = _make_ctx(current_task_id=1, verdict="RETRYABLE", state=state)

        node = UpdateTaskStatusNode()
        node.process(ctx)

        output = ctx.get_node_output("UpdateTaskStatusNode")["result"]
        updated = SDLCState.model_validate(output)
        task = next(t for t in updated.tasks if t.task_id == 1)
        assert task.attempt_count == 1
        assert task.status == "pending"
        assert updated.telemetry.total_attempts == 1
        assert updated.telemetry.tasks_passed == 0
        assert updated.telemetry.tasks_failed == 0

    def test_task_not_found_raises(self):
        state = _make_state()
        ctx = _make_ctx(current_task_id=999, verdict="PASS", state=state)

        node = UpdateTaskStatusNode()
        with pytest.raises(ValueError, match="999"):
            node.process(ctx)

    def test_telemetry_counters_correct(self):
        state = _make_state(n_tasks=3)
        ctx = _make_ctx(current_task_id=1, verdict="PASS", state=state)

        node = UpdateTaskStatusNode()
        node.process(ctx)

        # Second loop iteration: retry task 2, then bail on task 3.
        ctx.nodes["TaskQueueRouterNode"] = {"result": {"current_task_id": 2}}
        ctx.nodes["TriageTaskNode"] = {"result": {"verdict": "RETRYABLE"}}
        node.process(ctx)

        ctx.nodes["TaskQueueRouterNode"] = {"result": {"current_task_id": 3}}
        ctx.nodes["TriageTaskNode"] = {"result": {"verdict": "MAJOR_BAIL"}}
        node.process(ctx)

        output = ctx.get_node_output("UpdateTaskStatusNode")["result"]
        updated = SDLCState.model_validate(output)

        assert updated.telemetry.tasks_passed == 1
        assert updated.telemetry.tasks_failed == 1
        assert updated.telemetry.total_attempts == 3

        task_1 = next(t for t in updated.tasks if t.task_id == 1)
        task_2 = next(t for t in updated.tasks if t.task_id == 2)
        task_3 = next(t for t in updated.tasks if t.task_id == 3)
        assert task_1.status == "done"
        assert task_2.status == "pending"
        assert task_2.attempt_count == 1
        assert task_3.status == "failed"

    def test_unknown_verdict_raises(self):
        state = _make_state()
        ctx = _make_ctx(current_task_id=1, verdict="BOGUS", state=state)

        node = UpdateTaskStatusNode()
        with pytest.raises(ValueError, match="BOGUS"):
            node.process(ctx)
