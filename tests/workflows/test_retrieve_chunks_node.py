"""Tests for RetrieveChunksNode — the thin TaskContext adapter over
``app/brain/retrieval_engine.py``.

These tests cover:
- ``process``: verifies ``TaskContext`` seeding and output stored under the
  right key with the ``{"result": ...}`` contract (CLAUDE.md rule 9), and
  that every event field (``corpus``, ``filters``, ``include_archived``,
  ``expand_structural``) threads from the event into ``retrieve()``.
- The I32 two-weight order-flip pin test: runs the node end-to-end (DB seams
  patched) and asserts its stored chunk order follows
  ``retrieval_engine._SECTION_TITLE_WEIGHT`` — the single-source-of-truth
  guard against a private ranking path reappearing inside the node.

Engine-level tests (``_fuse_and_rank``, ``retrieve``, ``_semantic_search``,
``_keyword_search``, ``_structural_expand``, ``_keyword_expand``,
``_merge_candidates`` — anything whose subject is
``app/brain/retrieval_engine.py`` internals) live in
``tests/brain/test_retrieval_engine.py`` (relocated by
``OR.chore.test-layout-tidy``).
"""

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from brain import retrieval_engine
from core.task import TaskContext
from workflows.document_qa_workflow_nodes.retrieve_chunks_node import RetrieveChunksNode

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(
    dist: float = 0.1,
    is_section_title: bool = False,
    content: str = "some content",
    section_title: str | None = "Intro",
    candidate_id: uuid.UUID | None = None,
    file_path: str | None = None,
) -> dict:
    """Build a candidate dict as returned by ``_semantic_search``."""
    return {
        "id": candidate_id or uuid.uuid4(),
        "content": content,
        "section_title": section_title,
        "is_section_title": is_section_title,
        "distance": dist,
        "file_path": file_path,
    }


def _make_event(question: str = "What is RAG?", corpus: str = "content"):
    """Return a minimal event-like object with the fields RetrieveChunksNode reads."""
    event = MagicMock()
    event.question = question
    event.corpus = corpus
    return event


def _make_ctx(question: str = "What is RAG?", corpus: str = "content") -> TaskContext:
    """Build a TaskContext with a minimal mock event."""
    ctx = TaskContext(event=_make_event(question, corpus))
    return ctx


# ---------------------------------------------------------------------------
# process() — TaskContext integration
# ---------------------------------------------------------------------------


