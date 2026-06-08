"""Unit tests for WorkflowValidator in app/core/validate.py."""

import pytest
from pydantic import BaseModel

from core.nodes.base import Node
from core.schema import NodeConfig, WorkflowSchema
from core.task import TaskContext
from core.validate import WorkflowValidator


# ---------------------------------------------------------------------------
# Stub helpers — minimal Node subclasses (satisfy the ABC only)
# ---------------------------------------------------------------------------


class StubNodeA(Node):
    """Minimal stub node A for validator tests."""

    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context


class StubNodeB(Node):
    """Minimal stub node B for validator tests."""

    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context


class StubNodeC(Node):
    """Minimal stub node C for validator tests."""

    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context


class StubRouterNode(Node):
    """Minimal stub router node for validator tests."""

    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context


class StubEventSchema(BaseModel):
    """Minimal event schema for WorkflowSchema construction in validator tests."""

    action: str = "default"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_schema(start, nodes: list[NodeConfig]) -> WorkflowSchema:
    """Build a WorkflowSchema from raw node configs."""
    return WorkflowSchema(start=start, event_schema=StubEventSchema, nodes=nodes)


# ---------------------------------------------------------------------------
# validate() — valid linear workflow
# ---------------------------------------------------------------------------


class TestValidateLinearWorkflow:
    def test_linear_a_b_c_raises_no_error(self):
        """A → B → C; validate() completes without raising."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB, connections=[StubNodeC]),
                NodeConfig(node=StubNodeC),
            ],
        )
        validator = WorkflowValidator(schema)
        # Should not raise
        validator.validate()

    def test_single_node_raises_no_error(self):
        """A single node with no connections is a valid workflow."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[NodeConfig(node=StubNodeA)],
        )
        validator = WorkflowValidator(schema)
        validator.validate()

    def test_two_node_chain_raises_no_error(self):
        """A → B; validate() completes without raising."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB),
            ],
        )
        validator = WorkflowValidator(schema)
        validator.validate()


# ---------------------------------------------------------------------------
# validate() — cycle detection
# ---------------------------------------------------------------------------


class TestValidateCycleDetection:
    def test_direct_cycle_a_b_a_raises_value_error(self):
        """A → B → A (direct cycle) raises ValueError."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB, connections=[StubNodeA]),
            ],
        )
        validator = WorkflowValidator(schema)
        with pytest.raises(ValueError, match="cycle"):
            validator.validate()

    def test_self_loop_raises_value_error(self):
        """A → A (self-loop) raises ValueError containing 'cycle'."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeA]),
            ],
        )
        validator = WorkflowValidator(schema)
        with pytest.raises(ValueError, match="cycle"):
            validator.validate()

    def test_three_node_cycle_raises_value_error(self):
        """A → B → C → A (three-node cycle) raises ValueError."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB, connections=[StubNodeC]),
                NodeConfig(node=StubNodeC, connections=[StubNodeA]),
            ],
        )
        validator = WorkflowValidator(schema)
        with pytest.raises(ValueError, match="cycle"):
            validator.validate()


# ---------------------------------------------------------------------------
# validate() — unreachable nodes
# ---------------------------------------------------------------------------


class TestValidateUnreachableNodes:
    def test_unreachable_node_raises_value_error(self):
        """A → B declared; C declared but not reachable; raises ValueError."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB),
                NodeConfig(node=StubNodeC),  # not connected to anything
            ],
        )
        validator = WorkflowValidator(schema)
        with pytest.raises(ValueError, match="unreachable"):
            validator.validate()

    def test_error_message_names_unreachable_node(self):
        """ValueError message identifies the unreachable node class."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB),
                NodeConfig(node=StubNodeC),
            ],
        )
        validator = WorkflowValidator(schema)
        with pytest.raises(ValueError) as exc_info:
            validator.validate()
        assert "StubNodeC" in str(exc_info.value)


# ---------------------------------------------------------------------------
# validate() — connection cardinality rules
# ---------------------------------------------------------------------------


