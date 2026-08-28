"""scripts/index_code.py — per-repo source-code crawler + embedder (the `code` corpus).

Layer 2 of the brain RAG stack, alongside ``scripts/index_brain.py`` (Layer 1,
markdown). Where ``index_brain.py`` crawls each ``brain.toml`` manifest repo's
``docs/``/``planning/`` subtrees into ``brain_documents``, this script crawls
each manifest repo's SOURCE tree into ``code_chunks`` — the two never overlap.

Mirrors ``index_brain.py``'s structure deliberately (OR.P task 5): the same
manifest-driven repo discovery (``index_brain._find_brain_root`` /
``index_brain._load_brain_config``, reused rather than re-implemented), the
same incremental ``indexed_at``-vs-``mtime`` skip logic, and the same
``--rebuild``/``--dry-run`` shape. What differs is the unit of work — a
source file split into ``CodeChunkSpec`` objects by
``app.brain.code_chunking.chunk_source`` instead of a markdown file split by
section header — and the upsert key: ``(repo, file_path)`` (every chunk for
a file is replaced together, since a chunk's own key —
``(repo, file_path, start_line)`` per ``CodeChunk``'s unique constraint —
shifts whenever the file's boundaries change).

This script runs from the CLI — it is NOT a workflow node and is NOT run by
Celery.

Usage:
    python scripts/index_code.py [--repo SLUG] [--rebuild] [--dry-run]

Args:
    --repo SLUG    Index only this brain.toml manifest repo (its `slug`).
                   Default: every manifest repo that declares a `repo_path`.
    --rebuild      Disable the per-file incremental skip so every eligible
                   file re-embeds regardless of `indexed_at` vs mtime. Rows
                   for files no longer present are still pruned either way.
    --dry-run      Report the file and chunk counts that would be indexed
                   (respecting the same incremental skip) without calling
                   the embedding backend or writing to the DB.

File discovery: `git ls-files --cached --others --exclude-standard` inside
each repo (so `.gitignore` is honoured for free) when the repo is a git
working tree, else a plain walk that skips `_SKIP_DIR_NAMES`. Either way,
only extensions in `_SOURCE_EXTENSIONS` are considered, and any file over
`_MAX_FILE_BYTES` (512 KiB) is skipped outright — a generated or minified
asset that slipped past `.gitignore` must not blow up an embedding run on a
single file.
"""

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Ensure app/ and this script's own directory are importable — mirrors
# index_brain.py's lazy sys.path setup so `from brain.code_chunking import
# chunk_source` and `from index_brain import ...` both resolve regardless of
# the caller's CWD.
_SCRIPTS_DIR = Path(__file__).resolve().parent
_APP_DIR = _SCRIPTS_DIR.parent / "app"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

from index_brain import (  # noqa: E402  pylint: disable=wrong-import-position
    BrainConfig,
    _find_brain_root,
    _load_brain_config,
)

from brain.code_chunking import chunk_source  # noqa: E402  pylint: disable=wrong-import-position
from database.code_chunk import CodeChunk  # noqa: E402  pylint: disable=wrong-import-position
from database.session import db_session  # noqa: E402  pylint: disable=wrong-import-position

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

# Files above this size are skipped outright, regardless of extension — a
# generated or minified file (a bundled JS asset, a vendored lockfile that
# slipped past .gitignore) would otherwise blow up a single embedding call.
_MAX_FILE_BYTES = 512 * 1024

# Explicit skip-dir names, applied on TOP of .gitignore (via `git ls-files`)
# so a vendored/build directory is excluded even in a repo whose .gitignore
# does not list it, and so the plain-walk fallback (a non-git repo_path) has
# the same floor of protection.
_SKIP_DIR_NAMES = frozenset(
    {"target", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".git"}
)

# Recognised source extensions across the fleet's languages (per OR.P: Python
# and Rust get real tree-sitter boundary chunking; every other extension in
# this set still gets indexed, just via code_chunking's whole-file fallback —
# "indexed coarsely beats dropped silently" applies here too, not only inside
# the chunker). Extensions NOT in this set (images, lockfiles, `.json`,
# `.toml`, binary assets, …) are not source and are never crawled.
_SOURCE_EXTENSIONS = frozenset(
    {
        ".py",
        ".rs",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".dart",
        ".go",
        ".rb",
        ".java",
        ".kt",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".swift",
        ".sh",
    }
)


