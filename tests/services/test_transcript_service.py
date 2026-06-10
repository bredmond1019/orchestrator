"""Unit tests for TranscriptService."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from services.transcript_service import TranscriptService


@pytest.fixture
def service():
    return TranscriptService()


def _snippets(*texts):
    """Build a fake FetchedTranscript: an iterable of objects with ``.text``."""
    return [SimpleNamespace(text=t) for t in texts]


class TestExtractVideoId:
    def test_standard_watch_url(self, service):
        assert (
            service._extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            == "dQw4w9WgXcQ"
        )

    def test_short_url(self, service):
        assert (
            service._extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
        )

    def test_embed_url(self, service):
        assert (
            service._extract_video_id("https://www.youtube.com/embed/dQw4w9WgXcQ")
            == "dQw4w9WgXcQ"
        )

    def test_invalid_url_raises_value_error(self, service):
        with pytest.raises(ValueError, match="Cannot extract video ID"):
            service._extract_video_id("https://example.com/not-a-video")


class TestFetchTranscript:
    def test_joins_transcript_snippets(self, service):
        with patch(
            "services.transcript_service.YouTubeTranscriptApi.fetch",
            return_value=_snippets("Hello", "world"),
        ):
            result = service.fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        assert result == "Hello world"

    def test_bad_url_raises_value_error(self, service):
        with pytest.raises(ValueError, match="Cannot extract video ID"):
            service.fetch_transcript("https://example.com/nope")

    def test_unavailable_transcript_raises_runtime_error(self, service):
        with patch(
            "services.transcript_service.YouTubeTranscriptApi.fetch",
            side_effect=Exception("no transcript"),
        ):
            with pytest.raises(RuntimeError, match="Could not fetch transcript"):
                service.fetch_transcript("https://youtu.be/dQw4w9WgXcQ")

    def test_empty_transcript_raises_runtime_error(self, service):
        with patch(
            "services.transcript_service.YouTubeTranscriptApi.fetch",
            return_value=_snippets("", "   "),
        ):
            with pytest.raises(RuntimeError, match="is empty"):
                service.fetch_transcript("https://youtu.be/dQw4w9WgXcQ")


class TestFetchAndChunk:
    def test_delegates_to_chunking_service(self, service):
        with (
            patch.object(service, "fetch_transcript", return_value="word " * 100),
            patch(
                "services.transcript_service.ChunkingService.chunk_text",
                return_value=["chunk1", "chunk2"],
            ) as mock_chunk,
        ):
            result = service.fetch_and_chunk(
                "https://youtu.be/abc1234abcd", chunk_size=200, overlap=20
            )
        assert result == ["chunk1", "chunk2"]
        mock_chunk.assert_called_once_with(
            "word " * 100, chunk_size=200, overlap=20
        )
