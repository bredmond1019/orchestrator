"""app/brain/reconcile.py — the Brain's deep corpus/index drift read core.

`app/brain/ops.py::stale` only ever walks the *filesystem* corpus looking for
matching DB rows (a file changed on disk since it was last indexed). It never
walks DB rows looking for the filesystem/edge/embedding state they claim to
still be backed by — so an index can silently diverge from the corpus on five
independent axes and nothing reports it. This module is that inverse check:
`deep_stale()` is a pure, read-only report over `brain_documents`,
`content_chunks`, and `brain_edges` — it never writes, and every count is
derived from a live DB query, never from what a caller requested (the
`ops.py` fabricated-return trap this ticket is explicitly not fixing there).

Axes (see `ReconcileReport`):

1. **deleted-but-embedded** — an indexed `brain_documents.file_path` whose
   file no longer exists on disk under the corpus root. Excludes `ingested/%`
   rows (synthetic paths, no file was ever expected) and `client_slug`
   diagnostic rows (out of scope per the ticket).
2. **section-orphans** — for each still-existing indexed file, a
   `(file_path, section)` pair in the DB that no longer exists in the file's
   *current* section set (`chunking.chunk_by_section`). The upsert keys on
   this pair, so a header rename/removal leaks a row that survives every
   incremental re-index.
3. **orphaned content_chunks** — `content_chunks` has no FK enforcing that a
   `doc_id` group is complete (`StoreChunksNode` commits one chunk at a
   time). This module defines a group's "parent" as its `position == 0`
   chunk — the document-anchor row every `ingest_artifact`-shaped write
   produces first. A `doc_id` group with no `position == 0` row has no live
   parent and every chunk in it is reported orphaned.
4. **dangling brain_edges** — rows with a NULL `target_doc_id` (the loader
   keeps these deliberately, per `load_brain_edges.py`) plus rows whose
   non-null `target_doc_id` matches no `brain_documents.doc_id`.
5. **model mismatch** — `brain_documents`/`content_chunks` rows whose
   `embedding_model` stamp differs from the currently configured
   `EmbeddingService`'s stamp. NULL stamps are counted separately as
   `unstamped_count` (informational — pre-migration rows, not drift).
6. **ingested/ lane** (informational, not drift) — count and authored-at age
   range of `ingested/%` rows, which never appear in the filesystem axes.
7. **ingest ceiling** (informational, not drift) — the inverse of axes 1-2:
   filesystem -> DB instead of DB -> filesystem. `uncovered_files` (enumerated
   on disk, zero DB rows — the recall ceiling `syn eval` can never see past),
   `unparseable_files` (files whose YAML frontmatter fails to parse, whether
   caught during enumeration or while diffing section state), and
   `excluded_count` (files the enumeration itself excluded, broken down by
   reason: `skip_dir`, `leading_underscore`, `ephemeral_filename`). The
   enumeration is always `index_brain._collect_files` — imported, never
   reimplemented, so the two copies of the discovery logic can't drift.

`drift` is True when axes 1-5 report anything; the `ingested/` lane,
`unstamped_count`, and axis 7's three buckets are informational only.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

# `brain._bootstrap` puts `scripts/` on sys.path as an import-time side effect
# (so `scripts/index_brain.py` can be imported bare, as `import index_brain`).
# `brain.ops` needs the identical bootstrap; importing the *shared* leaf
# module here (rather than importing `brain.ops` itself, or duplicating the
# shim) avoids an import cycle — `ops.repair_deep_stale` calls back into this
# module (`deep_stale`), and `brain.ops` <-> `brain.reconcile` would cycle
# even though both call sites are lazy, function-local imports.
from brain import _bootstrap  # noqa: F401  pylint: disable=unused-import


@dataclass
class ReconcileReport:  # pylint: disable=too-many-instance-attributes
    """Structured deep-drift snapshot of the Brain corpus + retrieval substrate."""

    deleted_but_embedded: list[str]
    section_orphans: list[tuple[str, str]]
    orphaned_chunks: list[str]
    dangling_edges: list[dict]
    model_mismatch: list[dict]
    unstamped_count: int
    ingested_count: int
    ingested_min_authored_at: datetime | None
    ingested_max_authored_at: datetime | None
    drift: bool
    uncovered_files: list[str] = field(default_factory=list)
    unparseable_files: list[str] = field(default_factory=list)
    excluded_count: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Return a JSON-serializable dict (datetimes as ISO 8601 strings)."""
        payload = asdict(self)
        for key in ("ingested_min_authored_at", "ingested_max_authored_at"):
            if payload[key] is not None:
                payload[key] = payload[key].isoformat()
        payload["section_orphans"] = [list(pair) for pair in self.section_orphans]
        return payload


