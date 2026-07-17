"""Tests for retrieval confidence signal + event-schema grounding fields (Task 1).

Covers:
- ``RetrieveChunksNode._compute_retrieval_confidence``: monotonic in the top
  fused score, bounded [0, 1], 0.0 on zero chunks (pure-function test).
- ``RetrieveChunksNode.process``: the ``retrieval_confidence`` key lands
  alongside the existing ``chunks`` key without disturbing it (additive-only
  envelope, CLAUDE.md rule 9 storage contract).
- ``DocumentQAEventSchema``: ``confidence_threshold`` and ``high_stakes``
  validate with documented defaults and accept overrides.
"""

import uuid
from unittest.mock import MagicMock, patch

from core.task import TaskContext
from schemas.document_qa_schema import DocumentQAEventSchema
from workflows.document_qa_workflow_nodes.retrieve_chunks_node import RetrieveChunksNode


# ---------------------------------------------------------------------------
# _compute_retrieval_confidence (pure function)
# ---------------------------------------------------------------------------


class TestComputeRetrievalConfidence:
    def test_zero_chunks_yields_zero(self):
        assert RetrieveChunksNode._compute_retrieval_confidence([]) == 0.0

    def test_bounded_between_zero_and_one(self):
        low = RetrieveChunksNode._compute_retrieval_confidence([{"score": -10.0}])
        high = RetrieveChunksNode._compute_retrieval_confidence([{"score": 10.0}])
        assert 0.0 < low < 1.0
        assert 0.0 < high < 1.0
        assert low < high

    def test_monotonic_in_top_fused_score(self):
        """A strictly higher top score never yields a lower confidence."""
        scores = [-5.0, -1.0, 0.0, 0.5, 1.0, 2.0, 5.0]
        confidences = [
            RetrieveChunksNode._compute_retrieval_confidence([{"score": s}])
            for s in scores
        ]
        assert confidences == sorted(confidences)
        # Strictly increasing for distinct scores (logistic squash is strictly
        # monotonic, not just non-decreasing).
        assert len(set(confidences)) == len(confidences)

    def test_uses_max_score_across_multiple_chunks(self):
        chunks = [{"score": 0.1}, {"score": 3.0}, {"score": -2.0}]
        expected = RetrieveChunksNode._compute_retrieval_confidence([{"score": 3.0}])
        assert RetrieveChunksNode._compute_retrieval_confidence(chunks) == expected

    def test_zero_score_yields_one_half(self):
        assert RetrieveChunksNode._compute_retrieval_confidence([{"score": 0.0}]) == 0.5


# ---------------------------------------------------------------------------
# RetrieveChunksNode.process — additive envelope
# ---------------------------------------------------------------------------


class TestProcessEnvelope:
    def test_retrieval_confidence_added_alongside_chunks(self):
        event = MagicMock()
        event.question = "What is RAG?"
        event.corpus = "content"
        ctx = TaskContext(event=event)

        fake_chunks = [
            {
                "content": "some content",
                "section_title": "Intro",
                "score": 1.5,
                "source": "Intro",
                "file_path": "doc.md",
                "doc_id": None,
                "title": None,
                "via": "semantic",
            }
        ]

        node = RetrieveChunksNode()
        with patch.object(node, "retrieve", return_value=fake_chunks) as mock_retrieve:
            result_ctx = node.process(ctx)

        mock_retrieve.assert_called_once()
        stored = result_ctx.nodes[node.node_name]["result"]
        assert stored["chunks"] == fake_chunks
        assert "retrieval_confidence" in stored
        expected = RetrieveChunksNode._compute_retrieval_confidence(fake_chunks)
        assert stored["retrieval_confidence"] == expected

    def test_retrieval_confidence_zero_on_empty_chunks(self):
        event = MagicMock()
        event.question = "What is RAG?"
        event.corpus = "content"
        ctx = TaskContext(event=event)

        node = RetrieveChunksNode()
        with patch.object(node, "retrieve", return_value=[]):
            result_ctx = node.process(ctx)

        stored = result_ctx.nodes[node.node_name]["result"]
        assert stored["chunks"] == []
        assert stored["retrieval_confidence"] == 0.0


# ---------------------------------------------------------------------------
# DocumentQAEventSchema — new fields
# ---------------------------------------------------------------------------


class TestDocumentQAEventSchemaGroundingFields:
    def _make_event(self, **overrides) -> DocumentQAEventSchema:
        defaults = {
            "doc_id": uuid.uuid4(),
            "question": "What is RAG?",
        }
        defaults.update(overrides)
        return DocumentQAEventSchema(**defaults)

    def test_defaults(self):
        event = self._make_event()
        assert isinstance(event.confidence_threshold, float)
        assert 0.0 < event.confidence_threshold < 1.0
        assert event.high_stakes is False

    def test_overrides_accepted(self):
        event = self._make_event(confidence_threshold=0.8, high_stakes=True)
        assert event.confidence_threshold == 0.8
        assert event.high_stakes is True
