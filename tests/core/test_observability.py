"""Unit tests for incremental execution observability (node_runs, on_progress)."""

import pytest
from pydantic import BaseModel

from core.nodes.base import Node
from core.schema import NodeConfig, WorkflowSchema
from core.task import NodeStatus, TaskContext
from core.workflow import Workflow


# ---------------------------------------------------------------------------
# Shared event schema + stub nodes/workflows
# ---------------------------------------------------------------------------


class StubEventSchema(BaseModel):
    """Minimal Pydantic event schema for observability tests."""

    action: str = "default"


class StepNodeA(Node):
    """Records execution in task_context under key 'StepNodeA'."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("StepNodeA", ran=True)
        return task_context


class StepNodeB(Node):
    """Records execution in task_context under key 'StepNodeB'."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("StepNodeB", ran=True)
        return task_context


class TwoStepWorkflow(Workflow):
    """Two-node linear workflow: StepNodeA -> StepNodeB."""

    workflow_schema = WorkflowSchema(
        start=StepNodeA,
        event_schema=StubEventSchema,
        nodes=[
            NodeConfig(node=StepNodeA, connections=[StepNodeB]),
            NodeConfig(node=StepNodeB),
        ],
    )


class BoomNode(Node):
    """Node that always raises RuntimeError('boom')."""

    def process(self, task_context: TaskContext) -> TaskContext:
        raise RuntimeError("boom")


class BoomWorkflow(Workflow):
    """Single-node workflow whose only node always fails."""

    workflow_schema = WorkflowSchema(
        start=BoomNode,
        event_schema=StubEventSchema,
        nodes=[NodeConfig(node=BoomNode)],
    )


# ---------------------------------------------------------------------------
# 5.2 Happy-path status transitions
# ---------------------------------------------------------------------------


class TestHappyPathTransitions:
    """node_runs transitions PENDING -> RUNNING -> SUCCESS for clean runs."""

    def test_node_runs_reach_success(self):
        """Both nodes end SUCCESS with non-null started_at/completed_at."""
        ctx = TwoStepWorkflow().run({"action": "x"})
        for name in ("StepNodeA", "StepNodeB"):
            run = ctx.node_runs[name]
            assert run.status == NodeStatus.SUCCESS
            assert run.started_at is not None
            assert run.completed_at is not None
            assert run.error is None


# ---------------------------------------------------------------------------
# 5.3 Failure envelope + exception propagation
# ---------------------------------------------------------------------------


class TestFailureEnvelope:
    """A raising node yields FAILED + error + completed_at and still propagates."""

    def test_failed_node_records_error_and_propagates(self):
        """The FAILED envelope is observable via the live (seeded) context."""
        wf = BoomWorkflow()
        ctx_holder: dict[str, TaskContext] = {}

        def grab(ctx: TaskContext) -> None:
            ctx_holder["ctx"] = ctx

        with pytest.raises(RuntimeError, match="boom"):
            wf.run({"action": "x"}, on_progress=grab)

        # The seed snapshot fired before the first node with the same live
        # task_context the framework keeps mutating, so this is that object.
        ctx = ctx_holder["ctx"]
        run = ctx.node_runs["BoomNode"]
        assert run.status == NodeStatus.FAILED
        assert run.error is not None
        assert run.completed_at is not None


# ---------------------------------------------------------------------------
# 5.4 on_progress invocation count / order (spy)
# ---------------------------------------------------------------------------


class TestOnProgressSpy:
    """on_progress fires once before the first node and once per boundary."""

    def test_on_progress_called_once_before_first_node_and_per_boundary(self):
        """A 2-node workflow yields 3 snapshots: 1 seed + 2 boundaries."""
        calls: list[dict[str, NodeStatus]] = []

        TwoStepWorkflow().run(
            {"action": "x"},
            on_progress=lambda c: calls.append(
                {n: r.status for n, r in c.node_runs.items()}
            ),
        )

        assert len(calls) == 3
        # First snapshot: every node PENDING.
        assert all(s == NodeStatus.PENDING for s in calls[0].values())
        # Last snapshot: every node SUCCESS.
        assert all(s == NodeStatus.SUCCESS for s in calls[-1].values())


# ---------------------------------------------------------------------------
# 5.5 Backward compatibility (on_progress=None)
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    """Default path leaves behavior identical to today."""

    def test_default_on_progress_none_is_noop(self):
        """No callback: terminal cleanup + node-output contract are intact."""
        ctx = TwoStepWorkflow().run({"action": "x"})
        assert "nodes" not in ctx.metadata
        assert ctx.nodes["StepNodeA"] == {"ran": True}


# ---------------------------------------------------------------------------
# 5.6 Mid-run partial snapshot (the observability guarantee)
# ---------------------------------------------------------------------------


class TestMidRunSnapshot:
    """A mid-run model_dump shows a mix of SUCCESS and PENDING node_runs."""

    def test_mid_run_snapshot_is_partial(self):
        """After StepNodeA, StepNodeA is success while StepNodeB is pending."""
        snaps: list[dict] = []

        TwoStepWorkflow().run(
            {"action": "x"},
            on_progress=lambda c: snaps.append(c.model_dump(mode="json")),
        )

        # snaps[0] = seed; snaps[1] = after StepNodeA, before StepNodeB.
        mid = snaps[1]["node_runs"]
        assert mid["StepNodeA"]["status"] == "success"
        assert mid["StepNodeB"]["status"] == "pending"
