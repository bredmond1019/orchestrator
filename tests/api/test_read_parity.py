"""Core-vs-route parity tests for GET /recall, /walk, /pulse (OR.Q2 task 3).

The block's eval slice: proves the HTTP layer in ``api.read`` adds nothing
and drops nothing relative to the ``app/brain/`` read core it adapts. For
each route, the ``app/brain/`` core function is called directly and the
route is called via ``TestClient``, with the SAME arguments and the SAME
injected session (the Docker-gated ``pgvector_session`` fixture from
``tests/database/conftest.py``, pulled in the same way
``tests/brain/conftest.py`` does), and the route's JSON body is asserted to
equal the core's return value after only the documented serialization.

Embeddings are mocked to a deterministic 1024-dim vector
(``EmbeddingService.embed_text`` patched at its defining module) so both the
direct core call and the route call embed identically without a live
Ollama/Voyage backend, while still exercising a real pgvector round trip.

Skips cleanly (via the ``pgvector_engine`` fixture) when Docker is
unavailable, so this file must not break a Docker-less run.
"""

from datetime import datetime
from unittest.mock import patch

import pytest
from api.security import require_api_key
from brain import graph as graph_core
from brain import pulse as pulse_core
from brain import retrieval as retrieval_core
from database.brain_document import BrainDocument
from database.brain_edge import BrainEdge
from database.session import db_session
from fastapi.testclient import TestClient
from main import app

DETERMINISTIC_VECTOR = [0.1] * 1024


def _make_doc(doc_id: str, **overrides) -> BrainDocument:
    defaults = dict(
        file_path=f"docs/decisions/{doc_id}-example.md",
        doc_type="decision",
        content=f"Content for {doc_id}.",
        title=f"{doc_id} — Example Decision",
        section="",
        doc_id=doc_id,
        embedding=DETERMINISTIC_VECTOR,
        indexed_at=datetime(2026, 1, 1),
        authored_at=datetime(2026, 1, 1),
    )
    defaults.update(overrides)
    return BrainDocument(**defaults)


def _make_edge(source_doc_id: str, target_doc_id: str) -> BrainEdge:
    return BrainEdge(
        source_node_id=f"brain:{source_doc_id}",
        source_doc_id=source_doc_id,
        to_ref=target_doc_id,
        target_node_id=f"brain:{target_doc_id}",
        target_doc_id=target_doc_id,
    )


@pytest.fixture
def parity_client(pgvector_session):
    """Yields a TestClient whose `db_session` is the SAME injected `pgvector_session`.

    Auth is bypassed via a dependency override (parity is about the read
    core, not the auth guard, which is covered separately by
    `tests/api/test_read.py`). No commit/rollback happens in the override —
    only `flush()` is used by callers, preserving the fixture's
    transaction-rollback test isolation.
    """

    def override_db_session():
        yield pgvector_session

    def override_require_api_key() -> None:
        """Bypass auth so parity tests focus on core-vs-route output equality."""

    app.dependency_overrides[db_session] = override_db_session
    app.dependency_overrides[require_api_key] = override_require_api_key
    client = TestClient(app, raise_server_exceptions=False)

    yield client

    app.dependency_overrides.clear()


class TestRecallParity:
    """`GET /recall` returns exactly what `retrieval.recall()` returns."""

    def test_recall_route_matches_core(self, parity_client, pgvector_session):
        pgvector_session.add(_make_doc("D36"))
        pgvector_session.flush()

        with patch(
            "services.embedding_service.EmbeddingService.embed_text",
            return_value=DETERMINISTIC_VECTOR,
        ):
            core_results = retrieval_core.recall(
                "what is the bastion program", limit=5, hybrid=False, session=pgvector_session
            )
            response = parity_client.get(
                "/recall", params={"q": "what is the bastion program", "limit": 5}
            )

        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "what is the bastion program"
        assert body["count"] == len(core_results)
        assert body["results"] == core_results

    def test_recall_workspace_param_is_not_reachable_from_route(
        self, parity_client, pgvector_session
    ):
        """The `workspace` arg of `recall()` is explicitly out of scope for this block."""
        pgvector_session.add(_make_doc("D41"))
        pgvector_session.flush()

        with patch(
            "services.embedding_service.EmbeddingService.embed_text",
            return_value=DETERMINISTIC_VECTOR,
        ):
            core_results = retrieval_core.recall(
                "what is the bastion program", limit=5, hybrid=False, session=pgvector_session
            )
            # Passing an unknown `workspace` query param must not change anything:
            # it is silently ignored, not threaded through to `recall(workspace=...)`.
            response = parity_client.get(
                "/recall",
                params={"q": "what is the bastion program", "limit": 5, "workspace": "foo"},
            )

        assert response.status_code == 200
        assert response.json()["results"] == core_results


class TestWalkParity:
    """`GET /walk` returns exactly what `graph.walk()` returns."""

    def test_walk_route_matches_core(self, parity_client, pgvector_session):
        pgvector_session.add_all(
            [
                _make_doc("D36"),
                _make_doc("D41"),
                _make_edge("D36", "D41"),
            ]
        )
        pgvector_session.flush()

        core_result = graph_core.walk("D36", depth=1, session=pgvector_session)
        response = parity_client.get("/walk", params={"doc_id": "D36", "depth": 1})

        assert response.status_code == 200
        assert response.json() == core_result

    def test_walk_route_matches_core_when_no_edges(self, parity_client, pgvector_session):
        pgvector_session.add(_make_doc("D50"))
        pgvector_session.flush()

        core_result = graph_core.walk("D50", depth=1, session=pgvector_session)
        response = parity_client.get("/walk", params={"doc_id": "D50", "depth": 1})

        assert core_result["levels"] == []
        assert response.status_code == 200
        assert response.json() == core_result


class TestPulseParity:
    """`GET /pulse` returns exactly what `pulse.pulse().to_dict()` returns."""

    def test_pulse_route_matches_core(self, parity_client, pgvector_session):
        pgvector_session.add_all(
            [
                _make_doc("D36"),
                _make_doc("D41"),
                _make_edge("D36", "D41"),
            ]
        )
        pgvector_session.flush()

        with patch(
            "services.embedding_service.EmbeddingService.embed_text",
            return_value=DETERMINISTIC_VECTOR,
        ):
            core_report = pulse_core.pulse(session=pgvector_session)
            response = parity_client.get("/pulse")

        assert response.status_code == 200
        assert response.json() == core_report.to_dict()