def _resolve_root(brain_path: str | None) -> Path:
    import index_brain  # pylint: disable=import-outside-toplevel,import-error

    return Path(brain_path) if brain_path else index_brain._DEFAULT_BRAIN_PATH  # pylint: disable=protected-access


def _deleted_but_embedded(session, root: Path) -> list[str]:
    """Axis 1: indexed file_path rows whose file no longer exists on disk."""
    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel

    rows = (
        session.query(BrainDocument.file_path)
        .filter(BrainDocument.client_slug.is_(None))
        .filter(~BrainDocument.file_path.like("ingested/%"))
        .distinct()
        .all()
    )
    missing = [file_path for (file_path,) in rows if not (root / file_path).exists()]
    return sorted(missing)


def _section_orphans(
    session, root: Path, unparseable: set[str] | None = None
) -> list[tuple[str, str]]:
    """Axis 2: DB (file_path, section) pairs absent from the file's current sections.

    Args:
        unparseable: When supplied, a malformed file's ``file_path`` is added
            here instead of letting ``DocumentParseError`` propagate — this
            is the fix for the bare ``parse_document`` call that used to make
            ``deep_stale`` itself raise on one broken file. The file's other
            (already-indexed) sections are simply skipped for this axis; its
            malformed state surfaces via axis 7's ``unparseable_files``.
    """
    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel
    from index_brain import (  # pylint: disable=import-outside-toplevel,import-error
        DocumentParseError,
        parse_document,
    )

    from brain.chunking import chunk_by_section  # pylint: disable=import-outside-toplevel

    rows = (
        session.query(BrainDocument.file_path, BrainDocument.section)
        .filter(BrainDocument.client_slug.is_(None))
        .filter(~BrainDocument.file_path.like("ingested/%"))
        .distinct()
        .all()
    )
    by_file: dict[str, set[str]] = {}
    for file_path, section in rows:
        by_file.setdefault(file_path, set()).add(section or "")

    orphans: list[tuple[str, str]] = []
    for file_path, db_sections in sorted(by_file.items()):
        full_path = root / file_path
        if not full_path.exists():
            # Already reported as deleted-but-embedded (axis 1) — not a
            # second, redundant finding here.
            continue
        raw_content = full_path.read_text(encoding="utf-8")
        try:
            _meta, body = parse_document(raw_content, file_path=full_path)
        except DocumentParseError:
            if unparseable is not None:
                unparseable.add(file_path)
            continue
        current_sections = {header for header, _body in chunk_by_section(body)}
        for section in sorted(db_sections - current_sections):
            orphans.append((file_path, section))
    return orphans


def _orphaned_chunks(session) -> list[str]:
    """Axis 3: content_chunks doc_id groups with no position==0 anchor row."""
    from database.content_chunk import ContentChunk  # pylint: disable=import-outside-toplevel

    rows = session.query(
        ContentChunk.id, ContentChunk.doc_id, ContentChunk.position
    ).all()
    rooted_doc_ids = {doc_id for _id, doc_id, position in rows if position == 0}
    orphaned = [
        str(chunk_id)
        for chunk_id, doc_id, _position in rows
        if doc_id not in rooted_doc_ids
    ]
    return sorted(orphaned)


