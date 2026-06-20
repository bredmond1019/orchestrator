"""Read-only workflow graph introspection endpoints."""

from core.nodes.base import Node
from fastapi import APIRouter, HTTPException
from workflows.workflow_registry import WorkflowRegistry

from api.models import WorkflowGraphResponse, WorkflowListResponse

router = APIRouter()


@router.get("/workflows", response_model=WorkflowListResponse)
def list_workflows() -> WorkflowListResponse:
    return WorkflowListResponse(workflows=[w.name for w in WorkflowRegistry])


@router.get("/workflows/{workflow_type}/graph", response_model=WorkflowGraphResponse)
def workflow_graph(workflow_type: str) -> WorkflowGraphResponse:
    try:
        workflow_cls = WorkflowRegistry[workflow_type].value
    except KeyError as e:
        raise HTTPException(
            status_code=404, detail=f"Unknown workflow_type: {workflow_type!r}"
        ) from e

    schema = workflow_cls.workflow_schema
    nodes: list[str] = []

    def _add(node_cls: type[Node]) -> None:
        name = node_cls.__name__
        if name not in nodes:
            nodes.append(name)

    _add(schema.start)
    edges: list[tuple[str, str]] = []
    for node_config in schema.nodes:
        _add(node_config.node)
        for connection in node_config.connections:
            _add(connection)
            edges.append((node_config.node.__name__, connection.__name__))

    return WorkflowGraphResponse(nodes=nodes, edges=edges)
