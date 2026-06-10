"""Unit tests for ChunkingService."""

from unittest.mock import MagicMock, patch

import pytest
import tiktoken

from services.chunking_service import ChunkingService


@pytest.fixture
def service():
    return ChunkingService()


class TestChunkText:
    def test_short_text_returns_single_chunk(self, service):
        result = service.chunk_text("hello world", chunk_size=500, overlap=50)
        assert len(result) == 1
        assert "hello" in result[0]

    def test_empty_text_returns_empty_list(self, service):
        assert service.chunk_text("") == []

    def test_overlap_shared_between_adjacent_chunks(self, service):
        long_text = "word " * 600
        chunks = service.chunk_text(long_text, chunk_size=100, overlap=20)
        assert len(chunks) >= 2
        enc = tiktoken.get_encoding("cl100k_base")
        tail = enc.encode(chunks[0])[-20:]
        head = enc.encode(chunks[1])[:20]
        assert tail == head


class TestChunkDocument:
    def test_plain_text_returns_chunk_list(self, service):
        result = service.chunk_document(b"hello world", "text/plain")
        assert len(result) >= 1
        assert "hello" in result[0]

    def test_pdf_uses_fitz_open(self, service):
        mock_page = MagicMock()
        mock_page.get_text.return_value = "PDF page content"
        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page]))
        with patch("services.chunking_service.fitz.open", return_value=mock_doc):
            result = service.chunk_document(b"%PDF-fake", "application/pdf")
        assert any("PDF page content" in c for c in result)

    def test_unsupported_mime_raises_value_error(self, service):
        with pytest.raises(ValueError, match="Unsupported mime_type"):
            service.chunk_document(b"data", "image/png")