def _dangling_edges(session) -> list[dict]:
    """Axis 4: NULL-target edges, plus non-null targets resolving to no document."""
    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel
    from database.brain_edge import BrainEdge  # pylint: disable=import-outside-toplevel

    known_doc_ids = {
        doc_id
        for (doc_id,) in session.query(BrainDocument.doc_id).filter(
            BrainDocument.doc_id.isnot(None)
        )
    }
    dangling = [
        {
            "source_doc_id": edge.source_doc_id,
            "to_ref": edge.to_ref,
            "target_doc_id": edge.target_doc_id,
        }
        for edge in session.query(BrainEdge).all()
        if edge.target_doc_id is None or edge.target_doc_id not in known_doc_ids
    ]
    return dangling


def _model_mismatch(session, expected_stamp: str) -> tuple[list[dict], int]:
    """Axis 5: rows whose embedding_model stamp differs from the configured service.

    NULL stamps are counted separately (`unstamped_count`) — they are
    pre-migration rows, not drift.
    """
    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel
    from database.content_chunk import ContentChunk  # pylint: disable=import-outside-toplevel

    mismatches: list[dict] = []
    unstamped = 0

    for row_id, file_path, stamp in session.query(
        BrainDocument.id, BrainDocument.file_path, BrainDocument.embedding_model
    ):
        if stamp is None:
            unstamped += 1
        elif stamp != expected_stamp:
            mismatches.append(
                {
                    "table": "brain_documents",
                    "id": str(row_id),
                    "file_path": file_path,
                    "embedding_model": stamp,
                }
            )

    for row_id, doc_id, stamp in session.query(
        ContentChunk.id, ContentChunk.doc_id, ContentChunk.embedding_model
    ):
        if stamp is None:
            unstamped += 1
        elif stamp != expected_stamp:
            mismatches.append(
                {
                    "table": "content_chunks",
                    "id": str(row_id),
                    "doc_id": str(doc_id),
                    "embedding_model": stamp,
                }
            )

    return mismatches, unstamped


def _ingested_lane(session) -> tuple[int, datetime | None, datetime | None]:
    """Axis 6 (informational): count + authored_at age range of ingested/% rows."""
    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel
    from sqlalchemy import func  # pylint: disable=import-outside-toplevel

    ingested_query = session.query(BrainDocument).filter(
        BrainDocument.file_path.like("ingested/%")
    )
    count = ingested_query.count()
    if count == 0:
        return 0, None, None

    min_at = (
        session.query(func.min(BrainDocument.authored_at))  # pylint: disable=not-callable
        .filter(BrainDocument.file_path.like("ingested/%"))
        .scalar()
    )
    max_at = (
        session.query(func.max(BrainDocument.authored_at))  # pylint: disable=not-callable
        .filter(BrainDocument.file_path.like("ingested/%"))
        .scalar()
    )
    return count, min_at, max_at


def _load_config_for_root(root: Path):
    """Load ``brain.toml`` at ``root``; ``None`` when it's not a real brain root.

    Test fixtures exercise the other six axes against throwaway ``tmp_path``
    roots that carry no ``brain.toml`` — axis 7 degrades to empty results
    there (mirroring how a nonexistent brain root is already tolerated by the
    other axes) rather than raising ``SystemExit``, which is what
    ``index_brain._load_brain_config`` does on a missing manifest.
    """
    import index_brain  # pylint: disable=import-outside-toplevel,import-error

    config_file = root / index_brain._BRAIN_CONFIG_FILENAME  # pylint: disable=protected-access
    if not config_file.is_file():
        return None
    return index_brain._load_brain_config(root)  # pylint: disable=protected-access


