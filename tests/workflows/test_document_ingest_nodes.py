"""Unit tests for the document_ingest workflow nodes (Project D, Task 2).

All four nodes are tested in isolation — no real database, no real Voyage
API key, no real PDF parsing:

- ``ParseDocumentNode``: text path and PDF path (``fitz.open`` patched).
- ``ChunkDocumentNode``: section-aware chunking — heading chunks, section tags,
  position order, and token-window/overlap behaviour.
- ``EmbedChunksNode``: single batched ``embed_batch`` call; vectors zipped back.
- ``StoreChunksNode``: ``_persist`` monkeypatched; assert ORM objects are correct.

TaskContext seeds follow CLAUDE.md rule 9: upstream output is stored as
``{"result": payload}`` matching what ``update_node`` writes.
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from core.task import TaskContext
from schemas.document_ingest_schema import DocumentIngestEventSchema
from workflows.document_ingest_workflow_nodes.chunk_document_node import (
    ChunkDocumentNode,
)
from workflows.document_ingest_workflow_nodes.embed_chunks_node import EmbedChunksNode
from workflows.document_ingest_workflow_nodes.parse_document_node import (
    ParseDocumentNode,
)
from workflows.document_ingest_workflow_nodes.store_chunks_node import StoreChunksNode


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(**overrides) -> DocumentIngestEventSchema:
    defaults = {
        "title": "Test Doc",
        "content": "Hello world",
        "chunk_size": 500,
        "overlap": 50,
    }
    defaults.update(overrides)
    return DocumentIngestEventSchema(**defaults)


def _make_ctx(event: DocumentIngestEventSchema | None = None) -> TaskContext:
    return TaskContext(event=event or _make_event())


# ---------------------------------------------------------------------------
# ParseDocumentNode
# ---------------------------------------------------------------------------


class TestParseDocumentNode:
    def test_text_path_returns_content(self):
        """When event.content is set, the node stores it as-is."""
        event = _make_event(content="hello text")
        ctx = _make_ctx(event)
        ParseDocumentNode().process(ctx)
        result = ctx.nodes["ParseDocumentNode"]["result"]
        assert result["text"] == "hello text"

    def test_b64_text_plain_decoded(self):
        """Base64 text/plain bytes are decoded to a string."""
        import base64

        raw = "base64 content"
        encoded = base64.b64encode(raw.encode("utf-8")).decode()
        event = _make_event(content=None, content_b64=encoded, mime_type="text/plain")
        ctx = _make_ctx(event)
        ParseDocumentNode().process(ctx)
        assert ctx.nodes["ParseDocumentNode"]["result"]["text"] == raw

    def test_pdf_path_uses_fitz(self):
        """PDF path calls fitz.open and joins page text."""
        import base64

        fake_bytes = b"%PDF-fake"
        encoded = base64.b64encode(fake_bytes).decode()
        event = _make_event(
            content=None, content_b64=encoded, mime_type="application/pdf"
        )
        ctx = _make_ctx(event)

        fake_page = MagicMock()
        fake_page.get_text.return_value = "page text"
        fake_doc = MagicMock()
        fake_doc.__iter__ = MagicMock(return_value=iter([fake_page]))

        with patch(
            "workflows.document_ingest_workflow_nodes.parse_document_node.fitz.open",
            return_value=fake_doc,
        ):
            ParseDocumentNode().process(ctx)

        result = ctx.nodes["ParseDocumentNode"]["result"]
        assert "page text" in result["text"]

    def test_unsupported_mime_raises(self):
        """An unsupported MIME type raises ValueError."""
        import base64

        encoded = base64.b64encode(b"data").decode()
        event = _make_event(
            content=None, content_b64=encoded, mime_type="application/octet-stream"
        )
        ctx = _make_ctx(event)
        with pytest.raises(ValueError, match="Unsupported mime_type"):
            ParseDocumentNode().process(ctx)


# ---------------------------------------------------------------------------
# ChunkDocumentNode
# ---------------------------------------------------------------------------

_MARKDOWN_TEXT = """\
# Introduction

This is the introduction section. It contains some text about the topic.

## Details

