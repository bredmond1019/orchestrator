"""Event submission endpoint — generic dispatcher over registered workflow schemas.

This module defines the primary FastAPI endpoint for event ingestion. It follows
the "accept-and-delegate" pattern:
1. Validate the incoming event against its registered workflow schema.
2. Persist the event to the database.
3. Queue an asynchronous Celery processing task.
4. Return a typed 202 Accepted response.

This pattern keeps the API responsive while allowing long-running processing.
"""

import json
import uuid
from http import HTTPStatus

from database.event import Event
from database.repository import GenericRepository
from database.session import db_session
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session
from starlette.responses import Response
from worker.config import celery_app

from api.event_status import derive_status
from api.models import EventPayload, EventStatusResponse, TaskAcceptedResponse
from api.schema_registry import SCHEMA_MAP
from api.security import require_api_key

router = APIRouter()


@router.post("/", status_code=HTTPStatus.ACCEPTED, dependencies=[Depends(require_api_key)])
def handle_event(
    payload: EventPayload,
    session: Session = Depends(db_session),
) -> Response:
    """Validate an incoming event against its workflow schema and enqueue it.

    Args:
        payload: Generic event envelope carrying ``workflow_type`` and ``data``.
        session: Database session injected by FastAPI dependency.

    Returns:
        Response: 202 Accepted with a typed ``TaskAcceptedResponse`` body.

    Raises:
        HTTPException: 422 for an unknown ``workflow_type`` or invalid ``data``.
    """
    schema_cls = SCHEMA_MAP.get(payload.workflow_type)
    if schema_cls is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown workflow_type: {payload.workflow_type!r}. "
                f"Valid types: {list(SCHEMA_MAP.keys())}"
            ),
        )

    try:
        schema_cls.model_validate(payload.data)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc

    event = Event(data=payload.data, workflow_type=payload.workflow_type)

    # Stage without committing; flush assigns event.id within the open transaction.
    # If send_task raises below, db_session rolls back automatically — no orphaned row.
    session.add(event)
    session.flush()

    task = celery_app.send_task("process_incoming_event", args=[str(event.id)])

    return Response(
        content=json.dumps(
            TaskAcceptedResponse(
                task_id=str(task.id),
                event_id=str(event.id),
                message=f"process_incoming_event started `{task.id}`",
            ).model_dump()
        ),
        status_code=HTTPStatus.ACCEPTED,
        media_type="application/json",
    )


@router.get("/{event_id}", dependencies=[Depends(require_api_key)])
def get_event(
    event_id: str,
    session: Session = Depends(db_session),
) -> EventStatusResponse:
    """Read back a previously submitted event with a derived run status.

    Read-only: no ``session.add``, no ``flush``, no ``commit``, and no
    mutation of ``task_context``.

    Args:
        event_id: The ``events.id`` to look up (a UUID string).
        session: Database session injected by FastAPI dependency.

    Returns:
        EventStatusResponse: the event's identity, workflow type, derived
        ``status``, timestamps, and raw ``task_context``.

    Raises:
        HTTPException: 404 for an unknown id, and for a malformed/non-UUID
            id (never surfaced as a 500).
    """
    try:
        parsed_id = uuid.UUID(event_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail=f"Event not found: {event_id}"
        ) from exc

    try:
        event = GenericRepository(session=session, model=Event).get(obj_id=parsed_id)
    except StatementError as exc:
        raise HTTPException(
            status_code=404, detail=f"Event not found: {event_id}"
        ) from exc

    if event is None:
        raise HTTPException(status_code=404, detail=f"Event not found: {event_id}")

    return EventStatusResponse(
        event_id=str(event.id),
        workflow_type=event.workflow_type,
        status=derive_status(event.task_context),
        created_at=event.created_at,
        updated_at=event.updated_at,
        task_context=event.task_context,
    )
