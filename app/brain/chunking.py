"""app/brain/chunking.py — pure, DB-free text chunking helpers for the Brain corpus.

Extracted out of ``scripts/index_brain.py`` (OR.Q, CLAUDE.md rule 10 — extract
on the second consumer) so there is exactly one chunk→embed→write path shared
between the CLI indexer (``scripts/index_brain.py``) and the ``POST /ingest/*``
API route (``app/brain/ingest.py``). Behavior is byte-for-byte identical to the
original script functions; only the module changed.
"""

import re

# Matches an H2 or H3 markdown header line (``## ...`` / ``### ...``). Used by
# ``chunk_by_section`` to split a document's body into section-level chunks.
_HEADER_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


def build_context_prefix(meta: dict) -> str:
    """Build a compact semantic context prefix to prepend to embed-text.

    Includes only the semantic fields: ``type``, ``title``, ``description``,
    ``layer``, ``project``, ``keywords``.  Excludes ``status``, ``doc_id``,
    and ``related`` (non-semantic / relational metadata).  Returns an empty
    string when no semantic fields are present.

    The prefix is used *only* during embedding — it is never stored in the
    ``content`` column.

    Args:
        meta: Raw metadata dict returned by ``parse_document``.

    Returns:
        A newline-terminated prefix string, or ``""`` if no semantic fields
        are present.
    """
    parts: list[str] = []

    if meta.get("type"):
        parts.append(f"type: {meta['type']}")
    if meta.get("title"):
        parts.append(f"title: {meta['title']}")
    if meta.get("description"):
        parts.append(f"description: {meta['description']}")

    layer = meta.get("layer")
    if layer:
        if isinstance(layer, str):
            layer = [layer]
        parts.append(f"layer: {', '.join(str(v) for v in layer)}")

    if meta.get("project"):
        parts.append(f"project: {meta['project']}")

    keywords = meta.get("keywords")
    if keywords:
        if isinstance(keywords, str):
            keywords = [keywords]
        parts.append(f"keywords: {', '.join(str(v) for v in keywords)}")

    if not parts:
        return ""
    return "\n".join(parts) + "\n\n"


def chunk_by_section(content: str) -> list[tuple[str, str]]:
    """Split markdown content into (section, body) pairs by H2/H3 headers.

    Returns a list of (section_header, body_text) tuples. If the file has no
    H2/H3 headers the entire content is returned as a single chunk with section="".
    The section value is the full header line including the '#' characters.
    """
    matches = list(_HEADER_RE.finditer(content))
    if not matches:
        return [("", content.strip())]

    chunks: list[tuple[str, str]] = []

    # Text before the first header (preamble)
    preamble = content[: matches[0].start()].strip()
    if preamble:
        chunks.append(("", preamble))

    for i, m in enumerate(matches):
        section_header = m.group(0)
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip()
        combined = f"{section_header}\n{body}" if body else section_header
        chunks.append((section_header, combined))

    return chunks


def _is_header_only_chunk(section_header: str, chunk_text: str) -> bool:
    """True when a chunk is just a section header with no real body.

    ``chunk_by_section`` prepends the header to every chunk's text
    (``combined = f"{section_header}\n{body}"``), so a naive
    ``chunk_text.startswith("#")`` would flag *every* chunk. The flag must be
    measured on the **header-stripped body**: strip the leading header span,
    then treat the chunk as a section title only when what remains is empty or
    trivially short (< 40 chars). This feeds the 2x section-title weight in
    ``RetrieveChunksNode._fuse_and_rank`` — if it fired on every chunk the
    weight would be pure noise.
    """
    body = chunk_text[len(section_header):].strip()
    return body == "" or len(body) < 40


def _count_tokens(text: str) -> int:
    """Estimate token count using tiktoken cl100k_base encoding."""
    import tiktoken  # pylint: disable=import-outside-toplevel

    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def _split_chunk(text: str, max_tokens: int = 500, overlap: int = 50) -> list[str]:
    """Further split a chunk that exceeds max_tokens using ChunkingService."""
    from services.chunking_service import (  # pylint: disable=import-outside-toplevel
        ChunkingService,
    )

    svc = ChunkingService()
    return svc.chunk_text(text, chunk_size=max_tokens, overlap=overlap)
