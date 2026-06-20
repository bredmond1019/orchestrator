"""Typed Pydantic response and request models for the API layer."""

from pydantic import BaseModel


class TaskAcceptedResponse(BaseModel):
    task_id: str
    message: str


class EventPayload(BaseModel):
    workflow_type: str
    data: dict


class WorkflowListResponse(BaseModel):
    workflows: list[str]


class WorkflowGraphResponse(BaseModel):
    nodes: list[str]
    edges: list[tuple[str, str]]