def _repo_candidate_dirs(root: Path, config, containers: frozenset[str]) -> list[tuple[Path, Path]]:
    """The sub-repo half of axis 7's candidate directories: each manifest
    repo's ``planning/`` (non-tier-containers only) and ``docs/`` trees,
    paired with the root each is relative to.
    """
    candidate_dirs: list[tuple[Path, Path]] = []
    for repo in config.repos:
        slug = repo.get("slug")
        repo_path = repo.get("repo_path")
        if not slug or not repo_path or repo_path == ".":
            continue
        repo_root = (root / repo_path).resolve()
        if not repo_root.is_dir():
            continue
        if slug not in containers:
            planning_dir = repo_root / "planning"
            if planning_dir.is_dir():
                candidate_dirs.append((planning_dir, repo_root))
        docs_dir = repo_root / "docs"
        if docs_dir.is_dir():
            candidate_dirs.append((docs_dir, repo_root))
    return candidate_dirs


def _excluded_counts(root: Path, config, included: set[Path]) -> dict[str, int]:
    """Axis 7 (part): why the enumeration excluded a file, broken down by reason.

    Walks the same candidate directories :func:`index_brain._collect_files`
    walks (root corpus subtrees, tier ``docs/``, sub-repo ``planning/`` and
    ``docs/``) but only to *explain* an exclusion already made by that
    function — the exclusion **predicates** (``_is_skipped``,
    ``_EPHEMERAL_FILENAMES``, the leading-underscore rule) are imported from
    ``index_brain``, never reimplemented, so the two copies cannot drift.
    ``included`` (the file set ``_collect_files`` actually returned) is the
    source of truth for what was *not* excluded.
    """
    from index_brain import (  # pylint: disable=import-outside-toplevel,import-error
        _CORPUS_SUBTREES,
        _EPHEMERAL_FILENAMES,
        _corpus_roots,
        _is_skipped,
        _tier_container_slugs,
    )

    counts = {"skip_dir": 0, "leading_underscore": 0, "ephemeral_filename": 0}

    def _reason(name: str, rel: str) -> str | None:
        if name.startswith("_"):
            return "leading_underscore"
        if name in _EPHEMERAL_FILENAMES:
            return "ephemeral_filename"
        if _is_skipped(rel, config.skip_dirs):
            return "skip_dir"
        return None

    candidate_dirs: list[tuple[Path, Path]] = [
        (corpus_root / subtree, corpus_root)
        for corpus_root in _corpus_roots(root, config)
        for subtree in _CORPUS_SUBTREES
        if (corpus_root / subtree).is_dir()
    ]
    candidate_dirs.extend(
        _repo_candidate_dirs(root, config, _tier_container_slugs(config))
    )

    seen_candidates: set[Path] = set()
    for base, rel_root in candidate_dirs:
        for md_file in base.rglob("*.md"):
            if md_file in seen_candidates or md_file in included:
                continue
            seen_candidates.add(md_file)
            rel = md_file.relative_to(rel_root).as_posix()
            reason = _reason(md_file.name, rel)
            if reason:
                counts[reason] += 1
    return counts


def _ingest_ceiling(
    session, root: Path
) -> tuple[list[str], list[str], dict[str, int]]:
    """Axis 7: the filesystem -> DB gap none of axes 1-6 can see.

    Enumerates what the corpus *should* contain via
    ``index_brain._collect_files`` (never reimplemented — see the module
    docstring), diffs it against ``brain_documents.file_path``, and reports:

    - ``uncovered_files`` — enumerated on disk, zero DB rows. The recall
      ceiling ``syn eval`` can never see past.
    - ``unparseable_files`` — files ``index_brain`` itself flagged during
      enumeration (the sub-repo ``docs/`` lane) plus any other enumerated
      file that fails to parse when re-checked here (the three lanes that
      don't parse frontmatter at collection time).
    - ``excluded_count`` — see :func:`_excluded_counts`.

    Degrades to ``([], [], {})`` when ``root`` carries no ``brain.toml`` (a
    throwaway test root, or a brain-path override that isn't a real corpus
    root) — informational only, never raises.
    """
    import index_brain  # pylint: disable=import-outside-toplevel,import-error

    config = _load_config_for_root(root)
    if config is None:
        return [], [], {}

    errors: list[str] = []
    parse_failed_paths: list[str] = []
    files = index_brain._collect_files(  # pylint: disable=protected-access
        root, config, errors, parse_failed_paths
    )

    unparseable: set[str] = set(parse_failed_paths)
    enumerated: set[str] = set()
    included_paths: set[Path] = set()
    for abs_path, _doc_type, _override in files:
        included_paths.add(abs_path)
        rel = abs_path.relative_to(root).as_posix()
        enumerated.add(rel)
        if rel in unparseable:
            continue
        try:
            raw_content = abs_path.read_text(encoding="utf-8")
            index_brain.parse_document(raw_content, file_path=abs_path)
        except index_brain.DocumentParseError:
            unparseable.add(rel)
        except OSError:
            # File vanished between enumeration and read — not this axis's
            # concern; axis 1 (deleted-but-embedded) covers deletion.
            continue

    from database.brain_document import BrainDocument  # pylint: disable=import-outside-toplevel

    db_paths = {
        file_path
        for (file_path,) in session.query(BrainDocument.file_path)
        .filter(BrainDocument.client_slug.is_(None))
        .distinct()
        .all()
    }

    uncovered_files = sorted((enumerated - unparseable) - db_paths)
    excluded_count = _excluded_counts(root, config, included_paths)

    return uncovered_files, sorted(unparseable), excluded_count