Here we go into more detail about the subject matter at hand.
"""


class TestChunkDocumentNode:
    def _ctx_with_parse_result(self, text: str, chunk_size: int = 500, overlap: int = 50):
        event = _make_event(content=text, chunk_size=chunk_size, overlap=overlap)
        ctx = TaskContext(event=event)
        # Seed upstream node output using the real {"result": ...} contract (rule 9)
        ctx.nodes["ParseDocumentNode"] = {"result": {"text": text}}
        return ctx

    def test_markdown_headers_produce_title_chunks(self):
        """Each markdown header becomes a standalone is_section_title=True chunk."""
        ctx = self._ctx_with_parse_result(_MARKDOWN_TEXT)
        ChunkDocumentNode().process(ctx)
        chunks = ctx.nodes["ChunkDocumentNode"]["result"]["chunks"]
        title_chunks = [c for c in chunks if c["is_section_title"]]
        titles = [c["content"] for c in title_chunks]
        assert "Introduction" in titles
        assert "Details" in titles

    def test_body_chunks_tagged_with_section_title(self):
        """Body chunks carry the correct section_title from the preceding header."""
        ctx = self._ctx_with_parse_result(_MARKDOWN_TEXT)
        ChunkDocumentNode().process(ctx)
        chunks = ctx.nodes["ChunkDocumentNode"]["result"]["chunks"]
        body_under_intro = [
            c
            for c in chunks
            if not c["is_section_title"] and c["section_title"] == "Introduction"
        ]
        assert len(body_under_intro) >= 1
        assert "introduction" in body_under_intro[0]["content"].lower()

    def test_position_is_strictly_increasing(self):
        """Position counter must increase by 1 across all emitted chunks."""
        ctx = self._ctx_with_parse_result(_MARKDOWN_TEXT)
        ChunkDocumentNode().process(ctx)
        chunks = ctx.nodes["ChunkDocumentNode"]["result"]["chunks"]
        positions = [c["position"] for c in chunks]
        assert positions == list(range(len(positions)))

    def test_no_headers_text_has_no_section_title(self):
        """Plain text without headers produces only body chunks with section_title=None."""
        plain_text = "This is a plain document without any headers at all."
        ctx = self._ctx_with_parse_result(plain_text)
        ChunkDocumentNode().process(ctx)
        chunks = ctx.nodes["ChunkDocumentNode"]["result"]["chunks"]
        assert all(c["section_title"] is None for c in chunks)
        assert all(not c["is_section_title"] for c in chunks)

    def test_chunk_count_for_known_length_input(self):
        """For a text that produces exactly 2 chunks at 10-token windows/5-token overlap,
        the node emits 2 body chunks (no headers)."""
        # Use the real ChunkingService to get the expected count
        from services.chunking_service import ChunkingService

        text = "word " * 15  # 15 tokens
        chunk_size = 10
        overlap = 5
        expected = ChunkingService().chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        ctx = self._ctx_with_parse_result(text, chunk_size=chunk_size, overlap=overlap)
        ChunkDocumentNode().process(ctx)
        chunks = ctx.nodes["ChunkDocumentNode"]["result"]["chunks"]
        body_chunks = [c for c in chunks if not c["is_section_title"]]
        assert len(body_chunks) == len(expected)

    def test_all_chunks_have_required_keys(self):
        """Every chunk dict contains the four required keys."""
        ctx = self._ctx_with_parse_result(_MARKDOWN_TEXT)
        ChunkDocumentNode().process(ctx)
        chunks = ctx.nodes["ChunkDocumentNode"]["result"]["chunks"]
        for c in chunks:
            assert "position" in c
            assert "section_title" in c
            assert "is_section_title" in c
            assert "content" in c


# ---------------------------------------------------------------------------
# EmbedChunksNode
# ---------------------------------------------------------------------------


class TestEmbedChunksNode:
    def _ctx_with_chunks(self, n: int = 3):
        event = _make_event()
        ctx = TaskContext(event=event)
        chunks = [
            {
                "position": i,
                "section_title": None,
                "is_section_title": False,
                "content": f"chunk text {i}",
            }
            for i in range(n)
        ]
        ctx.nodes["ChunkDocumentNode"] = {"result": {"chunks": chunks}}
        return ctx, chunks

    def test_embed_batch_called_once(self):
        """embed_batch must be called exactly once with all chunk contents."""
        ctx, chunks = self._ctx_with_chunks(3)
        fake_vectors = [[float(i)] * 1024 for i in range(3)]

        with patch(
            "workflows.document_ingest_workflow_nodes.embed_chunks_node.EmbeddingService"
        ) as MockES:
            instance = MockES.return_value
            instance.embed_batch.return_value = fake_vectors
            EmbedChunksNode().process(ctx)

        instance.embed_batch.assert_called_once_with(
            [c["content"] for c in chunks]
        )

    def test_vectors_attached_to_chunks(self):
        """Each output chunk carries an 'embedding' key with the correct vector."""
        ctx, _ = self._ctx_with_chunks(2)
        fake_vectors = [[0.1] * 1024, [0.2] * 1024]

        with patch(
            "workflows.document_ingest_workflow_nodes.embed_chunks_node.EmbeddingService"
        ) as MockES:
            MockES.return_value.embed_batch.return_value = fake_vectors
            EmbedChunksNode().process(ctx)

        result_chunks = ctx.nodes["EmbedChunksNode"]["result"]["chunks"]
        assert result_chunks[0]["embedding"] == fake_vectors[0]
        assert result_chunks[1]["embedding"] == fake_vectors[1]

    def test_chunk_count_preserved(self):
        """The output chunk list has the same length as the input."""
        n = 5
        ctx, _ = self._ctx_with_chunks(n)
        fake_vectors = [[0.0] * 1024 for _ in range(n)]

        with patch(
            "workflows.document_ingest_workflow_nodes.embed_chunks_node.EmbeddingService"
        ) as MockES:
            MockES.return_value.embed_batch.return_value = fake_vectors
            EmbedChunksNode().process(ctx)

        assert len(ctx.nodes["EmbedChunksNode"]["result"]["chunks"]) == n


# ---------------------------------------------------------------------------
# StoreChunksNode
# ---------------------------------------------------------------------------


class TestStoreChunksNode:
    def _ctx_with_embedded_chunks(self, n: int = 3, doc_id: uuid.UUID | None = None):
        doc_id = doc_id or uuid.uuid4()
        event = _make_event(doc_id=doc_id)
        ctx = TaskContext(event=event)
        chunks = [
            {
                "position": i,
                "section_title": "Intro" if i % 2 == 0 else None,
                "is_section_title": False,
                "content": f"content {i}",
                "embedding": [float(i)] * 1024,
            }
            for i in range(n)
        ]
        ctx.nodes["EmbedChunksNode"] = {"result": {"chunks": chunks}}
        return ctx, doc_id

    def test_persist_called_with_orm_objects(self, monkeypatch):
        """_persist receives a list of ContentChunk ORM objects."""
        from database.content_chunk import ContentChunk

        ctx, doc_id = self._ctx_with_embedded_chunks(3)
        captured: list = []
        node = StoreChunksNode()
        monkeypatch.setattr(node, "_persist", lambda chunks: captured.extend(chunks))
        node.process(ctx)

        assert len(captured) == 3
        assert all(isinstance(c, ContentChunk) for c in captured)

    def test_chunks_carry_correct_doc_id(self, monkeypatch):
        """Each ContentChunk ORM object carries the event's doc_id."""
        doc_id = uuid.uuid4()
        ctx, _ = self._ctx_with_embedded_chunks(2, doc_id=doc_id)
        captured: list = []
        node = StoreChunksNode()
        monkeypatch.setattr(node, "_persist", lambda chunks: captured.extend(chunks))
        node.process(ctx)

        assert all(str(c.doc_id) == str(doc_id) for c in captured)

    def test_chunks_carry_correct_positions(self, monkeypatch):
        """Position values on ORM objects match the embedded chunk positions."""
        ctx, _ = self._ctx_with_embedded_chunks(4)
        captured: list = []
        node = StoreChunksNode()
        monkeypatch.setattr(node, "_persist", lambda chunks: captured.extend(chunks))
        node.process(ctx)

        assert [c.position for c in captured] == [0, 1, 2, 3]

    def test_result_reports_chunks_stored(self, monkeypatch):
        """The node output reports the correct chunks_stored count."""
        n = 4
        ctx, doc_id = self._ctx_with_embedded_chunks(n)
        node = StoreChunksNode()
        monkeypatch.setattr(node, "_persist", lambda chunks: None)
        node.process(ctx)

        result = ctx.nodes["StoreChunksNode"]["result"]
        assert result["chunks_stored"] == n
        assert result["embedded"] is True
        assert result["doc_id"] == str(doc_id)

    def test_embeddings_on_orm_objects(self, monkeypatch):
        """ContentChunk ORM objects carry the embedding from the upstream node."""
        ctx, _ = self._ctx_with_embedded_chunks(2)
        captured: list = []
        node = StoreChunksNode()
        monkeypatch.setattr(node, "_persist", lambda chunks: captured.extend(chunks))
        node.process(ctx)

        assert captured[0].embedding == [0.0] * 1024
        assert captured[1].embedding == [1.0] * 1024
