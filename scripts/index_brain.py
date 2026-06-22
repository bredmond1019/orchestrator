"""index_brain.py — Brain corpus ingestion script (Layer 1 of the brain RAG stack).

Crawls the company brain (agentic-portfolio) markdown files, chunks each file
by section header (H2/H3), embeds the chunks via Voyage AI, and stores rows in
the ``brain_documents`` pgvector table for later semantic retrieval.

This script runs from the CLI — it is NOT a workflow node and is NOT run by Celery.

Usage:
    python scripts/index_brain.py [--brain-path PATH] [--rebuild] [--dry-run]

Args:
    --brain-path PATH    Path to the brain repo root. Defaults to ../agentic-portfolio.
    --rebuild            Drop all non-diagnostic rows and re-index from scratch.
    --dry-run            Print what would be indexed without writing to DB or calling
                         the embedding API.
"""

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Corpus definition: (relative-path-in-brain-repo, doc_type)
# ---------------------------------------------------------------------------
CORPUS: list[tuple[str, str]] = [
    ("docs/decisions", "decision"),
    ("docs/projects", "project"),
    ("docs/career.md", "career"),
    ("docs/brand.md", "brand"),
    ("docs/business", "business"),
    ("docs/content", "content"),
    ("docs/linkedin.md", "content"),
    ("docs/profile-and-pitch.md", "career"),
    ("planning/the-diagnostic", "diagnostic"),
    ("memory", "memory"),
    ("MEMORY.md", "memory"),
]

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

_HEADER_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


def _resolve_brain_path(raw: str) -> Path:
    """Resolve --brain-path to an absolute path and validate it looks like the brain repo."""
    p = Path(raw).resolve()
    if not p.exists():
        raise SystemExit(f"Error: --brain-path does not exist: {p}")
    if not (p / "docs").is_dir():
        raise SystemExit(
            f"Error: {p} does not look like the brain repo — 'docs/' directory not found"
        )
    return p


def _collect_files(brain_path: Path) -> list[tuple[Path, str]]:
    """Return (absolute_path, doc_type) pairs for every file in the corpus."""
    result: list[tuple[Path, str]] = []
    for rel, doc_type in CORPUS:
        entry = brain_path / rel
        if not entry.exists():
            logger.info("Corpus entry not found, skipping: %s", rel)
            continue
        if entry.is_file():
            result.append((entry, doc_type))
        elif entry.is_dir():
            for md_file in sorted(entry.rglob("*.md")):
                if md_file.name.startswith("_"):
                    continue
                result.append((md_file, doc_type))
    return result


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


def _count_tokens(text: str) -> int:
    """Estimate token count using tiktoken cl100k_base encoding."""
    import tiktoken  # local import — not always needed (e.g. dry-run without split)

    enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def _split_chunk(text: str, max_tokens: int = 500, overlap: int = 50) -> list[str]:
    """Further split a chunk that exceeds max_tokens using ChunkingService."""
    import sys
    from pathlib import Path

    # Ensure app/ is on the path when called from scripts/
    app_dir = Path(__file__).resolve().parent.parent / "app"
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    from services.chunking_service import ChunkingService

    svc = ChunkingService()
    return svc.chunk_text(text, chunk_size=max_tokens, overlap=overlap)


def _get_doc_type_for_path(file_path: str, brain_path: Path) -> str:
    """Determine doc_type from a file path using the CORPUS mapping."""
    rel = Path(file_path)
    try:
        rel = rel.relative_to(brain_path)
    except ValueError:
        pass
    rel_str = str(rel)

    for corpus_rel, doc_type in CORPUS:
        if rel_str == corpus_rel or rel_str.startswith(corpus_rel.rstrip("/") + "/"):
            return doc_type
    return "content"  # fallback