def deep_stale(
    *,
    brain_path: str | None = None,
    session=None,
    embedding_service=None,
) -> ReconcileReport:
    """Report the five deep-drift axes plus the ingested/ lane and the ingest
    ceiling. Read-only — no writes.

    Args:
        brain_path: Optional brain root override (defaults to
            `index_brain._DEFAULT_BRAIN_PATH`); used to resolve on-disk file
            existence and current section sets for axes 1-2, and to
            enumerate the corpus for axis 7. Axis 7 degrades to empty
            results when `brain_path` carries no `brain.toml` (e.g. a
            throwaway test root).
        session: An open SQLAlchemy session (injected; opened via
            `database.session.db_session` when omitted).
        embedding_service: An `EmbeddingService` instance (injected;
            constructed with defaults when omitted) — only its `.stamp`
            property is read, no embedding call is made.

    Returns:
        A `ReconcileReport`. `drift` is True when any of axes 1-5 is
        non-empty; the `ingested/` lane, `unstamped_count`, and axis 7's
        `uncovered_files` / `unparseable_files` / `excluded_count` are all
        informational and never contribute to `drift`.
    """
    if session is None:
        from database.session import (  # pylint: disable=import-outside-toplevel
            db_session as _db_session,
        )

        session = next(_db_session())

    if embedding_service is None:
        from services.embedding_service import (  # pylint: disable=import-outside-toplevel
            EmbeddingService,
        )

        embedding_service = EmbeddingService()

    root = _resolve_root(brain_path)

    unparseable_from_sections: set[str] = set()
    deleted_but_embedded = _deleted_but_embedded(session, root)
    section_orphans = _section_orphans(session, root, unparseable_from_sections)
    orphaned_chunks = _orphaned_chunks(session)
    dangling_edges = _dangling_edges(session)
    model_mismatch, unstamped_count = _model_mismatch(session, embedding_service.stamp)
    ingested_count, ingested_min_at, ingested_max_at = _ingested_lane(session)
    uncovered_files, unparseable_files, excluded_count = _ingest_ceiling(session, root)
    unparseable_files = sorted(set(unparseable_files) | unparseable_from_sections)

    drift = bool(
        deleted_but_embedded
        or section_orphans
        or orphaned_chunks
        or dangling_edges
        or model_mismatch
    )

    return ReconcileReport(
        deleted_but_embedded=deleted_but_embedded,
        section_orphans=section_orphans,
        orphaned_chunks=orphaned_chunks,
        dangling_edges=dangling_edges,
        model_mismatch=model_mismatch,
        unstamped_count=unstamped_count,
        ingested_count=ingested_count,
        ingested_min_authored_at=ingested_min_at,
        ingested_max_authored_at=ingested_max_at,
        drift=drift,
        uncovered_files=uncovered_files,
        unparseable_files=unparseable_files,
        excluded_count=excluded_count,
    )
