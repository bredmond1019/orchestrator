
from pydantic import BaseModel, Field

from core.nodes.base import Node

"""
Workflow Schema Module

This module defines the schema classes used to configure workflow structures.
It provides a type-safe way to define node connections and workflow layouts
using Pydantic models.
"""


class NodeConfig(BaseModel):
    """Configuration model for workflow nodes.

    NodeConfig defines the structure and behavior of a single node within
    a workflow, including its connections to other nodes and routing properties.

    Attributes:
        node: The Node class to be instantiated
        connections: List of Node classes this node can connect to
        is_router: Flag indicating if this node performs routing logic
        description: Optional description of the node's purpose
        parallel_nodes: Optional list of Node classes that can run in parallel

    Example:
        config = NodeConfig(
            node=AnalyzeNode,
            connections=[RouterNode],
            is_router=False,
            description="Analyzes incoming requests"
            parallel_nodes=[FilterContentGuardrailNode, FilterSQLInjectionGuardrailNode]
        )
    """

    node: type[Node]
    connections: list[type[Node]] = Field(default_factory=list)
    is_router: bool = False
    description: str | None = None
    parallel_nodes: list[type[Node]] | None = Field(default_factory=list)


class WorkflowSchema(BaseModel):
    """Schema definition for a complete workflow.

    WorkflowSchema defines the overall structure of a processing workflow,
    including its entry point and all constituent nodes.

    Attributes:
        description: Optional description of the workflow's purpose
        event_schema: Pydantic model for validating incoming events
        start: The entry point Node class for the workflow
        nodes: List of NodeConfig objects defining the workflow structure

    Example:
        schema = WorkflowSchema(
            description="Support ticket processing workflow",
            start=AnalyzeNode,
            nodes=[
                NodeConfig(node=AnalyzeNode, connections=[RouterNode]),
                NodeConfig(node=RouterNode, connections=[ResponseNode, EscalateNode]),
            ]
        )
    """

    description: str | None = None
    event_schema: type[BaseModel]
    start: type[Node]
    nodes: list[NodeConfig]
