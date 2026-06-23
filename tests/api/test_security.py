"""Tests for API key authentication middleware (``app/api/security.py``).

Coverage:
- ``ORCHESTRATION_API_KEY`` unset  → ``POST /events/`` returns 503
- Missing ``X-API-Key`` header     → 401
- Wrong ``X-API-Key`` value        → 401
- Correct ``X-API-Key`` value      → request passes auth gate (202 when payload valid)
- ``GET /health`` is open          → 200 without any key
- Schema registry completeness     → every WorkflowRegistry member has a SCHEMA_MAP entry
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from api.schema_registry import SCHEMA_MAP
from workflows.workflow_registry import WorkflowRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_KEY = "test-secret-key"

_CONTENT_PIPELINE_PAYLOAD = {
    "workflow_type": "CONTENT_PIPELINE",
    "data": {"url": "https://example.com/article", "make_blog": False},
}


def _make_client(monkeypatch, api_key: str | None = _VALID_KEY) -> TestClient:
    """Return a TestClient with the DB and Celery fully mocked.

    ``api_key`` is the value set in the environment; ``None`` simulates
    the variable being unset.
    """
    from database.session import db_session
    from main import app

    # Patch env
    if api_key is None:
        monkeypatch.delenv("ORCHESTRATION_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ORCHESTRATION_API_KEY", api_key)

    # Stub out the DB session so no real database is needed
    mock_session = MagicMock()
    mock_session.flush = MagicMock()
    mock_session.add = MagicMock()

    def _override_db():
        yield mock_session

    app.dependency_overrides[db_session] = _override_db

    client = TestClient(app, raise_server_exceptions=False)
    yield client

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: ``GET /health`` must always be open
# ---------------------------------------------------------------------------


class TestHealthOpenAccess:
    def test_health_returns_200_without_key(self, monkeypatch):
        monkeypatch.delenv("ORCHESTRATION_API_KEY", raising=False)
        from main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/health")
        assert resp.status_code == status.HTTP_200_OK

    def test_health_returns_200_with_key(self, monkeypatch):
        monkeypatch.setenv("ORCHESTRATION_API_KEY", _VALID_KEY)
        from main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/health")
        assert resp.status_code == status.HTTP_200_OK


# ---------------------------------------------------------------------------
# Tests: ``POST /events/`` auth gate
# ---------------------------------------------------------------------------


class TestEventsAuthGate:
    def test_503_when_api_key_env_unset(self, monkeypatch):
        """Service returns 503 (fail-closed) when ORCHESTRATION_API_KEY is not set."""
        monkeypatch.delenv("ORCHESTRATION_API_KEY", raising=False)
        from main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/events/",
                json=_CONTENT_PIPELINE_PAYLOAD,
                headers={"X-API-Key": "anything"},
            )
        assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_401_when_header_missing(self, monkeypatch):
        """Request without X-API-Key header returns 401."""
        monkeypatch.setenv("ORCHESTRATION_API_KEY", _VALID_KEY)
        from main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post("/events/", json=_CONTENT_PIPELINE_PAYLOAD)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_401_when_key_wrong(self, monkeypatch):
        """Wrong X-API-Key value returns 401."""
        monkeypatch.setenv("ORCHESTRATION_API_KEY", _VALID_KEY)
        from main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.post(
                "/events/",
                json=_CONTENT_PIPELINE_PAYLOAD,
                headers={"X-API-Key": "wrong-key"},
            )
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_202_when_key_correct(self, monkeypatch):
        """Correct X-API-Key + valid payload reaches the handler and returns 202."""
        monkeypatch.setenv("ORCHESTRATION_API_KEY", _VALID_KEY)

        from database.session import db_session
        from main import app

        mock_session = MagicMock()
        mock_task = MagicMock()
        mock_task.id = "celery-task-uuid-1234"

        def _override_db():
            yield mock_session

        app.dependency_overrides[db_session] = _override_db

        try:
            with patch("api.endpoint.celery_app.send_task", return_value=mock_task):
                with TestClient(app, raise_server_exceptions=False) as c:
                    resp = c.post(
                        "/events/",
                        json=_CONTENT_PIPELINE_PAYLOAD,
                        headers={"X-API-Key": _VALID_KEY},
                    )
            assert resp.status_code == status.HTTP_202_ACCEPTED
            body = resp.json()
            assert "task_id" in body
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Tests: schema registry completeness (preserve existing coverage contract)
# ---------------------------------------------------------------------------


class TestSchemaRegistryCompleteness:
    def test_every_workflow_has_schema_entry(self):
        """Every WorkflowRegistry member must have a corresponding SCHEMA_MAP entry."""
        for member in WorkflowRegistry:
            assert member.name in SCHEMA_MAP, (
                f"WorkflowRegistry.{member.name} has no entry in SCHEMA_MAP. "
                "Add one to app/api/schema_registry.py."
            )
