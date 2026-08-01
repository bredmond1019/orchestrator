"""Tests for the POST /ingest/* router (OR.Q task 4).

Auth/validation cases reuse the ``endpoint_context`` in-memory SQLite pattern
from ``tests/api/test_endpoint.py`` and mock ``ingest_artifact`` so no real
pgvector write is needed — round-trip fidelity against a live embedding path
is covered separately by ``tests/api/test_ingest_roundtrip.py``.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.security import require_api_key
from database.session import Base, db_session
from main import app

VALID_PROPOSAL_PAYLOAD = {
    "artifact_id": "artifact-123",
    "company_name": "Acme Co",
    "doc_type": "proposal",
    "section": "Executive Summary",
    "content": "This is the proposal body content.",
    "roadmap": {"phases": [{"name": "Discovery"}]},
}

VALID_ARTIFACT_PAYLOAD = {
    "artifact_id": "artifact-456",
    "doc_type": "content",
    "content": "This is generic artifact content.",
}


@pytest.fixture
def ingest_context():
    """Yields (TestClient, session) sharing one in-memory SQLite DB.

    Mirrors ``tests/api/test_endpoint.py::endpoint_context`` — excludes
    ``brain_documents`` (a PostgreSQL/pgvector-only table) since these tests
    mock ``ingest_artifact`` and never touch it directly.
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
    session = sessionmaker(bind=engine)()

    def override_db_session():
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise

    def override_require_api_key() -> None:
        """Bypass auth so validation/dispatch tests focus on payload logic."""

    app.dependency_overrides[db_session] = override_db_session
    app.dependency_overrides[require_api_key] = override_require_api_key
    client = TestClient(app, raise_server_exceptions=False)

    yield client, session

    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


class TestIngestAuth:
    def test_proposal_without_api_key_returns_401(self, ingest_context):
        client, _ = ingest_context
        # Drop the auth override so the real dependency runs.
        del app.dependency_overrides[require_api_key]
        with patch.dict("os.environ", {"ORCHESTRATION_API_KEY": "secret"}):
            response = client.post("/ingest/proposal", json=VALID_PROPOSAL_PAYLOAD)
        assert response.status_code == 401

    def test_artifact_without_api_key_returns_401(self, ingest_context):
        client, _ = ingest_context
        del app.dependency_overrides[require_api_key]
        with patch.dict("os.environ", {"ORCHESTRATION_API_KEY": "secret"}):
            response = client.post("/ingest/artifact", json=VALID_ARTIFACT_PAYLOAD)
        assert response.status_code == 401


class TestIngestValidation:
    def test_proposal_missing_roadmap_returns_422(self, ingest_context):
        client, _ = ingest_context
        bad_payload = {k: v for k, v in VALID_PROPOSAL_PAYLOAD.items() if k != "roadmap"}
        response = client.post("/ingest/proposal", json=bad_payload)
        assert response.status_code == 422

    def test_proposal_empty_content_returns_422(self, ingest_context):
        client, _ = ingest_context
        bad_payload = {**VALID_PROPOSAL_PAYLOAD, "content": ""}
        response = client.post("/ingest/proposal", json=bad_payload)
        assert response.status_code == 422

    def test_artifact_missing_doc_type_returns_422(self, ingest_context):
        client, _ = ingest_context
        bad_payload = {k: v for k, v in VALID_ARTIFACT_PAYLOAD.items() if k != "doc_type"}
        response = client.post("/ingest/artifact", json=bad_payload)
        assert response.status_code == 422

    def test_malformed_body_never_returns_500(self, ingest_context):
        client, _ = ingest_context
        response = client.post("/ingest/proposal", json={"nonsense": True})
        assert response.status_code == 422


class TestIngestDispatch:
    def test_proposal_payload_returns_200_and_response(self, ingest_context):
        client, _ = ingest_context
        with patch("api.ingest.ingest_artifact", return_value=3) as mock_ingest:
            response = client.post("/ingest/proposal", json=VALID_PROPOSAL_PAYLOAD)

        assert response.status_code == 200
        body = response.json()
        assert body == {"artifact_id": "artifact-123", "chunks_written": 3}

        mock_ingest.assert_called_once()
        _, kwargs = mock_ingest.call_args
        assert kwargs["artifact_id"] == "artifact-123"
        assert kwargs["doc_type"] == "proposal"
        assert kwargs["content"] == "This is the proposal body content."
        assert kwargs["section"] == "Executive Summary"
        assert kwargs["project"] == "Acme Co"
        assert kwargs["authored_at"] is None

    def test_proposal_authored_at_is_passed_through(self, ingest_context):
        client, _ = ingest_context
        payload = {**VALID_PROPOSAL_PAYLOAD, "authored_at": "2026-01-01T12:00:00"}
        with patch("api.ingest.ingest_artifact", return_value=1) as mock_ingest:
            response = client.post("/ingest/proposal", json=payload)

        assert response.status_code == 200
        _, kwargs = mock_ingest.call_args
        assert kwargs["authored_at"].isoformat() == "2026-01-01T12:00:00"

    def test_artifact_payload_returns_200_and_response(self, ingest_context):
        client, _ = ingest_context
        with patch("api.ingest.ingest_artifact", return_value=1) as mock_ingest:
            response = client.post("/ingest/artifact", json=VALID_ARTIFACT_PAYLOAD)

        assert response.status_code == 200
        body = response.json()
        assert body == {"artifact_id": "artifact-456", "chunks_written": 1}

        mock_ingest.assert_called_once()
        _, kwargs = mock_ingest.call_args
        assert kwargs["artifact_id"] == "artifact-456"
        assert kwargs["doc_type"] == "content"
        assert kwargs["content"] == "This is generic artifact content."
        assert kwargs["section"] is None
        assert kwargs["project"] is None
        assert kwargs["authored_at"] is None

    def test_artifact_authored_at_is_passed_through(self, ingest_context):
        client, _ = ingest_context
        payload = {**VALID_ARTIFACT_PAYLOAD, "authored_at": "2026-02-02T08:00:00"}
        with patch("api.ingest.ingest_artifact", return_value=1) as mock_ingest:
            response = client.post("/ingest/artifact", json=payload)

        assert response.status_code == 200
        _, kwargs = mock_ingest.call_args
        assert kwargs["authored_at"].isoformat() == "2026-02-02T08:00:00"

    def test_ingest_slice_failure_returns_500_not_unhandled(self, ingest_context):
        client, _ = ingest_context
        with patch("api.ingest.ingest_artifact", side_effect=RuntimeError("boom")):
            response = client.post("/ingest/artifact", json=VALID_ARTIFACT_PAYLOAD)
        assert response.status_code == 500
