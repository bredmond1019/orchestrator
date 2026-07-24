"""Tests for the API endpoint layer — generic dispatch, validation, and health."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.security import require_api_key
from database.event import Event
from database.session import Base, db_session
from main import app
from worker.config import celery_app

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


@pytest.fixture
def endpoint_context():
    """Yields (TestClient, session) sharing one in-memory SQLite DB."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Exclude tables that use PostgreSQL-specific types (ARRAY, pgvector) which
    # SQLite cannot compile. brain_documents is covered by its own PG-backed tests.
    _POSTGRES_ONLY_TABLES = {"brain_documents"}
    sqlite_tables = [
        t for t in Base.metadata.sorted_tables if t.name not in _POSTGRES_ONLY_TABLES
    ]
    Base.metadata.create_all(engine, tables=sqlite_tables)
    session = sessionmaker(bind=engine)()

    def override_db_session():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    def override_require_api_key() -> None:
        """Bypass auth so dispatch tests focus on payload/DB/Celery logic."""

    app.dependency_overrides[db_session] = override_db_session
    app.dependency_overrides[require_api_key] = override_require_api_key
    client = TestClient(app, raise_server_exceptions=False)

    yield client, session

    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


class TestEventDispatch:
    def test_valid_payload_returns_202(self, endpoint_context):
        client, _ = endpoint_context
        with patch.object(celery_app, "send_task", return_value=MagicMock()):
            response = client.post("/events/", json=VALID_CUSTOMER_CARE_PAYLOAD)
        assert response.status_code == 202

    def test_unknown_workflow_type_returns_422(self, endpoint_context):
        client, _ = endpoint_context
        response = client.post(
            "/events/",
            json={"workflow_type": "NONEXISTENT", "data": {}},
        )
        assert response.status_code == 422

    def test_invalid_data_returns_422(self, endpoint_context):
        client, _ = endpoint_context
        response = client.post(
            "/events/",
            json={"workflow_type": "CUSTOMER_CARE", "data": {"from_email": "x"}},
        )
        assert response.status_code == 422

    def test_failed_enqueue_does_not_commit_event(self, endpoint_context):
        client, session = endpoint_context
        with patch.object(
            celery_app, "send_task", side_effect=RuntimeError("Redis unavailable")
        ):
            response = client.post("/events/", json=VALID_CUSTOMER_CARE_PAYLOAD)
        assert response.status_code == 500
        assert session.query(Event).count() == 0

    def test_successful_enqueue_commits_event(self, endpoint_context):
        client, session = endpoint_context
        with patch.object(celery_app, "send_task", return_value=MagicMock()):
            response = client.post("/events/", json=VALID_CUSTOMER_CARE_PAYLOAD)
        assert response.status_code == 202
        assert session.query(Event).count() == 1

    def test_202_body_contains_event_id_matching_persisted_row(self, endpoint_context):
        client, session = endpoint_context
        with patch.object(celery_app, "send_task", return_value=MagicMock()):
            response = client.post("/events/", json=VALID_CUSTOMER_CARE_PAYLOAD)
        assert response.status_code == 202

        body = response.json()
        assert "event_id" in body
        # Must be a parseable UUID string.
        event_uuid = uuid.UUID(body["event_id"])

        rows = session.query(Event).all()
        assert len(rows) == 1
        assert str(rows[0].id) == str(event_uuid)
        assert body["event_id"] == str(rows[0].id)


class TestEventRead:
    """Tests for `GET /events/{event_id}`."""

    def _seed_event(self, session, task_context=None, workflow_type="CUSTOMER_CARE"):
        event = Event(data={"foo": "bar"}, workflow_type=workflow_type)
        event.task_context = task_context
        session.add(event)
        session.commit()
        return event

    def test_200_for_seeded_row_with_typed_fields(self, endpoint_context):
        client, session = endpoint_context
        task_context = {
            "event": {"foo": "bar"},
            "nodes": {},
            "node_runs": {"NodeA": {"status": "success"}},
            "metadata": {},
        }
        event = self._seed_event(session, task_context=task_context)

        response = client.get(f"/events/{event.id}")

        assert response.status_code == 200
        body = response.json()
        assert body["event_id"] == str(event.id)
        assert body["workflow_type"] == "CUSTOMER_CARE"
        assert body["status"] == "succeeded"
        assert isinstance(body["created_at"], str)
        assert isinstance(body["updated_at"], str)
        assert body["task_context"] == task_context

    def test_404_for_unknown_uuid(self, endpoint_context):
        client, _ = endpoint_context
        response = client.get(f"/events/{uuid.uuid4()}")
        assert response.status_code == 404

    def test_404_not_500_for_malformed_id(self, endpoint_context):
        client, _ = endpoint_context
        response = client.get("/events/not-a-uuid")
        assert response.status_code == 404

    def test_401_without_api_key_header(self, endpoint_context, monkeypatch):
        client, session = endpoint_context
        event = self._seed_event(session)
        monkeypatch.setenv("ORCHESTRATION_API_KEY", "expected-key")
        app.dependency_overrides.pop(require_api_key, None)

        response = client.get(f"/events/{event.id}")

        assert response.status_code == 401

    def test_submit_then_poll_reports_queued(self, endpoint_context):
        client, _ = endpoint_context
        with patch.object(celery_app, "send_task", return_value=MagicMock()):
            post_response = client.post("/events/", json=VALID_CUSTOMER_CARE_PAYLOAD)
        assert post_response.status_code == 202
        event_id = post_response.json()["event_id"]

        get_response = client.get(f"/events/{event_id}")

        assert get_response.status_code == 200
        body = get_response.json()
        assert body["event_id"] == event_id
        assert body["status"] == "queued"
        assert body["task_context"] is None


class TestHealthCheck:
    def test_health_returns_200(self, endpoint_context):
        client, _ = endpoint_context
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


class TestSchemaRegistryCompleteness:
    """Every WorkflowRegistry member must have a SCHEMA_MAP entry.

    This test is the automated guard for the step-3 rule documented in
    docs/api-reference.md (WorkflowRegistry > Adding a New Entry). Without it,
    a new workflow added to WorkflowRegistry but forgotten in SCHEMA_MAP will
    cause the API dispatcher to 422 all requests for that workflow type.
    """

    def test_every_workflow_has_schema_map_entry(self):
        from api.schema_registry import SCHEMA_MAP
        from workflows.workflow_registry import WorkflowRegistry

        missing = [
            member.name
            for member in WorkflowRegistry
            if member.name not in SCHEMA_MAP
        ]
        assert not missing, (
            f"WorkflowRegistry members missing from SCHEMA_MAP: {missing}. "
            "Add them to app/api/schema_registry.py (see api-reference.md step 3)."
        )
