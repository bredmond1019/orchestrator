"""
Task Context Module

This module defines the context object that gets passed between workflow nodes.
It maintains the state and metadata throughout workflow execution.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_serializer


def to_jsonable(value: Any) -> Any:
    """Best-effort conversion of a node output to JSON-serializable data.

    The data contract requires whatever a node stores under
    ``TaskContext.nodes[name]`` to survive ``model_dump(mode="json")`` so any
    consumer (e.g. an observability reader) can parse it. Pydantic models —
    including ``output_type`` results returned by the LLM node base classes —
    are dumped to plain dicts; everything else (str, dict, list, scalars) is
    already JSON-serializable and passes through unchanged.
    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


class NodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class NodeRun(BaseModel):
    """Per-node execution envelope: status, timing, error, input, and usage.

    Parallel/additive to ``TaskContext.nodes`` — it never replaces node output,
    it records *how* each node ran. Written entirely by the framework (see
    ``Workflow.node_context`` and the LLM node base classes) so reference
    workflows stay frozen.

    ``input`` carries the prompt/messages a node sent (populated by the LLM
    node base classes); it remains ``None`` for non-LLM nodes unless an author
    sets it, and must be JSON-serializable. ``usage`` carries
    ``{input_tokens, output_tokens, model}`` for LLM nodes; it is ``None`` for
    non-LLM nodes. Per-node *output* lives in ``TaskContext.nodes[name]``.
    """

    status: NodeStatus = NodeStatus.PENDING
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    input: Any | None = None
    usage: dict | None = None


class TaskContext(BaseModel):
    """Context container for workflow task execution.

    TaskContext maintains the state and results of a workflow's execution,
    tracking the original event, intermediate node results, and additional
    metadata throughout the processing flow.

    Attributes:
        event: The original event that triggered the workflow
        nodes: Dictionary storing results and state from each node's execution
        metadata: Dictionary storing workflow-level metadata and configuration
        node_runs: Per-node execution envelope (status/timing/usage), keyed by
            node class name; a parallel, additive channel to ``nodes``

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
    node_runs: dict[str, NodeRun] = Field(
        default_factory=dict,
        description="Per-node execution envelope (status/timing/usage), keyed by node class name",
    )

    @field_serializer("metadata")
    def _serialize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Drop the transient runtime node registry from serialized output.

        During a run the framework stashes the workflow's node registry under
        ``metadata["nodes"]`` (a ``dict`` keyed by node *class*) so parallel
        nodes can resolve their config; it is popped when the run completes.
        Those class objects are not JSON-serializable, which would break a
        mid-run ``model_dump(mode="json")`` snapshot (the observability
        guarantee the worker relies on to persist progress at each boundary).
        Excluding the key here keeps ``TaskContext`` JSON-serializable at any
        point in the run without changing how nodes access the registry at
        runtime.
        """
        return {key: value for key, value in metadata.items() if key != "nodes"}

    def update_node(self, node_name: str, **kwargs):
        self.nodes[node_name] = {**self.nodes.get(node_name, {}), **kwargs}  # pylint: disable=no-member

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
