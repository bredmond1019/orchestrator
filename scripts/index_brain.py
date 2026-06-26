"""index_brain.py — Brain corpus ingestion script (Layer 1 of the brain RAG stack).

Crawls the company brain (agentic-portfolio) markdown files, chunks each file
by section header (H2/H3), embeds the chunks via Voyage AI, and stores rows in
the ``brain_documents`` pgvector table for later semantic retrieval.

This script runs from the CLI — it is NOT a workflow node and is NOT run by Celery.

Usage:
    python scripts/index_brain.py [--brain-path PATH] [--rebuild] [--dry-run]
    python scripts/index_brain.py --prune-paths PATH [PATH ...] [--dry-run]

Args:
    --brain-path PATH    Path to the brain repo root. Defaults to the parent of the
                         orchestration repo (the brain root) — resolved from this
                         script's location, so it is independent of the current
                         working directory.
    --rebuild            Drop all non-diagnostic rows and re-index from scratch.
    --dry-run            Print what would be indexed (or pruned) without writing to
                         DB or calling the embedding API.
    --prune-paths PATH … Delete brain_documents rows for these deleted/renamed-away
                         file paths, then exit. Surgical orphan cleanup with no
                         embedding call; driven by the brain repo's freshness hook.
"""

import argparse
import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import frontmatter

# ---------------------------------------------------------------------------
# Corpus definition: (relative-path-in-brain-repo, doc_type)
# ---------------------------------------------------------------------------
CORPUS: list[tuple[str, str]] = [
    # Decisions (all ADRs + index)
    ("docs/decisions", "decision"),
    # Projects (all project context docs)
    ("docs/projects", "project"),
    # Navigation and orientation
    ("README.md", "meta"),
    ("docs/index.md", "meta"),
    ("docs/progress.md", "meta"),
    ("CLAUDE.md", "meta"),
    # Career and business
    ("docs/career.md", "career"),
    ("docs/profile-and-pitch.md", "career"),
    ("docs/brand.md", "brand"),
    ("docs/linkedin.md", "content"),
    ("docs/business", "business"),
    # Content backlog
    ("docs/content", "content"),
    # Diagnostic service offering (was: planning/the-diagnostic — does not exist)
    ("docs/diagnostic", "diagnostic"),
    # Infrastructure and integrations
    ("docs/infrastructure.md", "meta"),
    ("docs/okf-frontmatter.md", "meta"),
    ("docs/integrations", "meta"),
    # Bastion program planning
    ("planning/bastion-product", "plan"),
    # cross-repo program; plan stays in brain (multi-repo). The bastion-ui/
    # Flutter sub-repo is gitignored — not in corpus.
    ("planning/bastion-ui", "plan"),
    # after Block A relocates architecture.md + ownership.md here
    ("docs/bastion", "meta"),
    ("planning/status.md", "meta"),
    # Archived — indexed but filtered out of default retrieval (status: archived)
    ("planning/archived", "archived"),
    # NOTE: memory/ + MEMORY.md are intentionally NOT in the corpus — they live
    # outside the brain repo (harness-managed auto-memory) and drift; the repo
    # docs are the authoritative current-state source. See brain-rag-improvements
    # plan, Block E1.
]

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Brain repo root = parent of the orchestration repo. Derived from this script's
# location (scripts/index_brain.py) so the default is correct regardless of the
# current working directory.
_DEFAULT_BRAIN_PATH = Path(__file__).resolve().parent.parent.parent

# ---------------------------------------------------------------------------
# OKF controlled vocabularies (from docs/okf-frontmatter.md + D27)
# ---------------------------------------------------------------------------
_VALID_LAYERS: frozenset[str] = frozenset(
    [
        "brain",
        "engine",
        "factory",
        "console",
        "surface",  # was "surfaces" — no doc uses the plural
        "infra",  # add — used by infrastructure docs
        "business",  # add — used by business docs
        "content",  # add — used by content docs
        "meta",  # add — used by navigation/meta docs
    ]
)
_VALID_PROJECTS: frozenset[str] = frozenset(
    [
        "python-orchestration",
        "rag-engine-rs",
        "claude-sdk-rs",
        "workflow-engine-rs",
        "bastion",
        "bastion-ui",  # add — used in docs/projects/bastion-ui.md + planning/bastion-ui/
        "markdown-engine-validator",
        "price-scout",
        "learn-ai",
        "base-template",
        "brain",  # add — used in ~44 docs
        "bella",  # add — used in docs/projects/bella.md
        "amistad",  # add — used in docs/projects/amistad.md
    ]
)
_VALID_STATUSES: frozenset[str] = frozenset(
    ["active", "draft", "archived", "deprecated", "superseded"]  # add "superseded"
)

