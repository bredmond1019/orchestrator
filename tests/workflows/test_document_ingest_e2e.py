"""End-to-end smoke tests for DocumentIngestWorkflow.

Runs the full four-node pipeline in sequence — ParseDocument → ChunkDocument
→ EmbedChunks → StoreChunks — with all external services mocked.  The goal is
not to re-test node behaviour (covered by test_document_ingest_nodes.py) but to
verify that the cross-node key contract holds end-to-end: each node correctly
reads what the previous node actually wrote, using the {"result": ...} wrapper.

This is the YouTube-pipeline gap class: unit tests can all pass while nodes
silently disagree about the key they publish/consume.
"""

import uuid
from unittest.mock import MagicMock, patch

from core.task import TaskContext
from schemas.document_ingest_schema import DocumentIngestEventSchema
from workflows.document_ingest_workflow_nodes.chunk_document_node import ChunkDocumentNode
from workflows.document_ingest_workflow_nodes.embed_chunks_node import EmbedChunksNode
from workflows.document_ingest_workflow_nodes.parse_document_node import ParseDocumentNode
from workflows.document_ingest_workflow_nodes.store_chunks_node import StoreChunksNode

_MARKDOWN_DOC = """\
# Introduction

This is a short introduction to the topic.

## Details

More detail about the subject matter here.
"""


def _make_event(**overrides) -> DocumentIngestEventSchema:
    defaults = {
        "title": "E2E Test Doc",
        "content": _MARKDOWN_DOC,
        "chunk_size": 500,
        "overlap": 50,
    }
    defaults.update(overrides)
    return DocumentIngestEventSchema(**defaults)


class TestDocumentIngestPipelineE2E:
    """Full pipeline: all four nodes run in sequence on the same TaskContext."""

    def _run_pipeline(self, event: DocumentIngestEventSchema | None = None):
        """Run the full ingest pipeline and return the final TaskContext."""
        event = event or _make_event()
        ctx = TaskContext(event=event)
        doc_id = event.doc_id

        # Node 1 — ParseDocumentNode (no external deps for text path)
        ParseDocumentNode().process(ctx)

        # Node 2 — ChunkDocumentNode (uses real ChunkingService)
        ChunkDocumentNode().process(ctx)

        chunks_after_chunk = ctx.nodes["ChunkDocumentNode"]["result"]["chunks"]
        n = len(chunks_after_chunk)

        # Node 3 — EmbedChunksNode (EmbeddingService mocked)
        fake_vectors = [[float(i % 10) / 10] * 1024 for i in range(n)]
        with patch(
            "workflows.document_ingest_workflow_nodes.embed_chunks_node.EmbeddingService"
        ) as MockES:
            MockES.return_value.embed_batch.return_value = fake_vectors
            EmbedChunksNode().process(ctx)

        # Node 4 — StoreChunksNode (_persist mocked)
        persisted: list = []
        node4 = StoreChunksNode()
        node4._persist = lambda chunks: persisted.extend(chunks)
        node4.process(ctx)

        return ctx, doc_id, persisted

    def test_final_result_reports_correct_chunk_count(self):
        """StoreChunksNode result['chunks_stored'] matches what ChunkDocumentNode produced."""
        ctx, _, persisted = self._run_pipeline()
        stored_result = ctx.nodes["StoreChunksNode"]["result"]
        chunked = ctx.nodes["ChunkDocumentNode"]["result"]["chunks"]
        assert stored_result["chunks_stored"] == len(chunked)
        assert stored_result["chunks_stored"] == len(persisted)

    def test_doc_id_consistent_through_pipeline(self):
        """doc_id on every persisted ORM object matches the event doc_id."""
        ctx, doc_id, persisted = self._run_pipeline()
        assert all(str(c.doc_id) == str(doc_id) for c in persisted)

    def test_embeddings_present_on_stored_chunks(self):
        """Every persisted ContentChunk carries a 1024-dim embedding."""
        _, _, persisted = self._run_pipeline()
        assert all(len(c.embedding) == 1024 for c in persisted)

    def test_section_title_chunks_survive_full_pipeline(self):
        """is_section_title=True chunks from ChunkDocument are stored correctly."""
        _, _, persisted = self._run_pipeline()
        from database.content_chunk import ContentChunk
        title_chunks = [c for c in persisted if c.is_section_title]
        assert len(title_chunks) >= 2  # "Introduction" and "Details"

    def test_positions_are_contiguous_in_stored_chunks(self):
        """Positions on stored ORM objects form a contiguous 0..N-1 sequence."""
        _, _, persisted = self._run_pipeline()
        positions = sorted(c.position for c in persisted)
        assert positions == list(range(len(positions)))

    def test_parse_output_key_contract(self):
        """ParseDocumentNode writes {"result": {"text": ...}} — consumed by ChunkDocumentNode."""
        event = _make_event(content="Hello world")
        ctx = TaskContext(event=event)
        ParseDocumentNode().process(ctx)
        # This is the exact key path ChunkDocumentNode reads
        text = ctx.nodes["ParseDocumentNode"]["result"]["text"]
        assert text == "Hello world"

    def test_chunk_output_key_contract(self):
        """ChunkDocumentNode writes {"result": {"chunks": [...]}} — consumed by EmbedChunksNode."""
        event = _make_event(content="Hello world without headers")
        ctx = TaskContext(event=event)
        ParseDocumentNode().process(ctx)
        ChunkDocumentNode().process(ctx)
        chunks = ctx.nodes["ChunkDocumentNode"]["result"]["chunks"]
        assert isinstance(chunks, list)
        assert len(chunks) >= 1
        assert all("content" in c and "embedding" not in c for c in chunks)

    def test_embed_output_key_contract(self):
        """EmbedChunksNode writes {"result": {"chunks": [...]}} — consumed by StoreChunksNode."""
        event = _make_event(content="Simple text")
        ctx = TaskContext(event=event)
        ParseDocumentNode().process(ctx)
        ChunkDocumentNode().process(ctx)
        n = len(ctx.nodes["ChunkDocumentNode"]["result"]["chunks"])
        with patch(
            "workflows.document_ingest_workflow_nodes.embed_chunks_node.EmbeddingService"
        ) as MockES:
            MockES.return_value.embed_batch.return_value = [[0.0] * 1024] * n
            EmbedChunksNode().process(ctx)
        chunks = ctx.nodes["EmbedChunksNode"]["result"]["chunks"]
        assert all("embedding" in c for c in chunks)