def main(argv: list[str] | None = None) -> None:
    """Entry point for the brain corpus indexer."""
    parser = argparse.ArgumentParser(
        description="Index the company brain markdown corpus into brain_documents table."
    )
    parser.add_argument(
        "--brain-path",
        default="../agentic-portfolio",
        help="Path to the brain repo root (default: ../agentic-portfolio)",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete all non-diagnostic rows and re-index from scratch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be indexed without writing to DB or calling the embedding API",
    )
    args = parser.parse_args(argv)

    brain_path = _resolve_brain_path(args.brain_path)

    # Set up sys.path for imports from app/
    app_dir = Path(__file__).resolve().parent.parent / "app"
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    # Collect files
    files = _collect_files(brain_path)

    if args.dry_run:
        logger.info("Dry run — no DB writes, no API calls.")
        logger.info("Files that would be indexed:")
        for fp, doc_type in files:
            rel = fp.relative_to(brain_path)
            logger.info("  [%s] %s", doc_type, rel)
        logger.info("Total: %d files", len(files))
        return

    # Import DB and service dependencies only when not dry-run
    from database.brain_document import BrainDocument
    from database.repository import GenericRepository
    from database.session import db_session
    from services.embedding_service import EmbeddingService

    embedding_svc = EmbeddingService()

    total_files = 0
    total_chunks = 0
    total_embeddings = 0
    skipped_files = 0
    errors: list[str] = []

    # Handle --rebuild: delete all non-diagnostic rows
    if args.rebuild:
        with next(db_session()) as session:  # type: ignore[arg-type]
            deleted = (
                session.query(BrainDocument)
                .filter(BrainDocument.client_slug.is_(None))
                .delete(synchronize_session=False)
            )
            session.commit()
            logger.info("--rebuild: deleted %d existing rows", deleted)

    for file_path, doc_type in files:
        rel_str = str(file_path.relative_to(brain_path))
        total_files += 1

        try:
            # Incremental skip check (skip --rebuild because we already cleared)
            if not args.rebuild:
                with next(db_session()) as session:  # type: ignore[arg-type]
                    existing = (
                        session.query(BrainDocument)
                        .filter(BrainDocument.file_path == rel_str)
                        .order_by(BrainDocument.indexed_at.desc())
                        .first()
                    )
                    if existing and existing.indexed_at is not None:
                        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if existing.indexed_at > mtime:
                            skipped_files += 1
                            continue

            # Read and chunk
            raw_content = file_path.read_text(encoding="utf-8")
            section_chunks = chunk_by_section(raw_content)

            # Further split oversized chunks
            final_chunks: list[tuple[str, str]] = []
            for section_header, body_text in section_chunks:
                if _count_tokens(body_text) > 500:
                    sub_chunks = _split_chunk(body_text)
                    for sub in sub_chunks:
                        final_chunks.append((section_header, sub))
                else:
                    final_chunks.append((section_header, body_text))

            if not final_chunks:
                continue

            chunk_texts = [c[1] for c in final_chunks]

            # Batch embed
            try:
                embeddings = embedding_svc.embed_batch(chunk_texts)
                total_embeddings += len(embeddings)
            except Exception as embed_err:  # pylint: disable=broad-except
                logger.error("Embedding failed for %s: %s", rel_str, embed_err)
                errors.append(f"{rel_str}: embed error — {embed_err}")
                continue

            # Upsert: delete existing rows for this file+section, insert new
            with next(db_session()) as session:  # type: ignore[arg-type]
                try:
                    for (section_header, chunk_text), embedding in zip(
                        final_chunks, embeddings
                    ):
                        # Delete old rows matching file_path + section
                        session.query(BrainDocument).filter(
                            BrainDocument.file_path == rel_str,
                            BrainDocument.section == section_header,
                        ).delete(synchronize_session=False)

                        doc = BrainDocument(
                            file_path=rel_str,
                            doc_type=doc_type,
                            section=section_header,
                            content=chunk_text,
                            embedding=embedding,
                            indexed_at=datetime.now(),
                        )
                        session.add(doc)
                    session.commit()
                except Exception as db_err:  # pylint: disable=broad-except
                    logger.error("DB write failed for %s: %s", rel_str, db_err)
                    errors.append(f"{rel_str}: db error — {db_err}")
                    continue

            total_chunks += len(final_chunks)
            logger.info("Indexed %s -> %d chunks", rel_str, len(final_chunks))

        except Exception as file_err:  # pylint: disable=broad-except
            logger.error("Failed to process %s: %s", rel_str, file_err)
            errors.append(f"{rel_str}: {file_err}")

    logger.info(
        "Done: %d files, %d chunks, %d embeddings. Skipped: %d files (unchanged).",
        total_files - skipped_files,
        total_chunks,
        total_embeddings,
        skipped_files,
    )
    if errors:
        logger.warning("Errors (%d):", len(errors))
        for err in errors:
            logger.warning("  %s", err)


if __name__ == "__main__":
    main()
