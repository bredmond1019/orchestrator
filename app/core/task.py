"""
Task Context Module

This module defines the context object that gets passed between workflow nodes.
It maintains the state and metadata throughout workflow execution.
"""

from typing import Any

from pydantic import BaseModel, Field


class TaskContext(BaseModel):
    """Context container for workflow task execution.

    TaskContext maintains the state and results of a workflow's execution,
    tracking the original event, intermediate node results, and additional
    metadata throughout the processing flow.

    Attributes:
        event: The original event that triggered the workflow
        nodes: Dictionary storing results and state from each node's execution
        metadata: Dictionary storing workflow-level metadata and configuration

    Example:
        context = TaskContext(
            event=incoming_event,
            nodes={"AnalyzeNode": {"score": 0.95}},
            metadata={"priority": "high"}
        )
    """

    event: Any
    nodes: dict[str, Any] = Field(
        default_factory=dict,
        description="Stores results and state from each node's execution",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Stores workflow-level metadata and configuration",
    )

    def update_node(self, node_name: str, **kwargs):
        self.nodes[node_name] = {**self.nodes.get(node_name, {}), **kwargs}

    def get_node_output(self, node_name: str) -> Any:
        """Retrieve the output stored for a completed node.

        Raises a descriptive ``KeyError`` if the node has not run yet, naming
        the missing node and listing the nodes that have run so far.  Router
        nodes should use this helper instead of accessing
        ``task_context.nodes[name]`` directly so that mis-ordered workflows
        surface a clear error rather than a raw ``KeyError``.

        Args:
            node_name: The name of the node whose output is needed.

        Returns:
            The value stored under ``task_context.nodes[node_name]``.

        Raises:
            KeyError: If ``node_name`` is not found in ``self.nodes``.
        """
        if node_name not in self.nodes:
            completed = list(self.nodes.keys())  # pylint: disable=no-member
            raise KeyError(
                f"Router expected output from node '{node_name}', but it has not run. "
                f"Nodes completed so far: {completed}. "
                f"Check that '{node_name}' appears before the router in the WorkflowSchema."
            )
        return self.nodes[node_name]  # pylint: disable=no-member