class TestValidateConnectionRules:
    def test_non_router_multiple_connections_raises_value_error(self):
        """Non-router node with connections=[B, C] raises ValueError."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(
                    node=StubNodeA,
                    connections=[StubNodeB, StubNodeC],
                    is_router=False,
                ),
                NodeConfig(node=StubNodeB),
                NodeConfig(node=StubNodeC),
            ],
        )
        validator = WorkflowValidator(schema)
        with pytest.raises(ValueError):
            validator.validate()

    def test_non_router_multiple_connections_error_names_node(self):
        """ValueError for multiple connections names the offending node."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(
                    node=StubNodeA,
                    connections=[StubNodeB, StubNodeC],
                    is_router=False,
                ),
                NodeConfig(node=StubNodeB),
                NodeConfig(node=StubNodeC),
            ],
        )
        validator = WorkflowValidator(schema)
        with pytest.raises(ValueError, match="StubNodeA"):
            validator.validate()

    def test_router_node_with_multiple_connections_raises_no_error(self):
        """Router node with connections=[B, C] and is_router=True passes validation."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubRouterNode]),
                NodeConfig(
                    node=StubRouterNode,
                    connections=[StubNodeB, StubNodeC],
                    is_router=True,
                ),
                NodeConfig(node=StubNodeB),
                NodeConfig(node=StubNodeC),
            ],
        )
        validator = WorkflowValidator(schema)
        # Should not raise — router is allowed multiple connections
        validator.validate()

    def test_non_router_single_connection_raises_no_error(self):
        """Non-router node with exactly one connection is valid."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB),
            ],
        )
        validator = WorkflowValidator(schema)
        validator.validate()

    def test_non_router_zero_connections_raises_no_error(self):
        """Non-router terminal node with no connections is valid."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB, connections=[]),
            ],
        )
        validator = WorkflowValidator(schema)
        validator.validate()


# ---------------------------------------------------------------------------
# _has_cycle() — called directly
# ---------------------------------------------------------------------------


class TestHasCycleDirect:
    def test_returns_true_for_direct_cycle(self):
        """_has_cycle() returns True when A → B → A."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB, connections=[StubNodeA]),
            ],
        )
        validator = WorkflowValidator(schema)
        assert validator._has_cycle() is True

    def test_returns_true_for_self_loop(self):
        """_has_cycle() returns True for a self-referencing node."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[NodeConfig(node=StubNodeA, connections=[StubNodeA])],
        )
        validator = WorkflowValidator(schema)
        assert validator._has_cycle() is True

    def test_returns_false_for_linear_chain(self):
        """_has_cycle() returns False for A → B → C (acyclic)."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB, connections=[StubNodeC]),
                NodeConfig(node=StubNodeC),
            ],
        )
        validator = WorkflowValidator(schema)
        assert validator._has_cycle() is False

    def test_returns_false_for_single_node(self):
        """_has_cycle() returns False when only one node with no connections."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[NodeConfig(node=StubNodeA)],
        )
        validator = WorkflowValidator(schema)
        assert validator._has_cycle() is False

    def test_returns_false_for_diamond_dag(self):
        """_has_cycle() returns False for a diamond shape A→B, A→C, B→D, C→D."""
        # A splits to B and C; both merge into D (a valid DAG)
        class StubNodeD(Node):
            def process(self, task_context: TaskContext) -> TaskContext:
                return task_context

        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(
                    node=StubNodeA,
                    connections=[StubNodeB, StubNodeC],
                    is_router=True,
                ),
                NodeConfig(node=StubNodeB, connections=[StubNodeD]),
                NodeConfig(node=StubNodeC, connections=[StubNodeD]),
                NodeConfig(node=StubNodeD),
            ],
        )
        validator = WorkflowValidator(schema)
        assert validator._has_cycle() is False


# ---------------------------------------------------------------------------
# _get_reachable_nodes() — called directly
# ---------------------------------------------------------------------------


class TestGetReachableNodesDirect:
    def test_linear_chain_all_reachable(self):
        """_get_reachable_nodes() returns all three nodes in A → B → C."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB, connections=[StubNodeC]),
                NodeConfig(node=StubNodeC),
            ],
        )
        validator = WorkflowValidator(schema)
        reachable = validator._get_reachable_nodes()
        assert StubNodeA in reachable
        assert StubNodeB in reachable
        assert StubNodeC in reachable

    def test_isolated_node_not_reachable(self):
        """_get_reachable_nodes() excludes a node not connected to start."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB),
                NodeConfig(node=StubNodeC),  # isolated
            ],
        )
        validator = WorkflowValidator(schema)
        reachable = validator._get_reachable_nodes()
        assert StubNodeA in reachable
        assert StubNodeB in reachable
        assert StubNodeC not in reachable

    def test_single_start_node_returns_set_of_one(self):
        """_get_reachable_nodes() returns {start} when only the start node exists."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[NodeConfig(node=StubNodeA)],
        )
        validator = WorkflowValidator(schema)
        reachable = validator._get_reachable_nodes()
        assert reachable == {StubNodeA}

    def test_router_branches_all_reachable(self):
        """_get_reachable_nodes() includes both branches of a router node."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubRouterNode]),
                NodeConfig(
                    node=StubRouterNode,
                    connections=[StubNodeB, StubNodeC],
                    is_router=True,
                ),
                NodeConfig(node=StubNodeB),
                NodeConfig(node=StubNodeC),
            ],
        )
        validator = WorkflowValidator(schema)
        reachable = validator._get_reachable_nodes()
        assert {StubNodeA, StubRouterNode, StubNodeB, StubNodeC} == reachable

    def test_returns_exact_expected_set(self):
        """_get_reachable_nodes() returns exactly the expected set, no extras."""
        schema = make_schema(
            start=StubNodeA,
            nodes=[
                NodeConfig(node=StubNodeA, connections=[StubNodeB]),
                NodeConfig(node=StubNodeB),
            ],
        )
        validator = WorkflowValidator(schema)
        reachable = validator._get_reachable_nodes()
        assert reachable == {StubNodeA, StubNodeB}
