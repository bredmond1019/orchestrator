"""TranscriptService fetches and optionally chunks YouTube video transcripts."""

import re

from youtube_transcript_api import YouTubeTranscriptApi

from services.chunking_service import ChunkingService

_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/|embed/|shorts/)([a-zA-Z0-9_-]{11})")


class TranscriptService:
    """Fetch YouTube transcripts and return clean text or overlapping chunks."""

    def _extract_video_id(self, url: str) -> str:
        """Extract the 11-character YouTube video ID from a URL.

        Raises ``ValueError`` if no video ID can be parsed from ``url``.
        """
        match = _VIDEO_ID_RE.search(url)
        if not match:
            raise ValueError(f"Cannot extract video ID from URL: {url!r}")
        return match.group(1)

    def fetch_transcript(self, url: str) -> str:
        """Fetch the transcript for a YouTube URL and return joined text.

        Raises ``ValueError`` for unsupported URL formats and ``RuntimeError``
        when no transcript is available or the result is empty. Never returns a
        silent empty string.
        """
        video_id = self._extract_video_id(url)
        try:
            fetched = YouTubeTranscriptApi().fetch(video_id)
        except Exception as e:
            raise RuntimeError(
                f"Could not fetch transcript for video {video_id!r}: {e}"
            ) from e
        text = " ".join(snippet.text for snippet in fetched).strip()
        if not text:
            raise RuntimeError(f"Transcript for video {video_id!r} is empty")
        return text

    def fetch_and_chunk(
        self, url: str, chunk_size: int = 500, overlap: int = 50
    ) -> list[str]:
        """Fetch a transcript and split it into overlapping token-sized chunks."""
        text = self.fetch_transcript(url)
        return ChunkingService().chunk_text(
            text, chunk_size=chunk_size, overlap=overlap
        )
