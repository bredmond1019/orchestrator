"""Unit tests for Workflow.run() in app/core/workflow.py."""

import logging

import pytest
from pydantic import BaseModel

from core.nodes.base import Node
from core.nodes.router import BaseRouter, RouterNode
from core.schema import NodeConfig, WorkflowSchema
from core.task import TaskContext
from core.workflow import Workflow


# ---------------------------------------------------------------------------
# Shared event schema
# ---------------------------------------------------------------------------


class StubEventSchema(BaseModel):
    """Minimal Pydantic event schema for workflow tests."""

    action: str = "default"


# ---------------------------------------------------------------------------
# Linear workflow — stub nodes
# ---------------------------------------------------------------------------


class LinearNodeA(Node):
    """Records execution in task_context under key 'LinearNodeA'."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("LinearNodeA", ran=True)
        return task_context


class LinearNodeB(Node):
    """Records execution in task_context under key 'LinearNodeB'."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("LinearNodeB", ran=True)
        return task_context


class LinearNodeC(Node):
    """Records execution in task_context under key 'LinearNodeC'."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("LinearNodeC", ran=True)
        return task_context


class LinearWorkflow(Workflow):
    """Three-node linear workflow: LinearNodeA → LinearNodeB → LinearNodeC."""

    workflow_schema = WorkflowSchema(
        start=LinearNodeA,
        event_schema=StubEventSchema,
        nodes=[
            NodeConfig(node=LinearNodeA, connections=[LinearNodeB]),
            NodeConfig(node=LinearNodeB, connections=[LinearNodeC]),
            NodeConfig(node=LinearNodeC),
        ],
    )


# ---------------------------------------------------------------------------
# Router workflow — stub nodes
# ---------------------------------------------------------------------------


class RouterSourceNode(Node):
    """Stores route_to='branch_b' in context for the router to inspect."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("RouterSourceNode", route_to="branch_b")
        return task_context


class BranchNodeB(Node):
    """Records execution in task_context under key 'BranchNodeB'."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("BranchNodeB", ran=True)
        return task_context


class BranchNodeC(Node):
    """Records execution in task_context under key 'BranchNodeC'."""

    def process(self, task_context: TaskContext) -> TaskContext:
        task_context.update_node("BranchNodeC", ran=True)
        return task_context


class BranchBCondition(RouterNode):
    """Routes to BranchNodeB when RouterSourceNode output has route_to=='branch_b'."""

    def determine_next_node(self, task_context: TaskContext) -> Node | None:
        output = task_context.get_node_output("RouterSourceNode")
        if output.get("route_to") == "branch_b":
            return BranchNodeB()
        return None


class StubBranchRouter(BaseRouter):
    """Router: tries BranchBCondition first; falls back to BranchNodeC."""

    def __init__(self):
        self.routes = [BranchBCondition()]
        self.fallback = BranchNodeC()


class RouterWorkflow(Workflow):
    """Workflow with a branching router: RouterSourceNode → StubBranchRouter → [B | C]."""

    workflow_schema = WorkflowSchema(
        start=RouterSourceNode,
        event_schema=StubEventSchema,
        nodes=[
            NodeConfig(node=RouterSourceNode, connections=[StubBranchRouter]),
            NodeConfig(
                node=StubBranchRouter,
                connections=[BranchNodeB, BranchNodeC],
                is_router=True,
            ),
            NodeConfig(node=BranchNodeB),
            NodeConfig(node=BranchNodeC),
        ],
    )


# ---------------------------------------------------------------------------
# Exception-propagation — stub node and workflow
# ---------------------------------------------------------------------------


class FailingNode(Node):
    """Node that always raises RuntimeError."""

    def process(self, task_context: TaskContext) -> TaskContext:
        raise RuntimeError("Intentional test error")


class FailingWorkflow(Workflow):
    """Single-node workflow whose only node always fails."""

    workflow_schema = WorkflowSchema(
        start=FailingNode,
        event_schema=StubEventSchema,
        nodes=[NodeConfig(node=FailingNode)],
    )


# ---------------------------------------------------------------------------
# Tests: linear pipeline
# ---------------------------------------------------------------------------


class TestLinearPipeline:
    """Verify that all three nodes in a linear chain run and produce output."""

    def test_all_nodes_ran(self):
        """All three linear nodes record output in task_context.nodes."""
        ctx = LinearWorkflow().run({"action": "test"})
        assert "LinearNodeA" in ctx.nodes
        assert "LinearNodeB" in ctx.nodes
        assert "LinearNodeC" in ctx.nodes

    def test_node_outputs_are_correct(self):
        """Each node's stored output matches what its process() wrote."""
        ctx = LinearWorkflow().run({"action": "test"})
        assert ctx.nodes["LinearNodeA"] == {"ran": True}
        assert ctx.nodes["LinearNodeB"] == {"ran": True}
        assert ctx.nodes["LinearNodeC"] == {"ran": True}

    def test_node_execution_order_is_preserved(self):
        """Nodes are recorded in A → B → C dict-insertion order."""
        ctx = LinearWorkflow().run({"action": "test"})
        keys = list(ctx.nodes.keys())
        assert keys == ["LinearNodeA", "LinearNodeB", "LinearNodeC"]