def _iter_repo_files(repo_root: Path) -> list[Path]:
    """List every tracked/untracked-but-not-ignored file under `repo_root`.

    Uses `git ls-files --cached --others --exclude-standard` when the repo
    is a git working tree — this honours `.gitignore` without this module
    re-implementing gitignore matching. Falls back to a plain `os.walk` that
    prunes `_SKIP_DIR_NAMES` and dotdirs when there is no `.git` (or `git`
    itself is unavailable), so a non-git repo_path (or a CI sandbox with no
    git binary) still gets *some* crawl rather than an empty one.
    """
    if (repo_root / ".git").exists():
        try:
            proc = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                check=True,
            )
            return [repo_root / line for line in proc.stdout.splitlines() if line]
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            logger.warning(
                "index_code: `git ls-files` failed for %s (%s); falling back to a plain walk",
                repo_root,
                exc,
            )

    result: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo_root):
        dirnames[:] = [
            d for d in dirnames if d not in _SKIP_DIR_NAMES and not d.startswith(".")
        ]
        for fname in filenames:
            result.append(Path(dirpath) / fname)
    return result


def _eligible_files(repo_root: Path) -> list[Path]:
    """Candidate source files under `repo_root`: right extension, right size, not vendored."""
    files: list[Path] = []
    for candidate in _iter_repo_files(repo_root):
        if not candidate.is_file():
            continue
        try:
            rel_parts = candidate.relative_to(repo_root).parts
        except ValueError:
            continue
        if any(part in _SKIP_DIR_NAMES for part in rel_parts):
            continue
        if candidate.suffix not in _SOURCE_EXTENSIONS:
            continue
        try:
            if candidate.stat().st_size > _MAX_FILE_BYTES:
                logger.warning(
                    "index_code: skipping %s — over the %d byte ceiling",
                    candidate,
                    _MAX_FILE_BYTES,
                )
                continue
        except OSError:
            continue
        files.append(candidate)
    return sorted(files)


def _index_repo(
    repo_slug: str,
    repo_root: Path,
    embedding_svc,
    *,
    rebuild: bool,
    dry_run: bool,
) -> dict[str, int]:
    """Crawl, chunk, (optionally) embed, and upsert one repo's source tree.

    Incremental by default: a file whose most-recent `code_chunks` row
    `indexed_at` is newer than the file's own mtime is skipped, mirroring
    `index_brain.py`'s per-file skip. `--rebuild` disables that check so
    every eligible file re-embeds. Either way, rows for files that no longer
    exist under `repo_root` are pruned at the end of the run — a deleted
    source file must not haunt the corpus.

    `embedding_svc` is `None` exactly when `dry_run` is True (`main()` never
    constructs one in that case); a chunk/embed count is still reported for
    a dry run, just without an embedding API call.

    Returns a stats dict: `files` (indexed this run), `chunks` (emitted),
    `embeddings` (vectors produced — 0 on a dry run), `skipped` (unchanged,
    incremental hit), `pruned_files` (deleted-file rows removed).
    """
    stats = {"files": 0, "chunks": 0, "embeddings": 0, "skipped": 0, "pruned_files": 0}
    current_rel_paths: set[str] = set()

    for file_path in _eligible_files(repo_root):
        rel_str = file_path.relative_to(repo_root).as_posix()
        current_rel_paths.add(rel_str)

        try:
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        except OSError as exc:
            logger.warning("index_code: cannot stat %s: %s", rel_str, exc)
            continue

        if not rebuild:
            with next(db_session()) as session:  # type: ignore[arg-type]
                existing = (
                    session.query(CodeChunk)
                    .filter(CodeChunk.repo == repo_slug, CodeChunk.file_path == rel_str)
                    .order_by(CodeChunk.indexed_at.desc())
                    .first()
                )
                if existing is not None and existing.indexed_at is not None:
                    if existing.indexed_at > mtime:
                        stats["skipped"] += 1
                        continue

        try:
            text = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as exc:
            logger.warning("index_code: skipping unreadable file %s: %s", rel_str, exc)
            continue

        chunks = chunk_source(text, file_path=rel_str)
        stats["files"] += 1
        stats["chunks"] += len(chunks)

        if dry_run:
            logger.info("Would index %s -> %d chunk(s)", rel_str, len(chunks))
            continue

        try:
            # strict=True: an embedding-count mismatch must fail loudly, never
            # silently misalign chunk<->embedding rows (mirrors index_brain.py).
            embeddings = embedding_svc.embed_batch([c.content for c in chunks])
        except Exception as exc:  # pylint: disable=broad-except
            logger.error("index_code: embedding failed for %s: %s", rel_str, exc)
            continue
        stats["embeddings"] += len(embeddings)

        with next(db_session()) as session:  # type: ignore[arg-type]
            # Every chunk for this file is replaced together: a chunk's own
            # unique key (repo, file_path, start_line) shifts whenever the
            # file's boundaries change, so a partial per-chunk upsert could
            # leave stale rows from the previous boundary layout behind.
            session.query(CodeChunk).filter(
                CodeChunk.repo == repo_slug, CodeChunk.file_path == rel_str
            ).delete(synchronize_session=False)

            indexed_at = datetime.now()
            for spec, embedding in zip(chunks, embeddings, strict=True):
                session.add(
                    CodeChunk(
                        repo=repo_slug,
                        file_path=rel_str,
                        language=spec.language,
                        symbol_name=spec.symbol_name,
                        symbol_kind=spec.symbol_kind,
                        start_line=spec.start_line,
                        end_line=spec.end_line,
                        content=spec.content,
                        embedding=embedding,
                        embedding_model=embedding_svc.stamp,
                        section=spec.section,
                        indexed_at=indexed_at,
                    )
                )
            session.commit()

        logger.info("Indexed %s -> %d chunk(s)", rel_str, len(chunks))

    if not dry_run:
        with next(db_session()) as session:  # type: ignore[arg-type]
            existing_paths = {
                row[0]
                for row in session.query(CodeChunk.file_path)
                .filter(CodeChunk.repo == repo_slug)
                .distinct()
                .all()
            }
            stale = existing_paths - current_rel_paths
            if stale:
                deleted = (
                    session.query(CodeChunk)
                    .filter(CodeChunk.repo == repo_slug, CodeChunk.file_path.in_(stale))
                    .delete(synchronize_session=False)
                )
                session.commit()
                stats["pruned_files"] = len(stale)
                logger.info(
                    "%s: pruned %d row(s) for %d deleted file(s)", repo_slug, deleted, len(stale)
                )

    return stats


