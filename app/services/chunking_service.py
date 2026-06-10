"""ChunkingService splits text or binary documents into overlapping token chunks."""

import fitz
import tiktoken


class ChunkingService:
    """Split text and binary documents into overlapping token-sized chunks.

    Uses ``tiktoken`` for token-boundary splitting and ``pymupdf`` (``fitz``)
    for PDF text extraction. Both dependencies are imported at module level so
    tests can patch ``services.chunking_service.fitz.open``.
    """

    _ENCODING = "cl100k_base"

    def _get_encoder(self) -> tiktoken.Encoding:
        return tiktoken.get_encoding(self._ENCODING)

    def chunk_text(
        self, text: str, chunk_size: int = 500, overlap: int = 50
    ) -> list[str]:
        """Split ``text`` into overlapping chunks on token boundaries.

        Each chunk holds up to ``chunk_size`` tokens; adjacent chunks share
        ``overlap`` tokens. Empty input yields an empty list.
        """
        enc = self._get_encoder()
        tokens = enc.encode(text)
        if not tokens:
            return []
        chunks = []
        step = chunk_size - overlap
        start = 0
        while start < len(tokens):
            chunk_tokens = tokens[start : start + chunk_size]
            chunks.append(enc.decode(chunk_tokens))
            start += step
        return chunks

    def chunk_document(
        self,
        content: bytes,
        mime_type: str,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> list[str]:
        """Dispatch on ``mime_type`` to the right parser, then chunk the text.

        Supports ``text/plain`` (decoded directly) and ``application/pdf``
        (text extracted via ``pymupdf``). Raises ``ValueError`` naming any
        unsupported ``mime_type``.
        """
        if mime_type == "text/plain":
            return self.chunk_text(content.decode("utf-8"), chunk_size, overlap)
        if mime_type == "application/pdf":
            doc = fitz.open(stream=content, filetype="pdf")
            text = "\n".join(page.get_text() for page in doc)
            return self.chunk_text(text, chunk_size, overlap)
        raise ValueError(f"Unsupported mime_type: {mime_type!r}")
