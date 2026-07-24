"""Golden response fixtures + end-to-end submit/poll/terminal tests for the event read API.

Two things live in this file:

1. **Golden fixture conformance** — for each pinned fixture under
   ``tests/fixtures/event_read/``, seed a row carrying that fixture's
   ``task_context``, call the live ``GET /events/{event_id}`` route, and
   assert the response's key set matches the fixture's exactly and the
   derived ``status`` equals the fixture's ``status``. A drifting response
   shape (a renamed or dropped field) or a status-derivation regression
   fails here first.
2. **End-to-end submit -> poll -> terminal** — ``POST /events/`` followed by
   polling ``GET /events/{event_id}`` through ``queued`` -> ``running`` ->
   ``succeeded`` for a stub workflow, and -> ``failed`` with
   ``metadata.failure.error`` populated for a deliberately raising one. The
   intermediate ``task_context`` writes are driven directly against the test
   database the same way ``persist_progress`` (``app/worker/tasks.py``) and
   the ``_write_failure_marker`` path do, rather than requiring a live
   Celery worker.

Reuses the ``endpoint_context`` fixture pattern from ``tests/api/test_endpoint.py``
(in-memory SQLite, ``db_session``/``require_api_key`` overrides) per the test
conventions documented in ``planning/or-y-event-read-api/tasks.md``.
"""

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import worker.tasks as worker_tasks
from api.security import require_api_key
from database.event import Event
from database.session import Base, db_session
from main import app
from worker.config import celery_app

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "event_read"

VALID_CUSTOMER_CARE_PAYLOAD = {
    "workflow_type": "CUSTOMER_CARE",
    "data": {
        "from_email": "sender@example.com",
        "to_email": "support@example.com",
        "sender": "Test User",
        "subject": "Test Subject",
        "body": "This is a test message.",
    },
}


def _load_fixture(name: str) -> dict:
    with open(FIXTURES_DIR / f"{name}.json", encoding="utf-8") as fixture_file:
        return json.load(fixture_file)


@pytest.fixture
def endpoint_context():
    """Yields (TestClient, engine, Session) sharing one in-memory SQLite DB.

    Also monkeypatches ``worker.tasks.db_session`` to open fresh sessions
    against this same engine, so ``worker.tasks._write_failure_marker`` (which
    deliberately opens its own session, independent of the caller's) writes
    against the test database instead of a real one.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _POSTGRES_ONLY_TABLES = {"brain_documents"}
    sqlite_tables = [
        t for t in Base.metadata.sorted_tables if t.name not in _POSTGRES_ONLY_TABLES
    ]
    Base.metadata.create_all(engine, tables=sqlite_tables)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    def override_db_session():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    def override_require_api_key() -> None:
        """Bypass auth so read/poll tests focus on status derivation."""

    def worker_db_session():
        fresh_session = session_factory()
        try:
            yield fresh_session
            fresh_session.commit()
        except Exception:
            fresh_session.rollback()
            raise
        finally:
            fresh_session.close()

    app.dependency_overrides[db_session] = override_db_session
    app.dependency_overrides[require_api_key] = override_require_api_key
    client = TestClient(app, raise_server_exceptions=False)

    with patch.object(worker_tasks, "db_session", worker_db_session):
        yield client, engine, session

    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def _seed_event(session, task_context=None, workflow_type="CUSTOMER_CARE") -> Event:
    event = Event(
        data=VALID_CUSTOMER_CARE_PAYLOAD["data"],
        workflow_type=workflow_type,
        task_context=task_context,
    )
    session.add(event)
    session.commit()
    return event


class TestGoldenFixtureConformance:
    """Each fixture's key set and derived status must match the live route."""

    @pytest.mark.parametrize(
        "fixture_name",
        ["queued", "running", "succeeded", "failed", "cancelled", "halted"],
    )
    def test_response_shape_matches_fixture(self, endpoint_context, fixture_name):
        client, _, session = endpoint_context
        fixture = _load_fixture(fixture_name)

        event = _seed_event(
            session,
            task_context=fixture["task_context"],
            workflow_type=fixture["workflow_type"],
        )

        response = client.get(f"/events/{event.id}")

        assert response.status_code == 200
        body = response.json()
        assert set(body.keys()) == set(fixture.keys())
        assert body["status"] == fixture["status"]

    def test_all_event_status_values_have_a_fixture(self):
        from api.event_status import EventStatus

        fixture_statuses = {
            _load_fixture(name)["status"]
            for name in ["queued", "running", "succeeded", "failed", "cancelled", "halted"]
        }
        assert fixture_statuses == {member.value for member in EventStatus}