# ---------------------------------------------------------------------------
# Tests: router workflow
# ---------------------------------------------------------------------------


class TestRouterWorkflow:
    """Verify that a router node directs execution to the correct branch."""

    def test_correct_branch_ran(self):
        """When condition matches 'branch_b', BranchNodeB output is present."""
        ctx = RouterWorkflow().run({"action": "test"})
        assert "BranchNodeB" in ctx.nodes

    def test_wrong_branch_did_not_run(self):
        """When condition matches 'branch_b', BranchNodeC does not run."""
        ctx = RouterWorkflow().run({"action": "test"})
        assert "BranchNodeC" not in ctx.nodes

    def test_router_output_records_routing_decision(self):
        """The router stores {'next_node': 'BranchNodeB'} in task_context.nodes."""
        ctx = RouterWorkflow().run({"action": "test"})
        assert "StubBranchRouter" in ctx.nodes
        assert ctx.nodes["StubBranchRouter"]["next_node"] == "BranchNodeB"

    def test_source_node_ran_before_router(self):
        """RouterSourceNode's output is present (it runs before the router)."""
        ctx = RouterWorkflow().run({"action": "test"})
        assert "RouterSourceNode" in ctx.nodes
        assert ctx.nodes["RouterSourceNode"]["route_to"] == "branch_b"


# ---------------------------------------------------------------------------
# Tests: event schema parsing
# ---------------------------------------------------------------------------


class TestEventSchemaParsing:
    """Verify that the raw event dict is parsed into the declared event_schema."""

    def test_event_is_pydantic_model_after_run(self):
        """task_context.event is a StubEventSchema instance after run() returns."""
        ctx = LinearWorkflow().run({"action": "ping"})
        assert isinstance(ctx.event, StubEventSchema)

    def test_event_field_value_is_correct(self):
        """Parsed event has the action value that was passed in the raw dict."""
        ctx = LinearWorkflow().run({"action": "ping"})
        assert ctx.event.action == "ping"

    def test_event_default_field_applies_when_omitted(self):
        """An omitted optional field takes the Pydantic default value."""
        ctx = LinearWorkflow().run({})
        assert ctx.event.action == "default"


# ---------------------------------------------------------------------------
# Tests: node_context logging
# ---------------------------------------------------------------------------


class TestNodeContextLogging:
    """Verify start and finish log lines are emitted by node_context()."""

    def test_start_log_emitted_for_each_node(self, caplog):
        """'Starting node: <name>' is logged at INFO for every node run."""
        with caplog.at_level(logging.INFO):
            LinearWorkflow().run({"action": "test"})
        assert "Starting node: LinearNodeA" in caplog.text
        assert "Starting node: LinearNodeB" in caplog.text
        assert "Starting node: LinearNodeC" in caplog.text

    def test_finish_log_emitted_for_each_node(self, caplog):
        """'Finished node: <name>' is logged at INFO for every node run."""
        with caplog.at_level(logging.INFO):
            LinearWorkflow().run({"action": "test"})
        assert "Finished node: LinearNodeA" in caplog.text
        assert "Finished node: LinearNodeB" in caplog.text
        assert "Finished node: LinearNodeC" in caplog.text

    def test_error_log_emitted_on_node_failure(self, caplog):
        """'Error in node <name>' is logged at ERROR when a node raises."""
        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError):
                FailingWorkflow().run({"action": "test"})
        assert "Error in node FailingNode" in caplog.text

    def test_finish_log_emitted_even_after_node_failure(self, caplog):
        """'Finished node: <name>' is still logged (finally block) after an error."""
        with caplog.at_level(logging.INFO):
            with pytest.raises(RuntimeError):
                FailingWorkflow().run({"action": "test"})
        assert "Finished node: FailingNode" in caplog.text


# ---------------------------------------------------------------------------
# Tests: exception propagation
# ---------------------------------------------------------------------------


class TestNodeExceptionPropagates:
    """Verify that exceptions raised inside nodes escape from run()."""

    def test_runtime_error_propagates_from_run(self):
        """RuntimeError raised inside a node propagates out of Workflow.run()."""
        with pytest.raises(RuntimeError, match="Intentional test error"):
            FailingWorkflow().run({"action": "test"})

    def test_exception_type_is_not_wrapped(self):
        """The propagated exception is exactly RuntimeError, not re-wrapped."""
        with pytest.raises(RuntimeError):
            FailingWorkflow().run({"action": "test"})


# ---------------------------------------------------------------------------
# Tests: metadata cleanup
# ---------------------------------------------------------------------------


class TestMetadataCleanup:
    """Verify that run() removes metadata['nodes'] when the workflow completes."""

    def test_nodes_key_absent_from_metadata_after_run(self):
        """task_context.metadata does not contain 'nodes' after run() returns."""
        ctx = LinearWorkflow().run({"action": "test"})
        assert "nodes" not in ctx.metadata

    def test_metadata_is_empty_after_stub_workflow(self):
        """Stub nodes add nothing to metadata; it is empty after run() cleans up."""
        ctx = LinearWorkflow().run({"action": "test"})
        assert ctx.metadata == {}
