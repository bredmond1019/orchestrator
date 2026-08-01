"""app/brain/ops.py — the Brain write/ops core (embed, ingest, prune, refresh, stale, routine).

Wraps `scripts/index_brain.py`'s incremental content-index path and the
`mev emit-graph | scripts/load_brain_edges.py::load_edges` structural-edge path
behind one set of typed functions, so `syn` (`app/brain/cli.py`) and the brain
repo's post-commit freshness hook share a single implementation. No second
chunk->embed->write path is introduced here (CLAUDE.md rule 10).
"""

import json
import logging
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from brain import _bootstrap  # noqa: F401  pylint: disable=unused-import

logger = logging.getLogger(__name__)


class UnknownRoutineError(Exception):
    """Raised when `run_routine` is given a name absent from the registry."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Unknown routine: {name!r}. Known: {sorted(ROUTINES)}")
        self.name = name


class MevUnavailableError(Exception):
    """Raised when the `mev` binary is not on PATH for an edge refresh."""


def embed_paths(paths: list[str], *, force: bool = False, brain_path: str | None = None) -> dict:
    """Re-embed exactly the named files via `index_brain`'s `--only-paths` path.

    No second chunk->embed->write implementation — this shells straight into
    `index_brain.main()`, which already carries the incremental-skip logic.

    Args:
        paths: File paths to restrict indexing to (forwarded to `--only-paths`).
        force: Disable the per-file incremental skip so the named paths fully
            re-embed, regardless of their existing `indexed_at`.
        brain_path: Optional brain root override (forwarded to `--brain-path`).

    Returns:
        A summary dict: `{"embedded": [...], "forced": bool}`.
    """
    import index_brain  # pylint: disable=import-outside-toplevel,import-error

    argv: list[str] = ["--only-paths", *paths]
    if force:
        argv.append("--force")
    if brain_path:
        argv += ["--brain-path", brain_path]
    index_brain.main(argv)
    return {"embedded": list(paths), "forced": force}


def ingest_dir(directory: str, *, force: bool = False, brain_path: str | None = None) -> dict:
    """Index every on-disk markdown file under `directory` via the `index_brain` path.

    This is on-disk *file* indexing (frontmatter-parsing, `doc_type`
    classification, `authored_at` from mtime) — a different concern from
    `app/brain/ingest.py::ingest_artifact`'s arbitrary-content API path. Do
    not route this through the OR.Q ingest core.

    Args:
        directory: Root directory to collect `*.md` files under.
        force: Forwarded to `embed_paths` — disables the incremental skip.
        brain_path: Optional brain root override.

    Returns:
        A summary dict: `{"ingested": [...], "forced": bool}`.

    Raises:
        NotADirectoryError: `directory` does not exist or is not a directory.
    """
    root = Path(directory)
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {directory}")

    files = [str(p) for p in sorted(root.rglob("*.md"))]
    if not files:
        return {"ingested": [], "forced": force}

    embed_paths(files, force=force, brain_path=brain_path)
    return {"ingested": files, "forced": force}


def prune_paths(paths: list[str], *, dry_run: bool = False, brain_path: str | None = None) -> dict:
    """Delete `brain_documents` rows for deleted/renamed-away file paths.

    Surgical cleanup — shells into `index_brain`'s `--prune-paths` mode (no
    embedding, no API call). The single implementation shared by `syn prune`
    and the brain repo's post-commit delete/rename freshness hook, which
    previously called `scripts/index_brain.py --prune-paths` directly.

    Args:
        paths: File paths (brain-root-relative or absolute) to prune.
        dry_run: Report what would be deleted without writing.
        brain_path: Optional brain root override (forwarded to `--brain-path`).

    Returns:
        A summary dict: `{"pruned": [...], "dry_run": bool}`.
    """
    import index_brain  # pylint: disable=import-outside-toplevel,import-error

    argv: list[str] = ["--prune-paths", *paths]
    if dry_run:
        argv.append("--dry-run")
    if brain_path:
        argv += ["--brain-path", brain_path]
    index_brain.main(argv)
    return {"pruned": list(paths), "dry_run": dry_run}


def refresh_edges(brain_path: Path) -> int:
    """Run `mev emit-graph --json <brain_path>` and load the payload into `brain_edges`.

    Moved here from `scripts/refresh_brain.py` (task 2) so `syn refresh`, the
    `refresh_brain.py` shim, and `syn routine refresh` share one edge-reload
    implementation.

    Args:
        brain_path: Path to the brain repo root to crawl.

    Returns:
        The number of edge rows loaded.

    Raises:
        MevUnavailableError: the `mev` binary is not on PATH.
    """
    from load_brain_edges import load_edges  # pylint: disable=import-outside-toplevel,import-error

    try:
        result = subprocess.run(
            ["mev", "emit-graph", "--json", str(brain_path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise MevUnavailableError("`mev` binary not found on PATH") from exc

    payload = json.loads(result.stdout)

    from database.session import db_session  # pylint: disable=import-outside-toplevel

    with next(db_session()) as session:  # type: ignore[arg-type]
        return load_edges(payload, session)


def refresh(*, rebuild: bool = False, dry_run: bool = False, brain_path: str | None = None) -> dict:
    """Run the content-index step then the edge-reload step, in that order.

    Supersedes `scripts/refresh_brain.py`'s `main()` sequencing — one
    invocation reproduces both freshness paths. `--dry-run` skips the edge
    step entirely (brain_edges has no dry-run equivalent), matching today's
    behavior.

    Args:
        rebuild: Forwarded to `index_brain.main` (`--rebuild`).
        dry_run: Forwarded to `index_brain.main` (`--dry-run`); also skips
            the edge-reload step.
        brain_path: Optional brain root override.

    Returns:
        `{"documents": {...}, "edges": {"loaded": N} | {"skipped": True}}`.
    """
    import index_brain  # pylint: disable=import-outside-toplevel,import-error

    index_argv: list[str] = []
    if brain_path:
        index_argv += ["--brain-path", brain_path]
    if rebuild:
        index_argv.append("--rebuild")
    if dry_run:
        index_argv.append("--dry-run")

    index_brain.main(index_argv)

    if dry_run:
        return {"documents": {"dry_run": True}, "edges": {"skipped": True}}

    resolved = (
        Path(brain_path) if brain_path else index_brain._DEFAULT_BRAIN_PATH  # pylint: disable=protected-access
    )
    loaded = refresh_edges(resolved)
    return {"documents": {"dry_run": False}, "edges": {"loaded": loaded}}


def _changed_files(root: Path, files: list, session) -> list[str]:
    """Content axis: names files whose mtime is newer than their `indexed_at`."""
    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel

    changed: list[str] = []
    for file_path, _doc_type, project_override in files:
        rel = str(file_path.relative_to(root))
        authored_at = datetime.fromtimestamp(file_path.stat().st_mtime)
        query = session.query(BrainDocument).filter(BrainDocument.file_path == rel)
        if project_override is not None:
            query = query.filter(BrainDocument.project == project_override)
        existing = query.order_by(BrainDocument.indexed_at.desc()).first()
        if existing is None or existing.indexed_at is None or authored_at > existing.indexed_at:
            changed.append(rel)
    return changed


def stale(*, brain_path: str | None = None) -> dict:
    """Report content-axis and structure-axis drift. Read-only — no writes.

    Content axis: reuses `index_brain._collect_files` and compares each
    file's mtime to the newest matching `brain_documents.indexed_at` (the
    same comparison `index_brain`'s incremental skip makes, but read-only).
    Structure axis: reuses `brain.pulse.pulse()`'s
    `edges_empty_but_related_exists` flag rather than re-deriving it.

    `ingested/%` rows (synthetic paths written by `app/brain/ingest.py` — no
    on-disk file was ever expected) are exempted from this axis rather than
    silently never surfacing: `index_brain._collect_files` only walks the
    filesystem, so it never yields an `ingested/%` path in the first place —
    they simply cannot appear in `changed`. `syn stale --deep` is what covers
    them (the informational `ingested/` lane in `reconcile.deep_stale`).

    Args:
        brain_path: Optional brain root override.

    Returns:
        `{"changed_files": [...], "edges_stale": bool, "drift": bool}` —
        `drift` is False on an untouched, fully-loaded corpus.
    """
    import index_brain  # pylint: disable=import-outside-toplevel,import-error
    from database.session import db_session  # pylint: disable=import-outside-toplevel

    root = (
        Path(brain_path) if brain_path else index_brain._DEFAULT_BRAIN_PATH  # pylint: disable=protected-access
    )
    config = index_brain._load_brain_config(root)  # pylint: disable=protected-access
    files = index_brain._collect_files(root, config)  # pylint: disable=protected-access

    with next(db_session()) as session:  # type: ignore[arg-type]
        changed = _changed_files(root, files, session)

    from brain.pulse import pulse  # pylint: disable=import-outside-toplevel

    report = pulse()
    edges_stale = report.edges_empty_but_related_exists

    return {
        "changed_files": changed,
        "edges_stale": edges_stale,
        "drift": bool(changed) or edges_stale,
    }


def _delete_orphaned_chunks(chunk_ids: list[str], session) -> int:
    """Delete `content_chunks` rows by id — targeted, provably-orphaned rows only.

    Mirrors `_prune_paths`'s style (exact-match delete, one commit, return the
    count) rather than reusing `GenericRepository.delete`, which is one
    row/one commit at a time and would be needlessly chatty for a batch of
    orphaned chunk ids.

    Args:
        chunk_ids: `ContentChunk.id` values (as returned by
            `reconcile.deep_stale`'s `orphaned_chunks` axis) to delete.
        session: An open SQLAlchemy session.

    Returns:
        The number of rows deleted.
    """
    import uuid as _uuid  # pylint: disable=import-outside-toplevel

    from database.content_chunk import ContentChunk  # pylint: disable=import-outside-toplevel

    ids = [_uuid.UUID(chunk_id) for chunk_id in chunk_ids]
    deleted = session.query(ContentChunk).filter(ContentChunk.id.in_(ids)).delete(
        synchronize_session=False
    )
    session.commit()
    return deleted


def repair_deep_stale(report, *, brain_path: str | None = None) -> dict:
    """Repair the repairable `reconcile.deep_stale` axes using existing primitives only.

    Dispatch, per axis (never touches `client_slug` diagnostic rows — every
    `deep_stale` axis already excludes them):

    - **deleted-but-embedded** -> `prune_paths` (exact paths).
    - **section-orphans** -> no automatic action; a targeted delete of one
      `(file_path, section)` pair is not an existing primitive, so the report
      names the manual follow-up (`refresh(rebuild=True)` / `syn refresh
      --rebuild`) instead of inventing a second write path.
    - **dangling brain_edges** -> `refresh_edges` (reloads the structural
      graph wholesale from `mev emit-graph`).
    - **model mismatch** -> no automatic action; same manual `--rebuild`
      follow-up as section-orphans (repairing in place would mean a second
      embed path, which this module does not introduce).
    - **orphaned content_chunks** -> `_delete_orphaned_chunks` (a targeted
      delete of provably-orphaned rows, mirroring `prune_paths`'s style).

    Detection re-runs after repair so the caller sees the delta, not just the
    actions taken.

    Args:
        report: A `reconcile.ReconcileReport` (typically freshly produced by
            `reconcile.deep_stale`) naming what to repair.
        brain_path: Optional brain root override (forwarded to `prune_paths`,
            `refresh_edges`, and the post-repair `deep_stale` re-check).

    Returns:
        `{"actions": [...], "before": {...}, "after": {...}}` — `before`/
        `after` are `ReconcileReport.to_dict()` snapshots.
    """
    import index_brain  # pylint: disable=import-outside-toplevel,import-error
    from database.session import db_session  # pylint: disable=import-outside-toplevel

    from brain.reconcile import deep_stale  # pylint: disable=import-outside-toplevel

    actions: list[dict] = []

    if report.deleted_but_embedded:
        prune_paths(list(report.deleted_but_embedded), brain_path=brain_path)
        actions.append(
            {
                "axis": "deleted_but_embedded",
                "action": "prune_paths",
                "count": len(report.deleted_but_embedded),
            }
        )

    if report.section_orphans:
        actions.append(
            {
                "axis": "section_orphans",
                "action": "manual --rebuild",
                "count": len(report.section_orphans),
            }
        )

    if report.dangling_edges:
        root = Path(brain_path) if brain_path else index_brain._DEFAULT_BRAIN_PATH  # pylint: disable=protected-access
        loaded = refresh_edges(root)
        actions.append(
            {"axis": "dangling_edges", "action": "refresh_edges", "loaded": loaded}
        )

    if report.model_mismatch:
        actions.append(
            {
                "axis": "model_mismatch",
                "action": "manual --rebuild",
                "count": len(report.model_mismatch),
            }
        )

    if report.orphaned_chunks:
        with next(db_session()) as session:  # type: ignore[arg-type]
            deleted = _delete_orphaned_chunks(report.orphaned_chunks, session)
        actions.append(
            {"axis": "orphaned_chunks", "action": "delete_orphaned_chunks", "count": deleted}
        )

    after = deep_stale(brain_path=brain_path)
    return {"actions": actions, "before": report.to_dict(), "after": after.to_dict()}


def _reconcile_routine() -> dict:
    """`ROUTINES["reconcile"]` body — report-only (a routine must be cron-safe)."""
    from brain.reconcile import deep_stale  # pylint: disable=import-outside-toplevel

    return deep_stale().to_dict()


ROUTINES: dict[str, Callable[[], dict]] = {
    # Lambdas (not direct function refs) so tests can `patch("app.brain.ops.refresh", ...)`
    # / `patch("app.brain.ops.stale", ...)` and have the registry dispatch to the patch —
    # a direct `refresh`/`stale` reference here would bind the original function object
    # at import time, before any patch is applied.
    "refresh": lambda: refresh(),  # pylint: disable=unnecessary-lambda
    "stale": lambda: stale(),  # pylint: disable=unnecessary-lambda
    # Deep drift check, report-only — no `--repair` dispatch from a cron routine.
    "reconcile": lambda: _reconcile_routine(),  # pylint: disable=unnecessary-lambda
}


def run_routine(name: str) -> dict:
    """Run a named chore from the registry — the convention `OR.J`'s cron invokes.

    Args:
        name: A key in `ROUTINES` (e.g. `"refresh"`, `"stale"`).

    Returns:
        The result dict of the underlying routine function.

    Raises:
        UnknownRoutineError: `name` is not a registered routine.
    """
    if name not in ROUTINES:
        raise UnknownRoutineError(name)
    return ROUTINES[name]()
