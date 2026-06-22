"""Tests for the API endpoint layer — generic dispatch, validation, and health."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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

    app.dependency_overrides[db_session] = override_db_session
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


class TestHealthCheck:
    def test_health_returns_200(self, endpoint_context):
        client, _ = endpoint_context
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
