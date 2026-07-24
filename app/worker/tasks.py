import logging
from contextlib import contextmanager
from datetime import UTC, datetime

from core.task import TaskContext
from database.event import Event
from database.repository import GenericRepository
from database.session import db_session
from workflows.workflow_registry import WorkflowRegistry

from worker.config import celery_app

"""
Workflow Task Processing Module

This module handles asynchronous processing of workflow events using Celery.
It manages the lifecycle of event processing from database retrieval through
workflow execution and result storage.
"""


@celery_app.task(name="process_incoming_event")
def process_incoming_event(event_id: str):
    """Processes an incoming event through its designated workflow.

    This Celery task handles the asynchronous processing of events by:
    1. Retrieving the event from the database
    2. Determining the appropriate workflow
    3. Executing the workflow
    4. Storing the results

    If the workflow raises, a terminal ``metadata.failure`` marker is written
    for the run (see ``_write_failure_marker``) before the original exception
    is re-raised, so Celery still records the task failure.

    Args:
        event_id: Unique identifier of the event to process
        workflow_type: Type of workflow to use for processing the event
    """
    with contextmanager(db_session)() as session:
        # Initialize repository for database operations
        repository = GenericRepository(session=session, model=Event)

        # Retrieve event from database
        db_event = repository.get(obj_id=event_id)
        if db_event is None:
            raise ValueError(f"Event with id {event_id} not found")

        # Execute workflow, persisting node-level progress at each boundary.
        workflow = WorkflowRegistry[db_event.workflow_type].value()

        def persist_progress(task_context: TaskContext) -> None:
            # The worker (which already owns the session) is the only place that
            # knows persistence exists; the framework stays deployment-agnostic.
            db_event.task_context = task_context.model_dump(mode="json")
            session.flush()

        try:
            result_context = workflow.run(db_event.data, on_progress=persist_progress)
        except Exception as exc:
            _write_failure_marker(event_id, exc)
            raise

        # Terminal authoritative write (final state of the run).
        db_event.task_context = result_context.model_dump(mode="json")
        repository.update(obj=db_event)


def _write_failure_marker(event_id: str, exc: Exception) -> None:
    """Write a run-level ``metadata.failure`` marker in a fresh session.

    The enclosing ``db_session`` used by ``process_incoming_event`` rolls back
    its whole transaction on exception (see ``database.session.db_session``),
    which would otherwise discard this marker along with everything else
    written on that session (including any ``persist_progress`` flushes). This
    function opens a second, independently committed session so the marker
    survives that rollback.

    Never lets a failure in the marker write itself mask the original
    exception: any error here is logged and swallowed, and the caller is
    always expected to re-raise ``exc`` regardless of this function's outcome.
    """
    marker = {
        "failed": True,
        "error": f"{type(exc).__name__}: {exc}",
        "at": datetime.now(UTC).isoformat(),
    }
    try:
        with contextmanager(db_session)() as session:
            repository = GenericRepository(session=session, model=Event)
            db_event = repository.get(obj_id=event_id)
            if db_event is None:
                return

            # Build fresh dict objects (never mutate db_event.task_context's
            # existing dict in place before reassigning it) — SQLAlchemy's
            # dirty-tracking for a plain JSON column compares the attribute
            # against the value it already holds; reassigning the *same*
            # (already-mutated) object is a same-identity no-op the ORM
            # silently skips, so a run that already has a non-empty
            # task_context (e.g. from persist_progress) would otherwise never
            # actually persist this marker.
            task_context = dict(db_event.task_context) if db_event.task_context else {}
            metadata = dict(task_context.get("metadata") or {})
            metadata["failure"] = marker
            task_context["metadata"] = metadata
            db_event.task_context = task_context
            repository.update(obj=db_event)
    except Exception as marker_exc:  # pylint: disable=broad-except
        logging.error(
            "Failed to write failure marker for event %s: %s", event_id, marker_exc
        )