_HEADER_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


def parse_document(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from a markdown document.

    Uses ``python-frontmatter`` to split the document into its metadata
    dictionary and the body text with the YAML block stripped.  A document
    with no frontmatter delimiter returns an empty metadata dict and the
    original text unchanged.

    Args:
        text: Raw file contents, possibly starting with a YAML frontmatter block.

    Returns:
        A ``(metadata, body)`` tuple where ``body`` contains no YAML delimiters
        or frontmatter fields.
    """
    post = frontmatter.loads(text)
    return dict(post.metadata), post.content


def normalize_metadata(meta: dict, file_path: Path, brain_path: Path) -> dict:
    """Normalise raw frontmatter metadata to the six OKF filterable fields.

    Applies typed defaults, coerces bare strings to lists where the schema
    expects lists, derives ``doc_id`` from the filename stem when absent, and
    logs (never raises) out-of-vocabulary values.

    Args:
        meta:       Raw metadata dict returned by ``parse_document``.
        file_path:  Absolute path to the source markdown file.
        brain_path: Absolute path to the brain repo root (used for rel-path
                    derivation only).

    Returns:
        A dict with keys: ``doc_id``, ``layer``, ``project``, ``status``,
        ``keywords``, ``related``.  Values are ``None`` when absent, keeping
        the DB columns nullable.
    """
    # doc_id: derive from filename stem when absent
    doc_id: str | None = meta.get("doc_id") or meta.get("id") or None
    if not doc_id:
        doc_id = file_path.stem

    # layer: coerce bare string → single-element list; lowercase before the
    # membership check and for storage (the real warning source was case —
    # e.g. "Surface" vs "surface" — not a vocabulary gap).
    raw_layer = meta.get("layer")
    layer: list[str] | None = None
    if raw_layer is not None:
        if isinstance(raw_layer, str):
            raw_layer = [raw_layer]
        layer = [str(v).strip().lower() for v in raw_layer]
        invalid = [v for v in layer if v not in _VALID_LAYERS]
        if invalid:
            logger.warning(
                "Out-of-vocabulary layer value(s) in %s: %s",
                file_path.relative_to(brain_path) if brain_path else file_path,
                invalid,
            )

    # project: scalar string, case-normalized
    raw_project = meta.get("project")
    project: str | None = str(raw_project).strip().lower() if raw_project else None
    if project and project not in _VALID_PROJECTS:
        logger.warning(
            "Out-of-vocabulary project value in %s: %s",
            file_path.relative_to(brain_path) if brain_path else file_path,
            project,
        )

    # status: scalar string, case-normalized ("Draft" → "draft", "Active" → "active")
    raw_status = meta.get("status")
    status: str | None = str(raw_status).strip().lower() if raw_status else None
    if status and status not in _VALID_STATUSES:
        logger.warning(
            "Out-of-vocabulary status value in %s: %s",
            file_path.relative_to(brain_path) if brain_path else file_path,
            status,
        )

    # keywords: list of strings
    raw_keywords = meta.get("keywords")
    keywords: list[str] | None = None
    if raw_keywords is not None:
        if isinstance(raw_keywords, str):
            raw_keywords = [raw_keywords]
        keywords = [str(v) for v in raw_keywords] or None

    # related: list of strings (paths)
    raw_related = meta.get("related")
    related: list[str] | None = None
    if raw_related is not None:
        if isinstance(raw_related, str):
            raw_related = [raw_related]
        related = [str(v) for v in raw_related] or None

    return {
        "doc_id": doc_id,
        "layer": layer,
        "project": project,
        "status": status,
        "keywords": keywords,
        "related": related,
    }


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


def _prune_paths(paths: list[str], brain_path: Path, dry_run: bool = False) -> None:
    """Delete ``brain_documents`` rows for files removed or renamed away.

    Surgical orphan cleanup: the incremental indexer keys its upsert on
    ``file_path + section``, so when a file is deleted or renamed its old rows
    are never revisited and linger as stale retrieval hits.  This deletes every
    row whose ``file_path`` matches one of ``paths`` — no embedding, no API call.

    Diagnostic rows (``client_slug`` set) are preserved, mirroring the
    ``--rebuild`` protection; if any matched a warning is logged so they can be
    handled by hand.

    Args:
        paths:      File paths to prune, relative to the brain root (absolute
                    paths under the brain root are accepted and relativised).
        brain_path: Absolute path to the brain repo root.
        dry_run:    When True, report what would be deleted without writing.
    """
    from database.brain_document import BrainDocument
    from database.session import db_session

    # Normalise to brain-root-relative strings to match the stored file_path.
    rel_paths: list[str] = []
    for raw in paths:
        p = Path(raw)
        if p.is_absolute():
            try:
                p = p.relative_to(brain_path)
            except ValueError:
                pass
        rel_paths.append(str(p))

    with next(db_session()) as session:  # type: ignore[arg-type]
        base = session.query(BrainDocument).filter(
            BrainDocument.file_path.in_(rel_paths)
        )
        protected = base.filter(BrainDocument.client_slug.isnot(None)).count()
        prunable = base.filter(BrainDocument.client_slug.is_(None))

        if dry_run:
            count = prunable.count()
            logger.info(
                "Dry run — would prune %d row(s) for %d path(s): %s",
                count,
                len(rel_paths),
                ", ".join(rel_paths),
            )
        else:
            deleted = prunable.delete(synchronize_session=False)
            session.commit()
            logger.info(
                "--prune-paths: deleted %d row(s) for %d path(s): %s",
                deleted,
                len(rel_paths),
                ", ".join(rel_paths),
            )

    if protected:
        logger.warning(
            "--prune-paths: kept %d diagnostic row(s) (client_slug set) — prune by hand if intended",
            protected,
        )


def main(argv: list[str] | None = None) -> None:
    """Entry point for the brain corpus indexer."""
    parser = argparse.ArgumentParser(
        description="Index the company brain markdown corpus into brain_documents table."
    )
    parser.add_argument(
        "--brain-path",
        default=str(_DEFAULT_BRAIN_PATH),
        help=f"Path to the brain repo root (default: {_DEFAULT_BRAIN_PATH})",
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
    parser.add_argument(
        "--prune-paths",
        nargs="+",
        metavar="PATH",
        help="Delete brain_documents rows for these (deleted/renamed-away) file paths, "
        "then exit. Surgical orphan cleanup — no embedding, no API call. "
        "Used by the brain repo's delete/rename freshness hook.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Process only the first N corpus files. Use with --rebuild for the "
        "pre-rebuild write-path check (embed a 2-3 file subset and confirm "
        "is_section_title is a True/False mix + title/description populate) "
        "before paying for the full corpus.",
    )
    args = parser.parse_args(argv)

    brain_path = _resolve_brain_path(args.brain_path)

    # Set up sys.path for imports from app/
    app_dir = Path(__file__).resolve().parent.parent / "app"
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    # --prune-paths: surgical orphan cleanup, exits before any embedding work
    # (so it needs no VOYAGE_API_KEY and never touches the corpus walk).
    if args.prune_paths:
        _prune_paths(args.prune_paths, brain_path, dry_run=args.dry_run)
        return

    # Collect files
    files = _collect_files(brain_path)
    if args.limit is not None:
        files = files[: args.limit]
        logger.info("--limit %d: processing first %d file(s) only", args.limit, len(files))

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

            # Read, parse frontmatter, and chunk the body only (no YAML)
            raw_content = file_path.read_text(encoding="utf-8")
            meta, body = parse_document(raw_content)
            norm = normalize_metadata(meta, file_path, brain_path)
            context_prefix = build_context_prefix(meta)
            section_chunks = chunk_by_section(body)

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

            # Embed text: prefix + chunk (prefix is semantic context; not stored).
            # Stored content is the clean chunk text (c[1]) — taken directly from
            # final_chunks in the upsert loop below, no YAML and no prefix.
            embed_texts = [context_prefix + c[1] for c in final_chunks]

            # Batch embed
            try:
                embeddings = embedding_svc.embed_batch(embed_texts)
                total_embeddings += len(embeddings)
            except Exception as embed_err:  # pylint: disable=broad-except
                logger.error("Embedding failed for %s: %s", rel_str, embed_err)
                errors.append(f"{rel_str}: embed error — {embed_err}")
                continue

            # Upsert: delete existing rows for this file+section, insert new
            with next(db_session()) as session:  # type: ignore[arg-type]
                try:
                    # strict=True: a Voyage count mismatch must fail loudly here,
                    # never silently truncate into misaligned chunk↔embedding rows.
                    for (section_header, chunk_text), embedding in zip(
                        final_chunks, embeddings, strict=True
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
                            doc_id=norm["doc_id"],
                            layer=norm["layer"],
                            project=norm["project"],
                            status=norm["status"],
                            keywords=norm["keywords"],
                            related=norm["related"],
                            is_section_title=_is_header_only_chunk(
                                section_header, chunk_text
                            ),
                            title=meta.get("title") or None,
                            description=meta.get("description") or None,
                            # content_tsv is a generated column — Postgres
                            # maintains it; NEVER set it here.
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