class TestSubmitPollTerminal:
    """POST /events/ -> poll GET /events/{event_id} through its full lifecycle."""

    def test_succeeding_workflow_transitions_queued_running_succeeded(
        self, endpoint_context
    ):
        client, _, session = endpoint_context

        with patch.object(celery_app, "send_task", return_value=MagicMock()):
            post_response = client.post("/events/", json=VALID_CUSTOMER_CARE_PAYLOAD)
        assert post_response.status_code == 202
        event_id = post_response.json()["event_id"]
        assert post_response.json()["task_id"]

        # 1. queued — no task_context has been written yet.
        first_poll = client.get(f"/events/{event_id}")
        assert first_poll.status_code == 200
        assert first_poll.json()["status"] == "queued"
        assert first_poll.json()["task_context"] is None

        # 2. running — the worker's persist_progress writes a snapshot with a
        #    non-terminal node before the run finishes.
        event = session.query(Event).filter(Event.id == uuid.UUID(event_id)).one()
        event.task_context = {
            "event": VALID_CUSTOMER_CARE_PAYLOAD["data"],
            "nodes": {},
            "metadata": {},
            "node_runs": {"ClassifyNode": {"status": "running"}},
        }
        session.add(event)
        session.commit()

        second_poll = client.get(f"/events/{event_id}")
        assert second_poll.status_code == 200
        assert second_poll.json()["status"] == "running"

        # 3. succeeded — the worker's terminal authoritative write.
        event = session.query(Event).filter(Event.id == uuid.UUID(event_id)).one()
        event.task_context = {
            "event": VALID_CUSTOMER_CARE_PAYLOAD["data"],
            "nodes": {"ClassifyNode": {"output": "billing"}},
            "metadata": {},
            "node_runs": {"ClassifyNode": {"status": "success"}},
        }
        session.add(event)
        session.commit()

        third_poll = client.get(f"/events/{event_id}")
        assert third_poll.status_code == 200
        assert third_poll.json()["status"] == "succeeded"

    def test_raising_workflow_transitions_queued_running_failed(self, endpoint_context):
        client, _, session = endpoint_context

        with patch.object(celery_app, "send_task", return_value=MagicMock()):
            post_response = client.post("/events/", json=VALID_CUSTOMER_CARE_PAYLOAD)
        assert post_response.status_code == 202
        event_id = post_response.json()["event_id"]

        first_poll = client.get(f"/events/{event_id}")
        assert first_poll.json()["status"] == "queued"

        # running — one node started before the workflow raised.
        event = session.query(Event).filter(Event.id == uuid.UUID(event_id)).one()
        event.task_context = {
            "event": VALID_CUSTOMER_CARE_PAYLOAD["data"],
            "nodes": {},
            "metadata": {},
            "node_runs": {"ClassifyNode": {"status": "running"}},
        }
        session.add(event)
        session.commit()

        second_poll = client.get(f"/events/{event_id}")
        assert second_poll.json()["status"] == "running"

        # failed — drive the actual worker failure-marker path (task 4's
        # rollback-surviving write), not a hand-written metadata.failure blob.
        worker_tasks._write_failure_marker(  # pylint: disable=protected-access
            uuid.UUID(event_id),
            ValueError("workflow raised while processing ClassifyNode"),
        )

        # The marker was written on an independent session (the whole point
        # of the rollback-survival fix in task 4); expire the read session's
        # identity map so the next query reflects it, mirroring how a real
        # poll from a separate process/session would see the committed write.
        session.expire_all()

        third_poll = client.get(f"/events/{event_id}")
        assert third_poll.status_code == 200
        body = third_poll.json()
        assert body["status"] == "failed"
        assert body["task_context"]["metadata"]["failure"]["failed"] is True
        assert "ValueError" in body["task_context"]["metadata"]["failure"]["error"]
