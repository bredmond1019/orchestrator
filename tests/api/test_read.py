"""Tests for the GET /recall, /walk, /pulse router (OR.Q2 task 2).

Reuses the ``ingest_context`` in-memory SQLite fixture pattern from
``tests/api/test_ingest.py`` and mocks the ``app.brain`` read core at its
import site in ``api.read`` so no real pgvector connection is needed here —
core-vs-route parity against a live store is covered separately by
``tests/api/test_read_parity.py``.
"""

from unittest.mock import patch

import pytest
from api.security import require_api_key
from database.session import Base, db_session
from fastapi.testclient import TestClient
from main import app
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

MOCK_RECALL_RESULTS = [
    {
        "doc_id": "D20",
        "file_path": "docs/decisions/D20.md",
        "title": "Shared data contract",
        "section": None,
        "content": "Some content.",
        "score": 0.12,
        "via": "semantic",
    }
]

MOCK_WALK_RESULT = {
    "root": "D20",
    "depth": 1,
    "levels": [["D21"]],
    "nodes": {"D21": {"doc_id": "D21", "file_path": "docs/decisions/D21.md", "title": "Next"}},
}

MOCK_WALK_EMPTY_RESULT = {
    "root": "D20",
    "depth": 1,
    "levels": [],
    "nodes": {},
}


class _FakePulseReport:
    """Stand-in for `PulseReport` whose `to_dict()` matches the real shape."""

    def __init__(self, healthy: bool = True):
        self._healthy = healthy

    def to_dict(self) -> dict:
        return {
            "pgvector_reachable": True,
            "embedding_reachable": True,
            "embedding_error": None,
            "brain_documents_count": 42,
            "brain_edges_count": 7,
            "max_indexed_at": "2026-07-27T00:00:00",
            "max_authored_at": "2026-07-20T00:00:00",
            "edges_empty_but_related_exists": False,
            "healthy": self._healthy,
            "errors": [],
        }


@pytest.fixture
def read_context():
    """Yields (TestClient, session) sharing one in-memory SQLite DB.

    Mirrors ``tests/api/test_ingest.py::ingest_context`` — excludes
    ``brain_documents`` (a PostgreSQL/pgvector-only table) since these tests
    mock the ``app.brain`` read core and never touch it directly.
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


class TestReadAuth:
    def test_recall_without_api_key_returns_401(self, read_context):
        client, _ = read_context
        del app.dependency_overrides[require_api_key]
        with patch.dict("os.environ", {"ORCHESTRATION_API_KEY": "secret"}):
            response = client.get("/recall", params={"q": "hello"})
        assert response.status_code == 401

    def test_walk_without_api_key_returns_401(self, read_context):
        client, _ = read_context
        del app.dependency_overrides[require_api_key]
        with patch.dict("os.environ", {"ORCHESTRATION_API_KEY": "secret"}):
            response = client.get("/walk", params={"doc_id": "D20"})
        assert response.status_code == 401

    def test_pulse_without_api_key_returns_401(self, read_context):
        client, _ = read_context
        del app.dependency_overrides[require_api_key]
        with patch.dict("os.environ", {"ORCHESTRATION_API_KEY": "secret"}):
            response = client.get("/pulse")
        assert response.status_code == 401

    def test_recall_without_configured_key_returns_503(self, read_context):
        client, _ = read_context
        del app.dependency_overrides[require_api_key]
        with patch.dict("os.environ", {}, clear=True):
            response = client.get("/recall", params={"q": "hello"})
        assert response.status_code == 503


class TestReadValidation:
    def test_recall_missing_q_returns_422(self, read_context):
        client, _ = read_context
        response = client.get("/recall")
        assert response.status_code == 422

    def test_recall_empty_q_returns_422(self, read_context):
        client, _ = read_context
        response = client.get("/recall", params={"q": ""})
        assert response.status_code == 422

    def test_recall_non_integer_limit_returns_422(self, read_context):
        client, _ = read_context
        response = client.get("/recall", params={"q": "hello", "limit": "abc"})
        assert response.status_code == 422

    def test_walk_missing_doc_id_returns_422(self, read_context):
        client, _ = read_context
        response = client.get("/walk")
        assert response.status_code == 422

    def test_walk_out_of_range_depth_returns_422(self, read_context):
        client, _ = read_context
        response = client.get("/walk", params={"doc_id": "D20", "depth": 99})
        assert response.status_code == 422

    def test_walk_non_integer_depth_returns_422(self, read_context):
        client, _ = read_context
        response = client.get("/walk", params={"doc_id": "D20", "depth": "abc"})
        assert response.status_code == 422


class TestReadDispatch:
    def test_recall_returns_200_and_calls_core(self, read_context):
        client, _ = read_context
        with patch("api.read.retrieval.recall", return_value=MOCK_RECALL_RESULTS) as mock_recall:
            response = client.get(
                "/recall", params={"q": "shared data contract", "limit": 3, "hybrid": True}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "shared data contract"
        assert body["count"] == 1
        assert body["results"] == MOCK_RECALL_RESULTS

        mock_recall.assert_called_once()
        args, kwargs = mock_recall.call_args
        assert args[0] == "shared data contract"
        assert kwargs["limit"] == 3
        assert kwargs["hybrid"] is True

    def test_walk_returns_200_and_calls_core(self, read_context):
        client, _ = read_context
        with patch("api.read.graph.walk", return_value=MOCK_WALK_RESULT) as mock_walk:
            response = client.get("/walk", params={"doc_id": "D20", "depth": 1})

        assert response.status_code == 200
        assert response.json() == MOCK_WALK_RESULT

        mock_walk.assert_called_once()
        args, kwargs = mock_walk.call_args
        assert args[0] == "D20"
        assert kwargs["depth"] == 1

    def test_walk_with_no_edges_returns_200_with_empty_levels(self, read_context):
        client, _ = read_context
        with patch("api.read.graph.walk", return_value=MOCK_WALK_EMPTY_RESULT):
            response = client.get("/walk", params={"doc_id": "D20"})

        assert response.status_code == 200
        body = response.json()
        assert body["levels"] == []
        assert body["nodes"] == {}

    def test_pulse_returns_200_and_calls_core(self, read_context):
        client, _ = read_context
        fake_report = _FakePulseReport(healthy=True)
        with patch("api.read.pulse_core.pulse", return_value=fake_report) as mock_pulse:
            response = client.get("/pulse")

        assert response.status_code == 200
        assert response.json() == fake_report.to_dict()
        mock_pulse.assert_called_once()

    def test_pulse_unhealthy_still_returns_200(self, read_context):
        client, _ = read_context
        fake_report = _FakePulseReport(healthy=False)
        with patch("api.read.pulse_core.pulse", return_value=fake_report):
            response = client.get("/pulse")

        assert response.status_code == 200
        assert response.json()["healthy"] is False

    def test_recall_core_failure_returns_500_not_unhandled(self, read_context):
        client, _ = read_context
        with patch("api.read.retrieval.recall", side_effect=RuntimeError("boom")):
            response = client.get("/recall", params={"q": "hello"})
        assert response.status_code == 500

    def test_walk_core_failure_returns_500_not_unhandled(self, read_context):
        client, _ = read_context
        with patch("api.read.graph.walk", side_effect=RuntimeError("boom")):
            response = client.get("/walk", params={"doc_id": "D20"})
        assert response.status_code == 500

    def test_pulse_core_failure_returns_500_not_unhandled(self, read_context):
        client, _ = read_context
        with patch("api.read.pulse_core.pulse", side_effect=RuntimeError("boom")):
            response = client.get("/pulse")
        assert response.status_code == 500
