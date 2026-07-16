"""Tests for RetrieveChunksNode Stage 1d memory expansion (block OR.M Task 4).

Gives ``MemoryLoaderNode`` its first consumer: accumulated ``SemanticMemory``
facts surface as a fourth ``via="memory"`` candidate source alongside
semantic/structural/keyword, gated on ``include_memory=True`` AND a non-None
``workspace_id`` (design decision 2).

Cases covered (mirroring the task spec's list):
(a) ``include_memory=False`` — ``_memory_expand`` never called.
(b) ``include_memory=True`` + ``workspace_id=None`` — ``[]``, no DB touched.
(c) No peers / no facts — output identical to pre-block (graceful
    degradation, the most important acceptance criterion in the block).
(d) Facts present — a ``via="memory"`` candidate reaches the returned chunks
    (asserts arrival, not merely that the code path executed).
(e) A decayed fact ranks below a fresh fact of equal cosine similarity.
(f) No ``semantic_memories`` id is passed to ``_keyword_search``.

Per CLAUDE.md standing rule 9, ``TaskContext`` output is asserted via the
real ``{"result": ...}`` contract produced by ``update_node``.
"""

import uuid
from unittest.mock import MagicMock, patch

from core.task import TaskContext
from workflows.document_qa_workflow_nodes.retrieve_chunks_node import (
    RetrieveChunksNode,
)


def _make_event(  # pylint: disable=too-many-arguments
    question: str = "What did we decide?",
    corpus: str = "content",
    workspace_id: str | None = None,
    peer_id: str | None = None,
    include_memory: bool = False,
):
    """Return a minimal event-like object with the fields RetrieveChunksNode reads."""
    event = MagicMock()
    event.question = question
    event.corpus = corpus
    event.filters = None
    event.include_archived = False
    event.expand_structural = True
    event.workspace_id = workspace_id
    event.peer_id = peer_id
    event.include_memory = include_memory
    return event


def _make_ctx(**kwargs) -> TaskContext:
    return TaskContext(event=_make_event(**kwargs))


