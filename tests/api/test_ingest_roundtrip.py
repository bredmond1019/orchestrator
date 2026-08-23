"""Round-trip fidelity test: POST /ingest/proposal -> semantic retrieve (OR.Q task 5).

Uses the Docker-gated ``pgvector_engine`` fixture (imported here the same way
``tests/brain/conftest.py`` re-exports it, so pytest's directory-scoped
fixture resolution picks it up under ``tests/api/`` too) to exercise the real
``POST /ingest/proposal`` route end-to-end against a live pgvector database:
engine-rs's exact ``PersistToBrainNode`` payload goes in, embeddings are
mocked to a deterministic 1024-dim vector so the same vector is queryable,
and the stored row is retrieved back out via a direct pgvector
cosine-distance query against ``brain_documents`` -- the same
``_semantic_search`` path ``RetrieveChunksNode`` uses today (see
``app/workflows/document_qa_workflow_nodes/retrieve_chunks_node.py``).

Once OR.N1 ships ``syn recall``, this test can be upgraded to assert through
that command instead of querying ``brain_documents`` directly -- OR.Q does
not depend on OR.N1, so the direct query is the honest check available today.
"""

from unittest.mock import patch

import pytest
from api.security import require_api_key
from database.brain_document import BrainDocument
from database.session import db_session
from fastapi.testclient import TestClient
from main import app
from sqlalchemy.orm import sessionmaker

from tests.api.test_ingest import LEARNING_ARTIFACT_PAYLOAD
from tests.database.conftest import pgvector_engine  # noqa: F401 -- fixture import

_FAKE_VECTOR = [0.42] * 1024

PROPOSAL_PAYLOAD = {
    "artifact_id": "roundtrip-artifact-1",
    "company_name": "Roundtrip Co",
    "doc_type": "proposal",
    "section": "Executive Summary",
    "content": "Roundtrip content body for the Executive Summary section.",
    "roadmap": {"phases": [{"name": "Discovery"}]},
}


@pytest.mark.integration
class TestIngestRoundtrip:
    """POST /ingest/proposal, then retrieve it via a direct pgvector query."""

    def test_posted_proposal_is_retrievable_by_semantic_query(
        self, pgvector_engine  # noqa: F811 -- fixture param shadows the import on purpose
    ):
        session_factory = sessionmaker(bind=pgvector_engine)
        session = session_factory()

        def override_db_session():
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

        def override_require_api_key() -> None:
            """Auth is covered by tests/api/test_ingest.py; not this test's concern."""

        app.dependency_overrides[db_session] = override_db_session
        app.dependency_overrides[require_api_key] = override_require_api_key
        client = TestClient(app, raise_server_exceptions=False)

        try:
            with patch("brain.ingest.EmbeddingService") as mock_svc:
                mock_svc.return_value.embed_batch.side_effect = lambda texts: [
                    list(_FAKE_VECTOR) for _ in texts
                ]
                mock_svc.return_value.stamp = "ollama:mxbai-embed-large"
                response = client.post("/ingest/proposal", json=PROPOSAL_PAYLOAD)

            assert response.status_code == 200
            body = response.json()
            assert body == {"artifact_id": "roundtrip-artifact-1", "chunks_written": 1}

            # Retrieve via the same cosine-distance similarity path
            # RetrieveChunksNode._semantic_search uses in production.
            distance_expr = BrainDocument.embedding.cosine_distance(_FAKE_VECTOR)
            hit = session.query(BrainDocument).order_by(distance_expr).limit(1).one()

            assert hit.content == PROPOSAL_PAYLOAD["content"]
            assert hit.doc_type == "proposal"
            assert hit.section == "Executive Summary"
            assert hit.file_path == "ingested/proposal/roundtrip-artifact-1.md"
            assert hit.project == "Roundtrip Co"
            assert hit.embedding_model == "ollama:mxbai-embed-large"
        finally:
            app.dependency_overrides.clear()
            session.close()

    def test_posted_learning_artifact_is_retrievable_with_live_auth(
        self, pgvector_engine  # noqa: F811 -- fixture param shadows the import on purpose
    ):
        """POST /ingest/artifact with the literal engine LearningArtifact body.

        Unlike the proposal case above, ``require_api_key`` is NOT
        overridden here -- the missing ``X-API-Key`` header is one of the
        three defects this block (OR.3.A) exists to close, so the auth path
        must stay live in this test. ``ORCHESTRATION_API_KEY`` is set via
        the environment and a matching ``X-API-Key`` header is sent.
        """
        session_factory = sessionmaker(bind=pgvector_engine)
        session = session_factory()

        def override_db_session():
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

        app.dependency_overrides[db_session] = override_db_session
        client = TestClient(app, raise_server_exceptions=False)

        try:
            with patch.dict("os.environ", {"ORCHESTRATION_API_KEY": "roundtrip-test-key"}):
                with patch("brain.ingest.EmbeddingService") as mock_svc:
                    mock_svc.return_value.embed_batch.side_effect = lambda texts: [
                        list(_FAKE_VECTOR) for _ in texts
                    ]
                    mock_svc.return_value.stamp = "ollama:mxbai-embed-large"
                    response = client.post(
                        "/ingest/artifact",
                        json=LEARNING_ARTIFACT_PAYLOAD,
                        headers={"X-API-Key": "roundtrip-test-key"},
                    )

            assert response.status_code == 200
            body = response.json()
            assert body["artifact_id"] == LEARNING_ARTIFACT_PAYLOAD["artifact_id"]
            assert body["chunks_written"] >= 1

            # Retrieve via the same cosine-distance similarity path
            # RetrieveChunksNode._semantic_search uses in production. Scoped
            # by doc_type since the identical fake embedding vector used
            # across this file's tests otherwise makes distance-ordering
            # ambiguous between rows.
            distance_expr = BrainDocument.embedding.cosine_distance(_FAKE_VECTOR)
            hit = (
                session.query(BrainDocument)
                .filter(BrainDocument.doc_type == "learning_artifact")
                .order_by(distance_expr)
                .limit(1)
                .one()
            )

            assert hit.content == LEARNING_ARTIFACT_PAYLOAD["digest_markdown"]
            assert hit.doc_type == "learning_artifact"
        finally:
            app.dependency_overrides.clear()
            session.close()
