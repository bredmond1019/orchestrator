"""Unit tests for NodeConfig and WorkflowSchema in app/core/schema.py."""

import pytest
from pydantic import BaseModel

from core.nodes.base import Node
from core.schema import NodeConfig, WorkflowSchema
from core.task import TaskContext


# ---------------------------------------------------------------------------
# Stub helpers — minimal Node subclasses (satisfy the ABC only)
# ---------------------------------------------------------------------------


class StubNodeA(Node):
    """Minimal stub node for schema tests."""

    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context


class StubNodeB(Node):
    """Minimal stub node for schema tests."""

    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context


class StubNodeC(Node):
    """Minimal stub node for schema tests."""

    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context


class StubRouterNode(Node):
    """Minimal stub router node for schema tests."""

    def process(self, task_context: TaskContext) -> TaskContext:
        return task_context


class StubEventSchema(BaseModel):
    """Minimal event schema for WorkflowSchema tests."""

    action: str = "default"


# ---------------------------------------------------------------------------
# NodeConfig — defaults
# ---------------------------------------------------------------------------


class TestNodeConfigDefaults:
    def test_connections_defaults_to_empty_list(self):
        """NodeConfig.connections defaults to an empty list when not supplied."""
        config = NodeConfig(node=StubNodeA)
        assert config.connections == []

    def test_is_router_defaults_to_false(self):
        """NodeConfig.is_router defaults to False when not supplied."""
        config = NodeConfig(node=StubNodeA)
        assert config.is_router is False

    def test_description_defaults_to_none(self):
        """NodeConfig.description defaults to None when not supplied."""
        config = NodeConfig(node=StubNodeA)
        assert config.description is None

    def test_parallel_nodes_defaults_to_empty_list(self):
        """NodeConfig.parallel_nodes defaults to an empty list when not supplied."""
        config = NodeConfig(node=StubNodeA)
        assert config.parallel_nodes == [] or config.parallel_nodes is None


# ---------------------------------------------------------------------------
# NodeConfig — override values
# ---------------------------------------------------------------------------


class TestNodeConfigOverrides:
    def test_node_is_stored(self):
        """NodeConfig stores the supplied node class."""
        config = NodeConfig(node=StubNodeA)
        assert config.node is StubNodeA

    def test_connections_stored_correctly(self):
        """NodeConfig stores the supplied connections list."""
        config = NodeConfig(node=StubNodeA, connections=[StubNodeB, StubNodeC])
        assert config.connections == [StubNodeB, StubNodeC]

    def test_is_router_can_be_set_true(self):
        """NodeConfig.is_router can be overridden to True."""
        config = NodeConfig(node=StubRouterNode, is_router=True)
        assert config.is_router is True

    def test_description_stored(self):
        """NodeConfig.description is stored when provided."""
        config = NodeConfig(node=StubNodeA, description="Does something useful")
        assert config.description == "Does something useful"

    def test_parallel_nodes_stored(self):
        """NodeConfig.parallel_nodes stores the supplied list."""
        config = NodeConfig(
            node=StubNodeA, parallel_nodes=[StubNodeB, StubNodeC]
        )
        assert StubNodeB in config.parallel_nodes
        assert StubNodeC in config.parallel_nodes


# ---------------------------------------------------------------------------
# WorkflowSchema — basic construction
# ---------------------------------------------------------------------------