def _select_repos(config: BrainConfig, only_slug: str | None) -> list[dict]:
    """Manifest repos eligible for source crawling: any `[[repos]]` entry with a `repo_path`.

    Raises `SystemExit` when `only_slug` is given but matches no manifest repo —
    a typo in `--repo` should fail loudly, not silently index nothing.
    """
    repos = [r for r in config.repos if r.get("slug") and r.get("repo_path")]
    if only_slug is not None:
        repos = [r for r in repos if r["slug"] == only_slug]
        if not repos:
            raise SystemExit(f"Error: no brain.toml manifest repo with slug {only_slug!r}")
    return repos


def main(argv: list[str] | None = None) -> int:
    """Entry point for the fleet source-code indexer.

    Returns `0` on a clean run. There is currently no per-file failure signal
    distinct from a logged warning (embedding/DB errors are logged and the
    file is skipped for this run — it will be retried on the next run since
    its `indexed_at` is never advanced), mirroring how `index_brain.py`
    reports failures without aborting the whole crawl.
    """
    parser = argparse.ArgumentParser(
        description="Index fleet source code into code_chunks (the `code` corpus)."
    )
    parser.add_argument(
        "--repo",
        default=None,
        metavar="SLUG",
        help="Index only this brain.toml manifest repo (its slug). "
        "Default: every manifest repo that declares a repo_path.",
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Disable the per-file incremental skip so every eligible file re-embeds "
        "regardless of indexed_at vs mtime.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report file/chunk counts that would be indexed without calling the "
        "embedding backend or writing to the DB.",
    )
    args = parser.parse_args(argv)

    brain_path = _find_brain_root(Path(__file__))
    if brain_path is None:
        raise SystemExit("Error: could not resolve a brain.toml root by walking up from this script")
    config = _load_brain_config(brain_path)
    repos = _select_repos(config, args.repo)

    embedding_svc = None
    if not args.dry_run:
        from services.embedding_service import EmbeddingService  # pylint: disable=import-outside-toplevel

        embedding_svc = EmbeddingService()

    total = {"files": 0, "chunks": 0, "embeddings": 0, "skipped": 0, "pruned_files": 0}
    for repo in repos:
        slug = repo["slug"]
        repo_root = (brain_path / repo["repo_path"]).resolve()
        if not repo_root.is_dir():
            logger.warning("index_code: repo root missing for %s: %s", slug, repo_root)
            continue

        stats = _index_repo(slug, repo_root, embedding_svc, rebuild=args.rebuild, dry_run=args.dry_run)
        for key in total:
            total[key] += stats[key]
        logger.info(
            "%s: %d files, %d chunks, %d embeddings. Skipped: %d (unchanged). Pruned: %d.",
            slug,
            stats["files"],
            stats["chunks"],
            stats["embeddings"],
            stats["skipped"],
            stats["pruned_files"],
        )

    logger.info(
        "Done: %d files, %d chunks, %d embeddings across %d repo(s). "
        "Skipped: %d (unchanged). Pruned: %d.",
        total["files"],
        total["chunks"],
        total["embeddings"],
        len(repos),
        total["skipped"],
        total["pruned_files"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
