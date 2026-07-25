"""Tests for app/brain/ingest.py — the shared ingest service slice (OR.Q task 2).

Pure-logic assertions (chunk count, provenance, embed-prefix-not-stored, upsert
delete-query shape) run against a mocked session with ``EmbeddingService``
patched out. The real-write / upsert-replaces-not-duplicates assertion runs
against the Docker-gated ``pgvector_engine`` fixture (``tests/brain/conftest.py``
re-exports it from ``tests/database/conftest.py``).
"""

from unittest.mock import MagicMock, patch

import pytest
from brain.ingest import ingest_artifact
from database.brain_document import BrainDocument

_FAKE_VECTOR = [0.1] * 1024


def _mock_embed_batch(texts: list[str]) -> list[list[float]]:
    return [list(_FAKE_VECTOR) for _ in texts]


class TestIngestArtifactPureLogic:
    """Assertions that don't require a real database — session is a MagicMock."""

    def test_writes_expected_row_count_and_fields(self):
        session = MagicMock()
        with patch("brain.ingest.EmbeddingService") as mock_svc:
            mock_svc.return_value.embed_batch.side_effect = _mock_embed_batch

            written = ingest_artifact(
                session,
                artifact_id="artifact-123",
                doc_type="proposal",
                content="## Summary\nSome proposal content.",
                section=None,
                project="acme-co",
                title="Acme Proposal",
                description="An automation roadmap proposal.",
            )

        assert written == 1
        assert session.add.call_count == 1
        (doc,) = (call.args[0] for call in session.add.call_args_list)
        assert isinstance(doc, BrainDocument)
        assert doc.file_path == "ingested/proposal/artifact-123.md"
        assert doc.doc_type == "proposal"
        assert doc.section == "## Summary"
        assert doc.project == "acme-co"
        assert doc.title == "Acme Proposal"
        assert doc.description == "An automation roadmap proposal."
        # Stored content is the clean chunk text — no context prefix baked in.
        assert doc.content == "## Summary\nSome proposal content."
        assert doc.content.startswith("## Summary")
        assert "type: proposal" not in doc.content
        assert list(doc.embedding) == _FAKE_VECTOR

    def test_embed_text_carries_prefix_but_stored_content_does_not(self):
        session = MagicMock()
        captured_embed_texts: list[str] = []

        def _capture(texts: list[str]) -> list[list[float]]:
            captured_embed_texts.extend(texts)
            return _mock_embed_batch(texts)

        with patch("brain.ingest.EmbeddingService") as mock_svc:
            mock_svc.return_value.embed_batch.side_effect = _capture

            ingest_artifact(
                session,
                artifact_id="artifact-456",
                doc_type="content",
                content="Body text with no headers.",
                title="A Title",
                description="A description.",
            )

        assert len(captured_embed_texts) == 1
        embed_text = captured_embed_texts[0]
        assert "title: A Title" in embed_text
        assert "description: A description." in embed_text
        assert embed_text.endswith("Body text with no headers.")

        (doc,) = (call.args[0] for call in session.add.call_args_list)
        assert doc.content == "Body text with no headers."
        assert "title: A Title" not in doc.content

    def test_derives_file_path_from_artifact_id_and_doc_type(self):
        session = MagicMock()
        with patch("brain.ingest.EmbeddingService") as mock_svc:
            mock_svc.return_value.embed_batch.side_effect = _mock_embed_batch
            ingest_artifact(
                session,
                artifact_id="xyz-789",
                doc_type="intel",
                content="Some content.",
            )
        (doc,) = (call.args[0] for call in session.add.call_args_list)
        assert doc.file_path == "ingested/intel/xyz-789.md"

    def test_upsert_deletes_by_file_path_and_section_before_insert(self):
        session = MagicMock()
        delete_query = session.query.return_value.filter.return_value
        with patch("brain.ingest.EmbeddingService") as mock_svc:
            mock_svc.return_value.embed_batch.side_effect = _mock_embed_batch
            ingest_artifact(
                session,
                artifact_id="artifact-del",
                doc_type="proposal",
                content="Plain body, no headers.",
            )
        session.query.assert_any_call(BrainDocument)
        assert delete_query.delete.called

    def test_project_scopes_the_upsert_delete_filter(self):
        session = MagicMock()
        base_filter = session.query.return_value.filter.return_value
        with patch("brain.ingest.EmbeddingService") as mock_svc:
            mock_svc.return_value.embed_batch.side_effect = _mock_embed_batch
            ingest_artifact(
                session,
                artifact_id="artifact-scoped",
                doc_type="proposal",
                content="Body.",
                project="acme-co",
            )
        # project set -> an extra .filter() call scopes the delete by project.
        assert base_filter.filter.called

    def test_embedding_count_mismatch_raises(self):
        session = MagicMock()
        with patch("brain.ingest.EmbeddingService") as mock_svc:
            # Return one fewer embedding than chunks -> zip(strict=True) must
            # fail loudly rather than silently misalign chunk<->embedding rows.
            mock_svc.return_value.embed_batch.return_value = []
            with pytest.raises(ValueError):
                ingest_artifact(
                    session,
                    artifact_id="artifact-mismatch",
                    doc_type="proposal",
                    content="Some non-empty body content.",
                )


@pytest.mark.integration
class TestIngestArtifactRealWrite:
    """Real pgvector write + upsert-replaces-not-duplicates (Docker-gated)."""

    def test_real_write_produces_row(self, pgvector_session):
        with patch("brain.ingest.EmbeddingService") as mock_svc:
            mock_svc.return_value.embed_batch.side_effect = _mock_embed_batch
            written = ingest_artifact(
                pgvector_session,
                artifact_id="real-artifact-1",
                doc_type="proposal",
                content="## Section One\nSome real content.",
                project="real-co",
            )
        pgvector_session.flush()

        assert written == 1
        rows = (
            pgvector_session.query(BrainDocument)
            .filter(BrainDocument.file_path == "ingested/proposal/real-artifact-1.md")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].content == "## Section One\nSome real content."
        assert rows[0].project == "real-co"
        assert len(rows[0].embedding) == 1024

    def test_reingesting_same_artifact_and_section_replaces_not_duplicates(
        self, pgvector_session
    ):
        with patch("brain.ingest.EmbeddingService") as mock_svc:
            mock_svc.return_value.embed_batch.side_effect = _mock_embed_batch
            ingest_artifact(
                pgvector_session,
                artifact_id="real-artifact-2",
                doc_type="proposal",
                content="## Only Section\nOriginal content.",
                project="real-co",
            )
            pgvector_session.flush()

            ingest_artifact(
                pgvector_session,
                artifact_id="real-artifact-2",
                doc_type="proposal",
                content="## Only Section\nUpdated content.",
                project="real-co",
            )
            pgvector_session.flush()

        rows = (
            pgvector_session.query(BrainDocument)
            .filter(BrainDocument.file_path == "ingested/proposal/real-artifact-2.md")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].content == "## Only Section\nUpdated content."