class _NodeHarness:
    """Shared setup: a node plus a context manager that patches every DB/embed
    seam RetrieveChunksNode.retrieve() touches except _memory_expand/
    MemoryLoaderNode.retrieve, which each test controls directly."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def _patched(self, semantic_candidates=None):
        semantic_candidates = semantic_candidates if semantic_candidates is not None else []
        return patch.multiple(
            self.node,
            _semantic_search=MagicMock(return_value=semantic_candidates),
            _structural_expand=MagicMock(return_value=[]),
            _keyword_expand=MagicMock(return_value=[]),
            _keyword_search=MagicMock(return_value={}),
        )


class TestIncludeMemoryGating(_NodeHarness):
    """(a) include_memory=False never calls _memory_expand."""

    def test_include_memory_false_never_calls_memory_expand(self):
        with self._patched(), patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as mock_emb, patch.object(
            self.node, "_memory_expand"
        ) as mock_memory_expand:
            mock_emb.return_value.embed_text.return_value = [0.1] * 1024
            self.node.retrieve(
                "q",
                corpus="content",
                workspace_id="some-workspace",
                include_memory=False,
            )
        mock_memory_expand.assert_not_called()

    def test_include_memory_false_via_process(self):
        """Same gate, driven end-to-end through process()."""
        ctx = _make_ctx(workspace_id="some-workspace", include_memory=False)
        with self._patched(), patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as mock_emb, patch.object(
            self.node, "_memory_expand"
        ) as mock_memory_expand:
            mock_emb.return_value.embed_text.return_value = [0.1] * 1024
            self.node.process(ctx)
        mock_memory_expand.assert_not_called()


class TestWorkspaceIdNoneNoOp(_NodeHarness):
    """(b) include_memory=True + workspace_id=None returns [] and touches no DB."""

    def test_memory_expand_returns_empty_when_workspace_id_none(self):
        result = RetrieveChunksNode._memory_expand(
            [0.1] * 1024, workspace_id=None, peer_id=None
        )
        assert result == []

    def test_memory_expand_opens_no_db_session_when_workspace_id_none(self):
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.MemoryLoaderNode"
        ) as mock_loader_cls:
            result = RetrieveChunksNode._memory_expand(
                [0.1] * 1024, workspace_id=None, peer_id="p1"
            )
        assert result == []
        mock_loader_cls.assert_not_called()

    def test_retrieve_end_to_end_workspace_id_none(self):
        with self._patched(), patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as mock_emb, patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.MemoryLoaderNode"
        ) as mock_loader_cls:
            mock_emb.return_value.embed_text.return_value = [0.1] * 1024
            results = self.node.retrieve(
                "q",
                corpus="content",
                workspace_id=None,
                include_memory=True,
            )
        assert results == []
        mock_loader_cls.assert_not_called()


class TestGracefulDegradationNoPeersNoFacts(_NodeHarness):
    """(c) No peers / no facts — output identical to pre-block. The single
    most important acceptance criterion in the spec."""

    def test_no_facts_returns_pre_block_identical_results(self):
        candidate_id = uuid.uuid4()
        semantic_candidate = {
            "id": candidate_id,
            "content": "doc content",
            "section_title": "Intro",
            "is_section_title": False,
            "distance": 0.1,
            "file_path": "doc.md",
            "doc_id": "doc-1",
            "title": "Doc",
            "via": "semantic",
        }

        with self._patched(semantic_candidates=[semantic_candidate]), patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as mock_emb, patch.object(
            self.node,
            "_memory_expand",
            return_value=[],  # MemoryLoaderNode with no facts returns []
        ):
            mock_emb.return_value.embed_text.return_value = [0.1] * 1024

            without_memory = self.node.retrieve(
                "q", corpus="content", workspace_id=None, include_memory=False
            )
            with_memory_no_facts = self.node.retrieve(
                "q", corpus="content", workspace_id="ws-1", include_memory=True
            )

        assert without_memory == with_memory_no_facts
        assert len(without_memory) == 1
        assert without_memory[0]["content"] == "doc content"


class TestMemoryFactReachesOutput(_NodeHarness):
    """(d) Facts present — a via="memory" candidate reaches the returned
    chunks, asserting arrival rather than mere code-path execution."""

    def test_memory_candidate_arrives_in_returned_chunks(self):
        memory_candidate = {
            "id": "mem-1",
            "content": "we decided X in June",
            "section_title": None,
            "is_section_title": False,
            "distance": 0.05,  # high similarity -> high score, should surface
            "file_path": None,
            "doc_id": None,
            "title": None,
            "via": "memory",
        }

        with self._patched(semantic_candidates=[]), patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as mock_emb, patch.object(
            self.node, "_memory_expand", return_value=[memory_candidate]
        ):
            mock_emb.return_value.embed_text.return_value = [0.1] * 1024
            results = self.node.retrieve(
                "q", corpus="content", workspace_id="ws-1", include_memory=True
            )

        memory_hits = [r for r in results if r["via"] == "memory"]
        assert len(memory_hits) >= 1
        assert memory_hits[0]["content"] == "we decided X in June"
        assert len(memory_hits) <= 3

    def test_memory_expand_adapts_fact_dicts_to_candidate_shape(self):
        """Verifies the real _memory_expand adapter (not a stand-in): the
        distance inversion, via tag, and None provenance fields."""
        fake_facts = {
            "facts": [
                {
                    "id": "fact-1",
                    "peer_id": "peer-a",
                    "fact": "the fact text",
                    "confidence": 0.9,
                    "effective_confidence": 0.9,
                    "score": 0.8,
                    "evidence_episode_ids": [],
                }
            ],
            "episodes": [],
        }
        with patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.MemoryLoaderNode"
        ) as mock_loader_cls:
            mock_loader_cls.return_value.retrieve.return_value = fake_facts
            result = RetrieveChunksNode._memory_expand(
                [0.1] * 1024, workspace_id="ws-1", peer_id=None
            )

        assert len(result) == 1
        candidate = result[0]
        assert candidate["id"] == "fact-1"
        assert candidate["content"] == "the fact text"
        assert candidate["via"] == "memory"
        assert candidate["file_path"] is None
        assert candidate["doc_id"] is None
        assert candidate["title"] is None
        assert candidate["section_title"] is None
        assert candidate["is_section_title"] is False
        # distance = 1.0 - (score * effective_confidence) = 1.0 - (0.8*0.9)
        assert candidate["distance"] == 1.0 - (0.8 * 0.9)

        mock_loader_cls.return_value.retrieve.assert_called_once_with(
            workspace_id="ws-1",
            peer_id=None,
            query_embedding=[0.1] * 1024,
            top_k=3,
        )


class TestDecayOrdering(_NodeHarness):
    """(e) A decayed memory fact ranks below a fresh fact of equal cosine
    similarity."""

    def test_decayed_fact_ranks_below_fresh_fact_of_equal_similarity(self):
        # Equal raw cosine score, but the decayed fact has a lower
        # effective_confidence multiplier baked into its distance.
        fresh_candidate = {
            "id": "fresh",
            "content": "fresh fact",
            "section_title": None,
            "is_section_title": False,
            "distance": 1.0 - (0.9 * 1.0),
            "file_path": None,
            "doc_id": None,
            "title": None,
            "via": "memory",
        }
        decayed_candidate = {
            "id": "decayed",
            "content": "decayed fact",
            "section_title": None,
            "is_section_title": False,
            "distance": 1.0 - (0.9 * 0.4),
            "file_path": None,
            "doc_id": None,
            "title": None,
            "via": "memory",
        }

        with self._patched(semantic_candidates=[]), patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as mock_emb, patch.object(
            self.node,
            "_memory_expand",
            return_value=[decayed_candidate, fresh_candidate],
        ):
            mock_emb.return_value.embed_text.return_value = [0.1] * 1024
            results = self.node.retrieve(
                "q", corpus="content", workspace_id="ws-1", include_memory=True
            )

        ids_in_order = [r["id"] for r in results]
        assert ids_in_order.index("fresh") < ids_in_order.index("decayed")


class TestMemoryIdsExcludedFromKeywordSearch(_NodeHarness):
    """(f) No semantic_memories id is passed to _keyword_search."""

    def test_memory_ids_never_reach_keyword_search(self):
        doc_candidate_id = uuid.uuid4()
        semantic_candidate = {
            "id": doc_candidate_id,
            "content": "doc content",
            "section_title": "Intro",
            "is_section_title": False,
            "distance": 0.2,
            "file_path": "doc.md",
            "doc_id": "doc-1",
            "title": "Doc",
            "via": "semantic",
        }
        memory_candidate = {
            "id": "mem-uuid-1",
            "content": "a fact",
            "section_title": None,
            "is_section_title": False,
            "distance": 0.1,
            "file_path": None,
            "doc_id": None,
            "title": None,
            "via": "memory",
        }

        with self._patched(semantic_candidates=[semantic_candidate]), patch(
            "workflows.document_qa_workflow_nodes.retrieve_chunks_node.EmbeddingService"
        ) as mock_emb, patch.object(
            self.node, "_memory_expand", return_value=[memory_candidate]
        ):
            mock_emb.return_value.embed_text.return_value = [0.1] * 1024
            self.node.retrieve(
                "q", corpus="content", workspace_id="ws-1", include_memory=True
            )

            called_args, called_kwargs = self.node._keyword_search.call_args
            candidate_ids_arg = (
                called_args[1] if len(called_args) > 1 else called_kwargs.get("candidate_ids")
            )
            assert "mem-uuid-1" not in candidate_ids_arg
            assert doc_candidate_id in candidate_ids_arg
