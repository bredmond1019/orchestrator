"""app/brain/ingest.py — the shared ingest service slice for POST /ingest/*.

Reuses the one chunk->embed->write path shared with the CLI indexer
(``scripts/index_brain.py``): chunking helpers live in ``app.brain.chunking``
(OR.Q task 1), embedding goes through ``EmbeddingService.embed_batch``, and
the upsert pattern mirrors the delete-by-``file_path``+``section`` then-insert
loop at ``scripts/index_brain.py``'s ``main()`` (around line 987). This module
is the write-behind-the-endpoint half of OR.Q's ingest seam: engine-rs hybrid
workflows acquire and reason, then POST the finished artifact here, and this
is where it becomes ``brain_documents`` rows.
"""

import logging
from datetime import datetime

from database.brain_document import BrainDocument
from services.embedding_service import EmbeddingService
from sqlalchemy.orm import Session

from brain.chunking import (
    _count_tokens,
    _is_header_only_chunk,
    _split_chunk,
    build_context_prefix,
    chunk_by_section,
)

logger = logging.getLogger(__name__)


def _derive_file_path(doc_type: str, artifact_id: str) -> str:
    """Derive a stable, human-readable provenance path from an artifact id.

    Ingested artifacts have no real filesystem path — this synthesizes one
    (``ingested/<doc_type>/<artifact_id>.md``) so ``brain_documents.file_path``
    keeps its existing semantics (a stable key the delete-then-insert upsert
    matches on) without conflating ingested rows with corpus-crawled ones.
    """
    return f"ingested/{doc_type}/{artifact_id}.md"


def _build_final_chunks(content: str, section: str | None) -> list[tuple[str, str]]:
    """Chunk ``content`` into (section, text) pairs, splitting oversized ones.

    When ``section`` is supplied (the engine-rs proposal shape, where the
    caller already knows which section this POST covers), the whole ``content``
    is treated as that one section's body — mirroring how a single
    ``index_brain.py`` section chunk is handled — and only oversized-token
    splitting applies. When ``section`` is omitted (the generic artifact
    shape), ``chunk_by_section`` first splits ``content`` by its own H2/H3
    headers, same as the CLI indexer does for a whole file.
    """
    section_chunks = chunk_by_section(content) if not section else [(section, content)]

    final_chunks: list[tuple[str, str]] = []
    for section_header, body_text in section_chunks:
        if _count_tokens(body_text) > 500:
            for sub in _split_chunk(body_text):
                final_chunks.append((section_header, sub))
        else:
            final_chunks.append((section_header, body_text))
    return final_chunks


def _upsert_chunk(
    session: Session,
    *,
    file_path: str,
    doc_type: str,
    attribution: dict[str, str | None],
    section_header: str,
    chunk_text: str,
    embedding: list[float],
) -> None:
    """Delete any existing row for this (file_path, section[, project]), then insert.

    ``attribution`` carries the caller's ``project``/``title``/``description``
    (bundled into one dict to keep this helper's argument count small and
    stable — see ``ingest_artifact`` for the source values).
    """
    project = attribution.get("project")
    delete_query = session.query(BrainDocument).filter(
        BrainDocument.file_path == file_path,
        BrainDocument.section == section_header,
    )
    if project:
        delete_query = delete_query.filter(BrainDocument.project == project)
    delete_query.delete(synchronize_session=False)

    session.add(
        BrainDocument(
            file_path=file_path,
            doc_type=doc_type,
            section=section_header,
            content=chunk_text,
            embedding=embedding,
            indexed_at=datetime.now(),
            authored_at=datetime.now(),
            project=project,
            is_section_title=_is_header_only_chunk(section_header, chunk_text),
            title=attribution.get("title") or None,
            description=attribution.get("description") or None,
            # content_tsv is a generated column — Postgres maintains it;
            # NEVER set it here.
        )
    )


def ingest_artifact(
    session: Session,
    *,
    artifact_id: str,
    doc_type: str,
    content: str,
    section: str | None = None,
    project: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> int:
    """Chunk, embed, and upsert one artifact's content into ``brain_documents``.

    Mirrors ``scripts/index_brain.py``'s chunk->embed->write path exactly:
    ``chunk_by_section`` + ``_split_chunk`` for oversized sections, an
    embed-text built by prefixing each chunk with ``build_context_prefix``
    (the prefix is embed-only and is never stored), and a delete-by-
    ``file_path``+``section`` (additionally scoped by ``project`` when set)
    then-insert upsert per chunk so re-ingesting the same artifact+section
    replaces rather than duplicates.

    Args:
        session: An open SQLAlchemy session (caller owns commit/rollback via
            its own ``db_session`` dependency).
        artifact_id: Stable identifier for the source artifact; used to
            derive ``file_path`` provenance.
        doc_type: Corpus category (e.g. ``proposal``, ``content``, ``intel``).
        content: The raw artifact text to chunk, embed, and store.
        section: Optional section label; stored on every chunk row produced
            from ``content`` (chunking further splits *within* the section
            when it exceeds 500 tokens, but every resulting sub-chunk keeps
            this same section label for the upsert match).
        project: Optional OKF project slug; scopes the upsert delete so two
            projects sharing an ``artifact_id`` never clobber each other.
        title: Optional OKF title, stored for FTS/citation display.
        description: Optional OKF description, stored for FTS/citation
            display and folded into the embed-text context prefix.

    Returns:
        The number of ``BrainDocument`` chunk rows written.
    """
    attribution = {"project": project, "title": title, "description": description}
    file_path = _derive_file_path(doc_type, artifact_id)
    context_prefix = build_context_prefix({"type": doc_type, **attribution})

    final_chunks = _build_final_chunks(content, section)
    if not final_chunks:
        return 0

    embed_texts = [context_prefix + chunk_text for _, chunk_text in final_chunks]
    embeddings = EmbeddingService().embed_batch(embed_texts)

    chunks_written = 0
    # strict=True: an embedding-count mismatch must fail loudly here, never
    # silently misalign chunk<->embedding rows (mirrors index_brain.py's guard).
    for (section_header, chunk_text), embedding in zip(final_chunks, embeddings, strict=True):
        _upsert_chunk(
            session,
            file_path=file_path,
            doc_type=doc_type,
            attribution=attribution,
            section_header=section_header,
            chunk_text=chunk_text,
            embedding=embedding,
        )
        chunks_written += 1

    logger.info(
        "Ingested artifact %s -> %d chunks written to %s",
        artifact_id,
        chunks_written,
        file_path,
    )
    return chunks_written
