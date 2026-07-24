"""Typed Pydantic response and request models for the API layer."""

from datetime import datetime

from pydantic import BaseModel


class TaskAcceptedResponse(BaseModel):
    task_id: str
    event_id: str
    message: str


class EventStatusResponse(BaseModel):
    """Response body for `GET /events/{event_id}` — a read-only status poll.

    `status` is derived (see `api.event_status.derive_status`), never stored.
    """

    event_id: str
    workflow_type: str
    status: str
    created_at: datetime | None
    updated_at: datetime | None
    task_context: dict | None


class EventPayload(BaseModel):
    workflow_type: str
    data: dict


class WorkflowListResponse(BaseModel):
    workflows: list[str]


class WorkflowGraphResponse(BaseModel):
    nodes: list[str]
    edges: list[tuple[str, str]]