class TestProcess:
    """Tests for the process() method, verifying TaskContext seeding and output."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_process_stores_result_in_task_context(self):
        """process() stores chunks under node_name with the {'result': ...} contract."""
        ctx = _make_ctx(question="What is a workflow?", corpus="content")
        fake_chunks = [
            {
                "content": "A workflow is a DAG.",
                "section_title": "Overview",
                "score": 0.9,
                "source": "Overview",
            }
        ]
        with patch.object(
            retrieval_engine, "retrieve", return_value=fake_chunks
        ):
            ctx = self.node.process(ctx)

        output = ctx.get_node_output("RetrieveChunksNode")
        assert "result" in output
        assert output["result"]["chunks"] == fake_chunks

    def test_node_ranks_through_the_shared_section_title_constant(self, monkeypatch):
        """The node's ranking must move with ``_SECTION_TITLE_WEIGHT`` — the
        single-source-of-truth pin.

        ``RetrieveChunksNode`` used to carry its own copy of the whole two-stage
        pipeline, including a duplicate ``2.0 if is_section_title`` rule; ``OR.K2``
        promoted the pipeline into ``brain.retrieval_engine`` and the node became a
        thin adapter. Nothing enforced that, so a private ranking path could
        silently reappear and let eval and production ``DOCUMENT_QA`` diverge
        again — which is exactly the defect this pin exists to catch. Runs the
        node end-to-end (DB seams patched) at the default weight and at 2.0 and
        asserts the stored chunk order flips.
        """
        body_id = uuid.uuid4()
        title_id = uuid.uuid4()
        candidates = [
            _make_candidate(dist=0.05, is_section_title=False, candidate_id=body_id),
            _make_candidate(dist=0.3, is_section_title=True, candidate_id=title_id),
        ]

        event = SimpleNamespace(
            question="what does the section say?",
            corpus="content",
            filters=None,
            include_archived=False,
            expand_structural=False,
            workspace_id=None,
            peer_id=None,
            include_memory=False,
            apply_decay=False,
        )

        def _run() -> list:
            ctx = TaskContext(event=event)
            with patch(
                "brain.retrieval_engine.EmbeddingService"
            ) as mock_embed, patch.object(
                retrieval_engine, "_semantic_search", return_value=list(candidates)
            ), patch.object(
                retrieval_engine, "_keyword_expand", return_value=[]
            ), patch.object(
                retrieval_engine, "_keyword_search", return_value=set()
            ), patch.object(
                retrieval_engine, "log_retrieval"
            ):
                mock_embed.return_value.embed_text.return_value = [0.1] * 1024
                ctx = self.node.process(ctx)
            return ctx.get_node_output("RetrieveChunksNode")["result"]["chunks"]

        neutral = _run()
        assert neutral[0]["id"] == body_id, "default weight must not favour a header stub"

        monkeypatch.setattr(retrieval_engine, "_SECTION_TITLE_WEIGHT", 2.0)
        boosted = _run()
        assert boosted[0]["id"] == title_id, (
            "node ranking did not follow the engine constant — a private ranking "
            "path has reappeared in RetrieveChunksNode"
        )

    def test_process_passes_corpus_from_event(self):
        """process() reads corpus from the event and passes it to retrieve."""
        ctx = _make_ctx(question="brain question", corpus="brain")
        with patch.object(retrieval_engine, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        assert mock_ret.call_args[1].get("corpus") == "brain" or \
               (len(mock_ret.call_args[0]) > 1 and mock_ret.call_args[0][1] == "brain")

    def test_process_defaults_corpus_to_content_when_absent(self):
        """process() falls back to corpus='content' if the event has no corpus attr."""
        event = MagicMock(spec=["question"])
        event.question = "What is chunking?"
        ctx = TaskContext(event=event)
        with patch.object(retrieval_engine, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        # The default should be "content"
        call_kwargs = mock_ret.call_args
        corpus_arg = (
            call_kwargs[1].get("corpus")
            if call_kwargs[1]
            else (call_kwargs[0][1] if len(call_kwargs[0]) > 1 else None)
        )
        assert corpus_arg == "content"

    def test_process_passes_filters_from_event(self):
        """process() reads filters from the event and forwards them to retrieve."""
        event = MagicMock()
        event.question = "brain question"
        event.corpus = "brain"
        event.filters = {"project": "orchestrator"}
        ctx = TaskContext(event=event)
        with patch.object(retrieval_engine, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        call_kwargs = mock_ret.call_args[1]
        assert call_kwargs.get("filters") == {"project": "orchestrator"}

    def test_process_defaults_filters_to_none_when_absent(self):
        """process() passes filters=None when the event has no filters attr."""
        event = MagicMock(spec=["question", "corpus"])
        event.question = "What is chunking?"
        event.corpus = "content"
        ctx = TaskContext(event=event)
        with patch.object(retrieval_engine, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        call_kwargs = mock_ret.call_args[1]
        assert call_kwargs.get("filters") is None


# ---------------------------------------------------------------------------
# include_archived threading — process() → retrieve()
# ---------------------------------------------------------------------------


class TestIncludeArchivedThreading:
    """include_archived threads from the event through process() to retrieve()."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_process_reads_include_archived_from_event(self):
        event = MagicMock()
        event.question = "brain question"
        event.corpus = "brain"
        event.filters = None
        event.include_archived = True
        ctx = TaskContext(event=event)
        with patch.object(retrieval_engine, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        assert mock_ret.call_args[1].get("include_archived") is True

    def test_process_defaults_include_archived_false_when_absent(self):
        event = MagicMock(spec=["question", "corpus"])
        event.question = "What is chunking?"
        event.corpus = "content"
        ctx = TaskContext(event=event)
        with patch.object(retrieval_engine, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        assert mock_ret.call_args[1].get("include_archived") is False


# ---------------------------------------------------------------------------
# expand_structural threading — process() → retrieve()
# ---------------------------------------------------------------------------


class TestExpandStructuralThreading:
    """expand_structural threads from the event through process() to retrieve()."""

    def setup_method(self):
        self.node = RetrieveChunksNode()

    def test_process_reads_expand_structural_from_event(self):
        event = MagicMock()
        event.question = "brain question"
        event.corpus = "brain"
        event.filters = None
        event.include_archived = False
        event.expand_structural = False
        ctx = TaskContext(event=event)
        with patch.object(retrieval_engine, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        assert mock_ret.call_args[1].get("expand_structural") is False

    def test_process_defaults_expand_structural_true_when_absent(self):
        event = MagicMock(spec=["question", "corpus"])
        event.question = "What is chunking?"
        event.corpus = "content"
        ctx = TaskContext(event=event)
        with patch.object(retrieval_engine, "retrieve", return_value=[]) as mock_ret:
            self.node.process(ctx)
        assert mock_ret.call_args[1].get("expand_structural") is True