class TestWorkflowSchemaConstruction:
    def test_start_node_is_stored(self):
        """WorkflowSchema stores the supplied start node class."""
        schema = WorkflowSchema(
            start=StubNodeA,
            event_schema=StubEventSchema,
            nodes=[NodeConfig(node=StubNodeA)],
        )
        assert schema.start is StubNodeA

    def test_nodes_list_is_stored(self):
        """WorkflowSchema stores the full list of NodeConfig objects."""
        configs = [
            NodeConfig(node=StubNodeA, connections=[StubNodeB]),
            NodeConfig(node=StubNodeB),
        ]
        schema = WorkflowSchema(
            start=StubNodeA,
            event_schema=StubEventSchema,
            nodes=configs,
        )
        assert len(schema.nodes) == 2
        assert schema.nodes[0].node is StubNodeA
        assert schema.nodes[1].node is StubNodeB

    def test_event_schema_is_stored(self):
        """WorkflowSchema stores the event_schema class."""
        schema = WorkflowSchema(
            start=StubNodeA,
            event_schema=StubEventSchema,
            nodes=[NodeConfig(node=StubNodeA)],
        )
        assert schema.event_schema is StubEventSchema

    def test_description_defaults_to_none(self):
        """WorkflowSchema.description defaults to None."""
        schema = WorkflowSchema(
            start=StubNodeA,
            event_schema=StubEventSchema,
            nodes=[NodeConfig(node=StubNodeA)],
        )
        assert schema.description is None

    def test_description_can_be_set(self):
        """WorkflowSchema.description stores a provided string."""
        schema = WorkflowSchema(
            description="My test workflow",
            start=StubNodeA,
            event_schema=StubEventSchema,
            nodes=[NodeConfig(node=StubNodeA)],
        )
        assert schema.description == "My test workflow"

    def test_multi_node_linear_workflow(self):
        """WorkflowSchema can represent a three-node linear chain."""
        configs = [
            NodeConfig(node=StubNodeA, connections=[StubNodeB]),
            NodeConfig(node=StubNodeB, connections=[StubNodeC]),
            NodeConfig(node=StubNodeC),
        ]
        schema = WorkflowSchema(
            start=StubNodeA,
            event_schema=StubEventSchema,
            nodes=configs,
        )
        assert schema.start is StubNodeA
        assert len(schema.nodes) == 3
        assert schema.nodes[0].connections == [StubNodeB]
        assert schema.nodes[1].connections == [StubNodeC]
        assert schema.nodes[2].connections == []


# ---------------------------------------------------------------------------
# WorkflowSchema — router node flag
# ---------------------------------------------------------------------------


class TestWorkflowSchemaRouterFlag:
    def test_is_router_flag_stored_on_node_config(self):
        """A NodeConfig with is_router=True stores that flag correctly."""
        configs = [
            NodeConfig(node=StubNodeA, connections=[StubRouterNode]),
            NodeConfig(
                node=StubRouterNode,
                connections=[StubNodeB, StubNodeC],
                is_router=True,
            ),
            NodeConfig(node=StubNodeB),
            NodeConfig(node=StubNodeC),
        ]
        schema = WorkflowSchema(
            start=StubNodeA,
            event_schema=StubEventSchema,
            nodes=configs,
        )
        router_config = next(
            nc for nc in schema.nodes if nc.node is StubRouterNode
        )
        assert router_config.is_router is True

    def test_non_router_nodes_have_is_router_false(self):
        """Non-router nodes in the same workflow have is_router=False."""
        configs = [
            NodeConfig(node=StubNodeA, connections=[StubRouterNode]),
            NodeConfig(
                node=StubRouterNode,
                connections=[StubNodeB, StubNodeC],
                is_router=True,
            ),
            NodeConfig(node=StubNodeB),
            NodeConfig(node=StubNodeC),
        ]
        schema = WorkflowSchema(
            start=StubNodeA,
            event_schema=StubEventSchema,
            nodes=configs,
        )
        non_routers = [nc for nc in schema.nodes if nc.node is not StubRouterNode]
        for nc in non_routers:
            assert nc.is_router is False

    def test_router_can_have_multiple_connections(self):
        """A router node config can hold two or more connection targets."""
        router_config = NodeConfig(
            node=StubRouterNode,
            connections=[StubNodeA, StubNodeB, StubNodeC],
            is_router=True,
        )
        assert len(router_config.connections) == 3
