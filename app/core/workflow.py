"""
Workflow Orchestration Module

This module implements the core workflow functionality.
It provides a flexible framework for defining and executing workflows with multiple
nodes and routing logic.
"""

import logging
from abc import ABC
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, ClassVar

from dotenv import load_dotenv

from core.nodes.base import Node
from core.nodes.router import BaseRouter
from core.schema import NodeConfig, WorkflowSchema
from core.task import NodeRun, NodeStatus, TaskContext
from core.validate import WorkflowValidator


class Workflow(ABC):
    """Abstract base class for defining processing workflows.

    The Workflow class provides a framework for creating processing workflows
    with multiple nodes and routing logic. Each workflow must define its structure
    using a WorkflowSchema.

    Attributes:
        workflow_schema: Class variable defining the workflow's structure and flow
        validator: Validates the workflow schema
        nodes: Dictionary mapping node classes to their instances

    Example:
        class SupportWorkflow(Workflow):
            workflow_schema = WorkflowSchema(
                start=AnalyzeNode,
                nodes=[
                    NodeConfig(node=AnalyzeNode, connections=[RouterNode]),
                    NodeConfig(node=RouterNode, connections=[ResponseNode]),
                ]
            )
    """

    workflow_schema: ClassVar[WorkflowSchema]

    def __init__(self):
        """Initializes the workflow by validating schema and creating nodes."""
        self.validator = WorkflowValidator(self.workflow_schema)
        self.validator.validate()
        self.nodes: dict[type[Node], NodeConfig] = self._initialize_nodes()
        load_dotenv()

    @contextmanager
    def node_context(self, node_name: str, task_context: TaskContext):
        """Context manager that logs node execution and stamps the run envelope.

        On entry the node's ``NodeRun`` is marked ``RUNNING`` with a UTC
        ``started_at``. On a clean exit it is marked ``SUCCESS`` with
        ``completed_at``. If the node raises, it is marked ``FAILED`` with the
        stringified ``error`` and ``completed_at`` before the exception
        re-propagates. The envelope is written entirely here by the framework,
        so individual nodes (and reference workflows) need no changes.

        Args:
            node_name: Name of the node being executed
            task_context: The live task context whose ``node_runs`` is stamped

        Yields:
            None

        Raises:
            Exception: Re-raises any exception that occurs during node execution
        """
        run = task_context.node_runs.setdefault(node_name, NodeRun())
        run.status = NodeStatus.RUNNING
        run.started_at = datetime.now(UTC).isoformat()
        logging.info("Starting node: %s", node_name)
        try:
            yield
        except Exception as e:
            run.status = NodeStatus.FAILED
            run.error = str(e)
            run.completed_at = datetime.now(UTC).isoformat()
            logging.error("Error in node %s: %s", node_name, str(e))
            raise
        else:
            run.status = NodeStatus.SUCCESS
            run.completed_at = datetime.now(UTC).isoformat()
        finally:
            logging.info("Finished node: %s", node_name)

    def _initialize_nodes(self) -> dict[type[Node], NodeConfig]:
        """Initializes all nodes defined in the workflow schema.

        Returns:
            Dictionary mapping node classes to their instances
        """
        nodes = {}
        for node_config in self.workflow_schema.nodes:
            nodes[node_config.node] = node_config
            for connected_node in node_config.connections:
                if connected_node not in nodes:
                    connected_node_config = NodeConfig(node=connected_node)
                    nodes[connected_node] = connected_node_config
        return nodes

    @staticmethod
    def _instantiate_node(node_class: type[Node]) -> Node:
        """Creates an instance of a node class.

        Args:
            node_class: The class of the node to instantiate

        Returns:
            An instance of the specified node class
        """
        return node_class()

    def run(
        self,
        event: Any,
        on_progress: Callable[[TaskContext], None] | None = None,
    ) -> TaskContext:
        """Executes the workflow for a given event.

        Args:
            event: The event to process through the workflow
            on_progress: Optional injected callback invoked with the live
                ``TaskContext`` once before the first node (with every node
                seeded ``PENDING``) and once after each node boundary. Default
                ``None`` is a no-op. The signature is intentionally broad — a
                single ``TaskContext`` argument — so a future publisher
                (e.g. push / pub-sub) can be layered in without changing the
                deployment-agnostic framework. No persistence or session code
                lives here; the caller owns where progress goes.

        Returns:
            TaskContext containing the results of workflow execution

        Raises:
            Exception: Any exception that occurs during workflow execution
        """
        task_context = TaskContext(event=event)

        # Parse the raw event to the Pydantic schema defined in the WorkflowSchema
        task_context.event = self.workflow_schema.event_schema(**event)

        task_context.metadata["nodes"] = self.nodes

        # Seed every node PENDING so a freshly-dispatched run shows the full DAG,
        # then emit the initial snapshot before any node executes.
        for node_class in self.nodes:
            task_context.node_runs.setdefault(node_class.__name__, NodeRun())  # pylint: disable=no-member
        if on_progress:
            on_progress(task_context)

        current_node_class = self.workflow_schema.start

        while current_node_class:
            current_node = self.nodes[current_node_class].node
            with self.node_context(current_node_class.__name__, task_context):
                task_context = current_node().process(task_context)

            if on_progress:
                on_progress(task_context)

            current_node_class = self._get_next_node_class(
                current_node_class, task_context
            )
        task_context.metadata.pop("nodes")
        return task_context

    def _get_next_node_class(
        self, current_node_class: type[Node], task_context: TaskContext
    ) -> type[Node] | None:
        """Determines the next node to execute in the workflow.

        Args:
            current_node_class: The class of the current node
            task_context: The current task context

        Returns:
            The class of the next node to execute, or None if at the end
        """
        node_config = next(
            (nc for nc in self.workflow_schema.nodes if nc.node == current_node_class),
            None,
        )

        if not node_config or not node_config.connections:
            return None

        if node_config.is_router:
            router: BaseRouter = self.nodes[current_node_class].node()
            return self._handle_router(router, task_context)

        return node_config.connections[0]

    def _handle_router(
        self, router: BaseRouter, task_context: TaskContext
    ) -> type[Node] | None:
        """Handles routing logic for router nodes.

        Args:
            router: The router node instance
            task_context: The current task context

        Returns:
            The class of the next node to execute, or None if at the end
        """
        next_node = router.route(task_context)
        return next_node.__class__ if next_node else None
