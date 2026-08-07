"""index_brain.py — Brain corpus ingestion script (Layer 1 of the brain RAG stack).

Crawls the company brain (agentic-portfolio) markdown files, chunks each file
by section header (H2/H3), embeds the chunks via Voyage AI, and stores rows in
the ``brain_documents`` pgvector table for later semantic retrieval.

This script runs from the CLI — it is NOT a workflow node and is NOT run by Celery.

Usage:
    python scripts/index_brain.py [--brain-path PATH] [--rebuild] [--dry-run]
    python scripts/index_brain.py --prune-paths PATH [PATH ...] [--dry-run]

Args:
    --brain-path PATH    Path to the brain repo root (the directory holding
                         brain.toml). Defaults to the nearest ancestor of this
                         script that contains brain.toml — resolved by walking up,
                         so it is independent of the current working directory and
                         of where in the tier tree the orchestrator repo lives.
    --rebuild            Drop all non-diagnostic rows and re-index from scratch.
    --dry-run            Print what would be indexed (or pruned) without writing to
                         DB or calling the embedding API.
    --prune-paths PATH … Delete brain_documents rows for these deleted/renamed-away
                         file paths, then exit. Surgical orphan cleanup with no
                         embedding call; driven by the brain repo's freshness hook.
    --backfill-dates     Populate authored_at (file mtime) for existing rows without
                         re-embedding — a stat() call per file, no Ollama/Voyage
                         round-trip. Exits after backfilling; combine with --dry-run
                         to preview without writing.
"""

import argparse
import logging
import os
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import frontmatter
from sqlalchemy import or_

# Ensure app/ is importable before pulling in the shared chunking helpers below
# (mirrors the lazy sys.path setup main() does for its own app/ imports).
_APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

# Re-exported for backward compatibility: these used to be defined in this
# module. They now live in app/brain/chunking.py (OR.Q, CLAUDE.md rule 10 —
# extract on the second consumer) so scripts/index_brain.py and
# app/brain/ingest.py share one chunk->embed->write path instead of two.
# `from index_brain import chunk_by_section` (etc.) still resolves via these
# re-exports.
from brain.chunking import (  # noqa: E402  pylint: disable=wrong-import-position
    _count_tokens,
    _is_header_only_chunk,
    _split_chunk,
    build_context_prefix,
    chunk_by_section,
)

# ---------------------------------------------------------------------------
# Corpus derivation (manifest-driven; HQ Restructure Block I)
# ---------------------------------------------------------------------------
# The corpus is no longer a hand-maintained list. It is derived from the brain
# structure described by ``brain.toml``: the ``docs/`` and ``planning/`` subtrees
# of the brain root and each sub-brain tier (``core/``, ``portfolio/`` …), plus
# each scope's ``README.md`` + ``CLAUDE.md``.
#
# Tier containers (``core``, ``business``, ``portfolio``, ``side``, ``client`` —
# any manifest slug that is another repo's ``tier``) are themselves ``[[repos]]``
# entries, so they are excluded from the root walk above. Their ``docs/`` trees
# are collected by a dedicated lane with NO project override: they are
# brain-repo-tracked OKF documents carrying their own ``project:`` frontmatter,
# unlike the OR.O sub-repo files below. Their ``planning/`` + ``CLAUDE.md`` come
# from the OR.O lane instead, which is what stamps them with the tier slug.
#
# Per Bastion program Block OR.O, each gitignored project repo named in the
# manifest (``repo_path != "."``) additionally contributes its OWN
# ``planning/`` subtree + root ``CLAUDE.md`` as its own workspace-scoped
# corpus, keyed by that repo's manifest ``slug`` (stamped into the
# ``BrainDocument.project`` column, overriding any frontmatter ``project:``
# value — the slug is the workspace identity, not the file's own metadata).
# Their source trees remain out of scope (Block P territory).
#
# `OR.ticket.corpus-sub-repo-docs` adds a fourth lane: every manifest repo with
# ``repo_path != "."`` that is NOT a tier container also contributes its
# ``docs/**/*.md`` subtree (tier containers' ``docs/`` already arrive via the
# tier-docs lane above). Attribution there is frontmatter-wins/slug-fallback —
# a sub-repo doc's own ``project:`` frontmatter is honoured when present, and
# only falls back to the repo's manifest slug when the file carries none. See
# :func:`_sub_repo_docs_files` for the mechanism.
#
# ``doc_type`` is a soft categorisation column (retrieval filters on ``status`` and
# ``corpus``, never on ``doc_type``); it is assigned by a path classifier applied
# relative to each scope root.
#
# NOTE: memory/ + MEMORY.md are intentionally NOT in the corpus — they live
# outside the brain repo (harness-managed auto-memory) and drift; the repo docs
# are the authoritative current-state source. They are never crawled because only
# the docs/ + planning/ subtrees and README/CLAUDE of each scope are walked.

# Path-prefix → doc_type, matched against a path relative to a brain/sub-brain
# root. Order matters: specific entries precede the broad ``planning``/``docs``
# fallbacks.
_DOC_TYPE_RULES: list[tuple[str, str]] = [
    ("docs/decisions", "decision"),
    ("docs/projects", "project"),
    ("docs/business", "business"),
    ("docs/content", "content"),
    ("docs/diagnostic", "diagnostic"),
    ("docs/career.md", "career"),
    ("docs/profile-and-pitch.md", "career"),
    ("docs/brand.md", "brand"),
    ("docs/linkedin.md", "content"),
    ("planning", "plan"),
    ("docs", "meta"),
    ("README.md", "meta"),
    ("CLAUDE.md", "meta"),
]

# Subtrees crawled within each brain/sub-brain root, and the root-level files.
_CORPUS_SUBTREES: tuple[str, ...] = ("docs", "planning")
_CORPUS_ROOT_FILES: tuple[str, ...] = ("README.md", "CLAUDE.md")

# Ephemeral / non-corpus files skipped even inside crawled subtrees.
_EPHEMERAL_FILENAMES: frozenset[str] = frozenset({"handoff.md"})

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# brain.toml — root marker, controlled vocab, crawl rules, repo manifest
# ---------------------------------------------------------------------------
_BRAIN_CONFIG_FILENAME = "brain.toml"


def _find_brain_root(start: Path) -> Path | None:
    """Walk up from ``start`` to the nearest directory containing ``brain.toml``.

    ``brain.toml`` doubles as the brain root marker, so the indexer resolves the
    root by walking up rather than by counting directory levels (depth math broke
    when the orchestrator repo was relocated under the ``core/`` tier).
    """
    start = start.resolve()
    search = [start] if start.is_dir() else []
    search.extend(start.parents)
    for directory in search:
        if (directory / _BRAIN_CONFIG_FILENAME).is_file():
            return directory
    return None


# Default brain root: walk up from this script to brain.toml. Independent of CWD
# and of where in the tier tree the orchestrator repo lives. Falls back to a
# best-effort guess only so import never fails; real runs always find a brain.toml
# (and --brain-path / _resolve_brain_path validate it).
_DEFAULT_BRAIN_PATH = _find_brain_root(Path(__file__)) or Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class BrainConfig:
    """Parsed ``brain.toml`` — the single source of vocab, crawl rules, manifest."""

    valid_layers: frozenset[str]
    valid_projects: frozenset[str]
    valid_statuses: frozenset[str]
    skip_dirs: tuple[str, ...]
    repos: tuple[dict, ...]


def _load_brain_config(brain_path: Path) -> BrainConfig:
    """Load and parse ``brain.toml`` at ``brain_path`` into a :class:`BrainConfig`.

    Project vocab is *derived* from the ``[[repos]]`` slugs rather than listed —
    the manifest is the single source of the valid-project set.
    """
    config_file = brain_path / _BRAIN_CONFIG_FILENAME
    if not config_file.is_file():
        raise SystemExit(f"Error: {_BRAIN_CONFIG_FILENAME} not found at {config_file}")
    with config_file.open("rb") as fh:
        data = tomllib.load(fh)

    vocab = data.get("vocab", {})
    crawl = data.get("crawl", {})
    repos = tuple(data.get("repos", []))
    return BrainConfig(
        valid_layers=frozenset(vocab.get("layer", [])),
        valid_projects=frozenset(r["slug"] for r in repos if "slug" in r),
        valid_statuses=frozenset(vocab.get("status", [])),
        skip_dirs=tuple(crawl.get("skip_dirs", [])),
        repos=repos,
    )


class DocumentParseError(Exception):
    """Raised when YAML frontmatter fails to parse for a corpus file.

    Carries the source ``file_path`` and the underlying ``cause`` so a call
    site can log both without re-deriving either, and so this failure is
    distinguishable (via ``isinstance``) from an IO error (file missing/
    unreadable) or a DB error (both raised as bare exceptions elsewhere in
    this module) rather than collapsing into one generic ``Exception``.
    """

    def __init__(self, file_path: "Path | str", cause: Exception) -> None:
        self.file_path = file_path
        self.cause = cause
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"{self.file_path}: frontmatter parse error — {self.cause}"


def parse_document(text: str, file_path: "Path | str | None" = None) -> tuple[dict, str]:
    """Parse YAML frontmatter from a markdown document.

    Uses ``python-frontmatter`` to split the document into its metadata
    dictionary and the body text with the YAML block stripped.  A document
    with no frontmatter delimiter returns an empty metadata dict and the
    original text unchanged.

    Args:
        text: Raw file contents, possibly starting with a YAML frontmatter block.
        file_path: Optional source path, used only to enrich the
            :class:`DocumentParseError` raised on a malformed YAML block.
            Callers that already wrap this call in their own path-aware
            error handling may omit it.

    Returns:
        A ``(metadata, body)`` tuple where ``body`` contains no YAML delimiters
        or frontmatter fields.

    Raises:
        DocumentParseError: if the YAML frontmatter block is malformed.
    """
    try:
        post = frontmatter.loads(text)
    except Exception as exc:  # pylint: disable=broad-except
        raise DocumentParseError(
            file_path if file_path is not None else "<unknown>", exc
        ) from exc
    return dict(post.metadata), post.content


def normalize_metadata(
    meta: dict, file_path: Path, brain_path: Path, config: BrainConfig
) -> dict:
    """Normalise raw frontmatter metadata to the six OKF filterable fields.

    Applies typed defaults, coerces bare strings to lists where the schema
    expects lists, derives ``doc_id`` from the filename stem when absent, and
    logs (never raises) out-of-vocabulary values against the ``brain.toml`` vocab.

    Args:
        meta:       Raw metadata dict returned by ``parse_document``.
        file_path:  Absolute path to the source markdown file.
        brain_path: Absolute path to the brain repo root (used for rel-path
                    derivation only).
        config:     Parsed ``brain.toml`` supplying the controlled vocab.

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
        invalid = [v for v in layer if v not in config.valid_layers]
        if invalid:
            logger.warning(
                "Out-of-vocabulary layer value(s) in %s: %s",
                file_path.relative_to(brain_path) if brain_path else file_path,
                invalid,
            )

    # project: scalar string, case-normalized
    raw_project = meta.get("project")
    project: str | None = str(raw_project).strip().lower() if raw_project else None
    if project and project not in config.valid_projects:
        logger.warning(
            "Out-of-vocabulary project value in %s: %s",
            file_path.relative_to(brain_path) if brain_path else file_path,
            project,
        )

    # status: scalar string, case-normalized ("Draft" → "draft", "Active" → "active")
    raw_status = meta.get("status")
    status: str | None = str(raw_status).strip().lower() if raw_status else None
    if status and status not in config.valid_statuses:
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


def _resolve_brain_path(raw: str) -> Path:
    """Resolve --brain-path to an absolute path and validate it is a brain root."""
    p = Path(raw).resolve()
    if not p.exists():
        raise SystemExit(f"Error: --brain-path does not exist: {p}")
    if not (p / _BRAIN_CONFIG_FILENAME).is_file():
        raise SystemExit(
            f"Error: {p} does not look like a brain root — "
            f"'{_BRAIN_CONFIG_FILENAME}' not found"
        )
    return p


def _classify_doc_type(rel_posix: str) -> str:
    """Map a path (relative to a brain/sub-brain root) to its ``doc_type``."""
    for prefix, doc_type in _DOC_TYPE_RULES:
        if rel_posix == prefix or rel_posix.startswith(prefix + "/"):
            return doc_type
    return "content"


def _is_skipped(rel_posix: str, skip_dirs: tuple[str, ...]) -> bool:
    """True when a path matches a ``[crawl].skip_dirs`` entry.

    Single-name entries (``node_modules``, ``.git``) match any path component;
    path-like entries (``planning/archive``) match a prefix of the path.
    """
    parts = rel_posix.split("/")
    for skip in skip_dirs:
        if "/" in skip:
            if rel_posix == skip or rel_posix.startswith(skip + "/"):
                return True
        elif skip in parts:
            return True
    return False


def _corpus_roots(brain_path: Path, config: BrainConfig) -> list[Path]:
    """The brain root, plus any immediate child directory not named in the manifest.

    In practice this is **the brain root alone**: every tier (``core``,
    ``business``, ``portfolio``, ``side``, ``client``) is itself a ``[[repos]]``
    entry, so every tier is excluded here. Tiers reach the corpus through the two
    dedicated lanes in :func:`_collect_files` instead — :func:`_tier_docs_files`
    for ``<tier>/docs/**`` and :func:`_sub_repo_files` for ``<tier>/planning/**``
    plus the root ``CLAUDE.md``.

    Do **not** "fix" this by dropping tier containers from ``excluded`` so they
    become full corpus roots. ``_collect_files`` walks roots *before* the
    sub-repo lane and shares one ``seen`` set, so the root walk would claim
    ``<tier>/planning/**`` first and stamp it ``project=None`` — silently
    re-attributing every tier planning row away from its ``project=<tier slug>``
    workspace identity and breaking tier-scoped retrieval. The separate
    ``docs/``-only lane has no such effect.
    """
    excluded = {
        (brain_path / r["repo_path"]).resolve()
        for r in config.repos
        if r.get("repo_path") and r["repo_path"] != "."
    }
    roots = [brain_path]
    for child in sorted(brain_path.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name in config.skip_dirs:
            continue
        if child.resolve() in excluded:
            continue
        if (child / "docs").is_dir() or (child / "planning").is_dir():
            roots.append(child)
    return roots


def _tier_container_slugs(config: BrainConfig) -> frozenset[str]:
    """Manifest slugs that are *tier containers* — repos other repos live inside.

    A repo is a tier container iff its ``slug`` appears as some other repo's
    ``tier`` value: ``core`` holds ``core/orchestrator``, ``business`` holds
    ``business/bastiel``, and so on. Derived purely from the manifest and never
    hardcoded — registering a new tier in ``brain.toml`` is enough to bring its
    ``docs/`` tree into the corpus.

    Leaf code repos that happen to sit at the brain root (``learn-ai``,
    ``base-template`` — both ``tier = "_root"``) are deliberately *not* tier
    containers: nothing declares them as its tier, so they keep their OR.O
    treatment (``planning/`` + ``CLAUDE.md``, never ``docs/`` or source).
    """
    slugs = {r["slug"] for r in config.repos if r.get("slug")}
    tiers = {r["tier"] for r in config.repos if r.get("tier")}
    return frozenset(slugs & tiers)


def _tier_docs_files(
    brain_path: Path, config: BrainConfig, seen: set[Path]
) -> list[tuple[Path, str, None]]:
    """Return (absolute_path, doc_type, None) triples for each tier's ``docs/`` tree.

    Every tier container (:func:`_tier_container_slugs`) contributes its own
    ``docs/**/*.md`` subtree, honouring the same ``[crawl].skip_dirs`` (so
    ``archive/`` subtrees stay out), underscore-prefix, and ephemeral-filename
    rules as every other lane. Only ``docs/`` — a tier's ``planning/`` and root
    ``CLAUDE.md`` already arrive via :func:`_sub_repo_files`, and re-collecting
    them here would change their project attribution.

    **The project override is ``None`` on purpose.** Unlike OR.O sub-repo files
    — whose manifest-slug stamp exists precisely because ``planning/status.md``
    carries no ``project:`` and ``CLAUDE.md`` has no frontmatter at all — tier
    ``docs/`` files are brain-repo-tracked OKF documents that carry their own,
    meaningful ``project:`` value. ``core/docs/projects/bastion.md`` declares
    ``project: bastion``; stamping the tier slug would drop the document *about*
    bastion out of a ``project=bastion``-scoped query. Frontmatter wins here,
    exactly as it does for the brain root's own ``docs/``.
    """
    result: list[tuple[Path, str, None]] = []
    containers = _tier_container_slugs(config)
    for repo in config.repos:
        slug = repo.get("slug")
        repo_path = repo.get("repo_path")
        if not slug or not repo_path or repo_path == "." or slug not in containers:
            continue
        tier_root = (brain_path / repo_path).resolve()
        docs_dir = tier_root / "docs"
        if not docs_dir.is_dir():
            continue
        for md_file in sorted(docs_dir.rglob("*.md")):
            if md_file.name.startswith("_") or md_file.name in _EPHEMERAL_FILENAMES:
                continue
            rel_to_tier = md_file.relative_to(tier_root).as_posix()
            if _is_skipped(rel_to_tier, config.skip_dirs):
                continue
            if md_file in seen:
                continue
            seen.add(md_file)
            result.append((md_file, _classify_doc_type(rel_to_tier), None))
    return result


def _sub_repo_files(
    brain_path: Path, config: BrainConfig, seen: set[Path]
) -> list[tuple[Path, str, str]]:
    """Return (absolute_path, doc_type, project_slug) triples for sub-repo corpora.

    Per Bastion program Block OR.O: every manifest ``[[repos]]`` entry with
    ``repo_path != "."`` (the gitignored project repos) contributes its own
    ``planning/**/*.md`` subtree **and** its root ``CLAUDE.md`` as its own
    workspace-scoped corpus — never its ``docs/`` or source trees. Every triple
    returned here carries that repo's manifest ``slug`` as the project override,
    since sub-repo ``planning/status.md`` carries no ``project:`` frontmatter
    field and ``CLAUDE.md`` has no frontmatter at all; the slug is stamped
    regardless (it is the workspace identity, not a per-file property).
    """
    result: list[tuple[Path, str, str]] = []
    for repo in config.repos:
        repo_path = repo.get("repo_path")
        slug = repo.get("slug")
        if not repo_path or repo_path == "." or not slug:
            continue
        repo_root = (brain_path / repo_path).resolve()
        if not repo_root.is_dir():
            continue

        planning_dir = repo_root / "planning"
        if planning_dir.is_dir():
            for md_file in sorted(planning_dir.rglob("*.md")):
                if md_file.name.startswith("_") or md_file.name in _EPHEMERAL_FILENAMES:
                    continue
                rel_to_repo = md_file.relative_to(repo_root).as_posix()
                if _is_skipped(rel_to_repo, config.skip_dirs):
                    continue
                if md_file in seen:
                    continue
                seen.add(md_file)
                result.append((md_file, _classify_doc_type(rel_to_repo), slug))

        claude_file = repo_root / "CLAUDE.md"
        if claude_file.is_file() and claude_file not in seen:
            seen.add(claude_file)
            result.append((claude_file, _classify_doc_type("CLAUDE.md"), slug))

    return result


def _sub_repo_docs_files(
    brain_path: Path,
    config: BrainConfig,
    seen: set[Path],
    errors: list[str] | None = None,
    parse_failed_paths: list[str] | None = None,
) -> list[tuple[Path, str, str | None]]:
    """Return (absolute_path, doc_type, project_override) triples for sub-repo ``docs/``.

    `OR.ticket.corpus-sub-repo-docs`. Every manifest ``[[repos]]`` entry with
    ``repo_path != "."`` that is **not** a tier container (:func:`_tier_container_slugs`
    — tier containers' ``docs/`` already arrive via :func:`_tier_docs_files`)
    additionally contributes its own ``docs/**/*.md`` subtree. Source trees stay
    out of scope (the OR.O boundary against source code is unchanged); only
    ``docs/`` is added here.

    **Attribution is frontmatter-wins, slug-fallback** — a third semantics,
    distinct from both other lanes' plain ``None``/override. Sub-repo ``docs/``
    files are OKF documents (standing rule 11) and mostly carry a correct
    ``project:`` of their own (this repo's ``docs/`` all say ``orchestrator``),
    but a sub-repo doc with no frontmatter ``project:`` field should still land
    in its own repo's scope rather than falling through to ``None`` the way
    tier ``docs/`` does. Implementation choice: **(b) — this lane peeks each
    file's frontmatter at collect time** (before ``_collect_files``'s caller
    ever sees the triple) and emits ``None`` when a ``project:`` field is
    present (so the later frontmatter-driven pipeline in ``main()`` — which
    only stamps ``project_override`` when it is truthy — applies the file's own
    value untouched) or the repo's manifest ``slug`` when the field is absent
    (so the same "truthy override wins" pipeline stamps the fallback). This
    keeps the ingest path in ``main()`` completely unchanged: no new override
    semantics need to be taught to ``_backfill_dates``/the incremental-skip
    check/the upsert loop, because ``None`` vs "a slug string" is exactly the
    contract they already implement.

    A file with malformed YAML frontmatter is recorded (path + cause) into
    ``errors`` if supplied, skipped, and does **not** abort the rest of this
    lane or the overall corpus walk — this is the fix for the aborting lane
    documented at the call site in :func:`_collect_files`. Its brain-root-relative
    path is additionally recorded into ``parse_failed_paths`` if supplied — the
    same relative form the main loop stores in ``brain_documents.file_path`` —
    so the caller can report/prune its quarantined rows (``--prune-failed``).
    """
    result: list[tuple[Path, str, str | None]] = []
    containers = _tier_container_slugs(config)
    for repo in config.repos:
        slug = repo.get("slug")
        repo_path = repo.get("repo_path")
        if not slug or not repo_path or repo_path == "." or slug in containers:
            continue
        repo_root = (brain_path / repo_path).resolve()
        docs_dir = repo_root / "docs"
        if not docs_dir.is_dir():
            continue
        for md_file in sorted(docs_dir.rglob("*.md")):
            if md_file.name.startswith("_") or md_file.name in _EPHEMERAL_FILENAMES:
                continue
            rel_to_repo = md_file.relative_to(repo_root).as_posix()
            if _is_skipped(rel_to_repo, config.skip_dirs):
                continue
            if md_file in seen:
                continue
            seen.add(md_file)
            raw_content = md_file.read_text(encoding="utf-8")
            try:
                meta, _body = parse_document(raw_content, file_path=md_file)
            except DocumentParseError as exc:
                logger.error("Failed to parse %s: %s", exc.file_path, exc.cause)
                if errors is not None:
                    errors.append(str(exc))
                if parse_failed_paths is not None:
                    parse_failed_paths.append(md_file.relative_to(brain_path).as_posix())
                continue
            project_override = None if meta.get("project") else slug
            result.append((md_file, _classify_doc_type(rel_to_repo), project_override))
    return result


def _collect_files(
    brain_path: Path,
    config: BrainConfig,
    errors: list[str] | None = None,
    parse_failed_paths: list[str] | None = None,
) -> list[tuple[Path, str, str | None]]:
    """Return (absolute_path, doc_type, project_override) triples for the corpus.

    Four lanes, in order, sharing one ``seen`` set so no file is ever collected
    twice:

    1. **Brain-root subtrees** (:func:`_corpus_roots`) — ``docs/`` + ``planning/``
       plus ``README.md``/``CLAUDE.md``. No project override (``None``);
       ``project`` comes from each file's own frontmatter.
    2. **Tier ``docs/``** (:func:`_tier_docs_files`) — every manifest tier
       container's ``docs/**/*.md``. Also no project override, for the same
       reason: these are brain-repo-tracked OKF documents with their own
       ``project:`` values.
    3. **Sub-repo widening** (:func:`_sub_repo_files`, Block OR.O) — each
       gitignored sub-repo's ``planning/`` subtree + root ``CLAUDE.md``, each
       stamped with that repo's manifest slug as the project override. Sub-repo
       ``docs/`` and source are never reached by this lane.
    4. **Sub-repo ``docs/``** (:func:`_sub_repo_docs_files`,
       `OR.ticket.corpus-sub-repo-docs`) — every non-tier-container manifest
       repo's ``docs/**/*.md``, frontmatter-wins/slug-fallback attribution.

    All four honour ``[crawl].skip_dirs`` and skip underscore-prefixed and
    ephemeral files.

    A file with malformed YAML frontmatter (lane 4 only — the other three
    lanes do not parse frontmatter during collection) is recorded into
    ``errors`` if supplied and skipped rather than aborting the whole walk.
    Its relative path is additionally recorded into ``parse_failed_paths`` if
    supplied (see :func:`_sub_repo_docs_files`).
    """
    result: list[tuple[Path, str, str | None]] = []
    seen: set[Path] = set()
    for root in _corpus_roots(brain_path, config):
        for subtree in _CORPUS_SUBTREES:
            base = root / subtree
            if not base.is_dir():
                continue
            for md_file in sorted(base.rglob("*.md")):
                if md_file.name.startswith("_") or md_file.name in _EPHEMERAL_FILENAMES:
                    continue
                rel_to_root = md_file.relative_to(root).as_posix()
                if _is_skipped(rel_to_root, config.skip_dirs):
                    continue
                if md_file in seen:
                    continue
                seen.add(md_file)
                result.append((md_file, _classify_doc_type(rel_to_root), None))
        for fname in _CORPUS_ROOT_FILES:
            root_file = root / fname
            if root_file.is_file() and root_file not in seen:
                seen.add(root_file)
                result.append((root_file, _classify_doc_type(fname), None))

    result.extend(_tier_docs_files(brain_path, config, seen))
    result.extend(_sub_repo_files(brain_path, config, seen))
    result.extend(
        _sub_repo_docs_files(brain_path, config, seen, errors, parse_failed_paths)
    )
    return result


# Empty-vocab config used in workspace mode: no brain.toml, no vocab checks, no
# manifest, no skip_dirs narrowing — normalize_metadata still runs (for doc_id
# derivation, list coercion, etc.) but never logs an out-of-vocabulary warning
# because the vocab sets are empty (a warning check against an empty set can
# still fire on any non-empty value, so normalize_metadata's warnings are the
# expected, harmless side effect of a plain OKF corpus with no brain.toml).
_WORKSPACE_CONFIG = BrainConfig(
    valid_layers=frozenset(),
    valid_projects=frozenset(),
    valid_statuses=frozenset(),
    skip_dirs=(),
    repos=(),
)


def _collect_workspace_files(root: Path) -> list[Path]:
    """Recursively collect the OKF corpus under an arbitrary workspace root.

    Contract §4 shared minimum: ``.md`` and ``.mdx`` files; skip any file or
    directory whose name starts with ``.``; skip any directory named
    ``target``. No brain.toml, no vocab, no manifest, no tier/sub-repo logic,
    no underscore/ephemeral-filename skips — those are brain-mode narrowings,
    not part of the shared-minimum contract.
    """
    result: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "target")
        for fname in sorted(filenames):
            if fname.startswith("."):
                continue
            if Path(fname).suffix not in (".md", ".mdx"):
                continue
            result.append(Path(dirpath) / fname)
    return result


def _get_doc_type_for_path(file_path: str, brain_path: Path) -> str:
    """Determine doc_type from a file path via the classifier.

    Strips a leading sub-brain/tier component (e.g. ``core/``) so a tiered cache
    path classifies the same as its HQ-relative equivalent.
    """
    rel = Path(file_path)
    try:
        rel = rel.relative_to(brain_path)
    except ValueError:
        pass
    parts = rel.parts
    # Drop a leading tier/sub-brain directory if present (anything that isn't a
    # crawled subtree or a known root-level file).
    if (
        len(parts) > 1
        and parts[0] not in _CORPUS_SUBTREES
        and parts[0] not in _CORPUS_ROOT_FILES
    ):
        rel = Path(*parts[1:])
    return _classify_doc_type(rel.as_posix())


def _prune_paths(
    paths: list[str],
    brain_path: Path,
    dry_run: bool = False,
    project: str | None = None,
) -> None:
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
        brain_path: Absolute path to the brain repo root (or workspace root).
        dry_run:    When True, report what would be deleted without writing.
        project:    In workspace mode, the workspace name — scopes the delete to
                    ``project == <name>`` so two workspaces sharing a relative
                    path never prune each other's rows. ``None`` in brain mode.
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
        if project is not None:
            base = base.filter(BrainDocument.project == project)
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


def _report_and_prune_failed_files(
    failed_paths: list[str],
    dry_run: bool = False,
    project: str | None = None,
    prune: bool = False,
) -> dict[str, int]:
    """Report (and, opt-in, delete) stale rows for files that failed to parse.

    **The bug this closes:** the per-file upsert is delete-then-insert keyed on
    ``file_path`` + ``section`` — when parsing raises, that delete never runs,
    so the file's previously-indexed rows survive untouched and keep being
    retrieved. The corpus quietly serves a stale copy of a now-broken file
    indefinitely rather than losing the document.

    **Quarantine, not delete, is the default** — this matches the repo's own
    precedent (``reconcile.py`` reports, ``ops.repair_deep_stale`` repairs,
    kept separate) and avoids destroying retrievable content with no preview
    on what may be a transient YAML typo. Only ``--prune-failed`` deletes.

    Args:
        failed_paths: Brain-root-relative ``file_path`` values (the same form
            stored in ``brain_documents.file_path``) for every file that
            failed to parse this run — collection-time (sub-repo ``docs/``
            lane) and per-file (main loop) failures alike.
        dry_run:      When True, report what ``--prune-failed`` would delete
            without writing anything.
        project:      Workspace-mode project scope — mirrors every other
            delete path in this module (``None`` in brain mode).
        prune:        ``--prune-failed``. Default False — retain (quarantine).

    Returns:
        A ``{file_path: stale_rows_retained}`` map, one entry per failed path
        (post-delete count is ``0`` once a path has actually been pruned).
    """
    if not failed_paths:
        return {}

    from database.brain_document import BrainDocument
    from database.session import db_session

    retained: dict[str, int] = {}
    with next(db_session()) as session:  # type: ignore[arg-type]
        for file_path in failed_paths:
            query = session.query(BrainDocument).filter(
                BrainDocument.file_path == file_path
            )
            if project is not None:
                query = query.filter(BrainDocument.project == project)
            count = query.count()

            if not prune:
                logger.warning(
                    "%s: stale_rows_retained=%d%s",
                    file_path,
                    count,
                    " (quarantined — retained; use --prune-failed to delete)"
                    if count
                    else " (no surviving rows)",
                )
                retained[file_path] = count
                continue

            if dry_run:
                logger.warning(
                    "%s: stale_rows_retained=%d (dry run — --prune-failed would "
                    "delete these; nothing deleted)",
                    file_path,
                    count,
                )
                retained[file_path] = count
                continue

            deleted = query.delete(synchronize_session=False)
            session.commit()
            logger.warning(
                "%s: stale_rows_retained=0 (--prune-failed deleted %d row(s))",
                file_path,
                deleted,
            )
            retained[file_path] = 0

    return retained


def _backfill_dates(
    files: list[tuple[Path, str, str | None]],
    brain_path: Path,
    dry_run: bool = False,
) -> None:
    """Populate ``authored_at`` (file mtime) for existing rows, no re-embedding.

    A stat() call per file — no Ollama/Voyage round-trip. Scopes the update by
    ``project`` only when the corpus entry carries a ``project_override``
    (workspace mode, or an OR.O sub-repo file in brain mode) — mirroring the
    incremental-skip check's scoping in ``main()`` — so brain-family files
    (``project_override is None``) update every row sharing the relative
    ``file_path`` regardless of their frontmatter-derived ``project`` value.

    Args:
        files:      (absolute_path, doc_type, project_override) triples, as
                    produced by ``_collect_files``/``_collect_workspace_files``.
        brain_path: Absolute path to the brain repo root (or workspace root).
        dry_run:    When True, report what would be updated without writing.
    """
    from database.brain_document import BrainDocument
    from database.session import db_session

    total_updated = 0
    total_files = 0
    for file_path, _doc_type, project_override in files:
        rel_str = str(file_path.relative_to(brain_path))
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
        total_files += 1

        if dry_run:
            logger.info("Dry run — would set authored_at=%s for %s", mtime, rel_str)
            continue

        with next(db_session()) as session:  # type: ignore[arg-type]
            query = session.query(BrainDocument).filter(
                BrainDocument.file_path == rel_str
            )
            if project_override is not None:
                query = query.filter(BrainDocument.project == project_override)
            updated = query.update({"authored_at": mtime}, synchronize_session=False)
            session.commit()
            total_updated += updated

    if dry_run:
        logger.info("Dry run — would backfill authored_at for %d file(s)", total_files)
    else:
        logger.info(
            "--backfill-dates: updated %d row(s) across %d file(s)",
            total_updated,
            total_files,
        )


def main(argv: list[str] | None = None) -> int:
    """Entry point for the brain corpus indexer.

    Returns:
        ``0`` on a clean run, ``1`` if any file failed to parse, embed, or
        write (the failed paths are named in the logged summary). Every
        early-return branch (``--prune-paths``, ``--backfill-dates``,
        ``--dry-run``) also returns a code so ``sys.exit(main())`` and the
        in-process ``app/brain/ops.py`` call sites both see a real result
        rather than the ``None`` this used to return unconditionally.
    """
    parser = argparse.ArgumentParser(
        description="Index the company brain markdown corpus into brain_documents table."
    )
    parser.add_argument(
        "--brain-path",
        default=None,
        help=f"Path to the brain repo root (default: {_DEFAULT_BRAIN_PATH}). "
        "Brain-mode-only — do not combine with --workspace/--root.",
    )
    parser.add_argument(
        "--workspace",
        default=None,
        metavar="NAME",
        help="Index an arbitrary knowledge workspace by registered name (contract §3) "
        "instead of the brain repo. Selects workspace mode.",
    )
    parser.add_argument(
        "--root",
        default=None,
        metavar="PATH",
        help="Explicit workspace root path, overriding registry resolution (contract §3 "
        "step 1). Requires --workspace (the name supplies the row identity).",
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
    parser.add_argument(
        "--backfill-dates",
        action="store_true",
        help="Populate authored_at (file mtime) for existing rows without "
        "re-embedding — a stat() call per file, no embedding API call. "
        "Exits after backfilling; combine with --dry-run to preview.",
    )
    parser.add_argument(
        "--only-paths",
        nargs="+",
        default=None,
        metavar="PATH",
        help="Restrict indexing to the named file paths (still flows through the same "
        "chunk->embed->write + incremental-skip pipeline). Paths not part of the corpus "
        "are warned and skipped.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Disable the per-file incremental skip so the targeted files fully re-embed "
        "(distinct from --rebuild, which deletes all non-diagnostic rows corpus-wide).",
    )
    parser.add_argument(
        "--prune-failed",
        action="store_true",
        help="Delete brain_documents rows for files that failed to parse this run, "
        "instead of retaining them. Default is retain (quarantine, not delete) — a "
        "parse failure never runs the per-file delete-then-insert upsert, so without "
        "this flag the file's pre-existing rows keep being retrieved, reported per "
        "path as stale_rows_retained in the summary. Respects --dry-run (reports "
        "what would be deleted, deletes nothing) and the same workspace/project "
        "delete scoping as --rebuild/--prune-paths.",
    )
    args = parser.parse_args(argv)

    workspace_mode = bool(args.workspace or args.root)

    if args.root and not args.workspace:
        raise SystemExit(
            "Error: --root requires --workspace — the name supplies the row identity "
            "('project' column); --root only overrides resolution."
        )
    if args.brain_path is not None and workspace_mode:
        raise SystemExit(
            "Error: --brain-path is a brain-mode-only flag; do not combine it with "
            "--workspace/--root."
        )

    # Set up sys.path for imports from app/
    app_dir = Path(__file__).resolve().parent.parent / "app"
    if str(app_dir) not in sys.path:
        sys.path.insert(0, str(app_dir))

    project_scope: str | None = None
    if workspace_mode:
        from services.workspace_resolver import (
            WorkspaceResolverError,
            default_registry_path,
            load_registry,
            resolve_workspace_root,
        )

        registry_path = default_registry_path(
            xdg_config_home=os.environ.get("XDG_CONFIG_HOME"),
            home=os.environ.get("HOME"),
        )
        explicit_root = Path(args.root).resolve() if args.root else None
        try:
            registry = load_registry(registry_path)
            brain_path = resolve_workspace_root(explicit_root, args.workspace, registry)
        except WorkspaceResolverError as e:
            raise SystemExit(f"Error: {e}") from e
        brain_path = brain_path.resolve()
        if not brain_path.is_dir():
            raise SystemExit(
                f"Error: resolved workspace root is not a directory: {brain_path}"
            )
        project_scope = args.workspace
        config = _WORKSPACE_CONFIG
    else:
        brain_path = _resolve_brain_path(
            args.brain_path if args.brain_path is not None else str(_DEFAULT_BRAIN_PATH)
        )
        config = None  # loaded below, after the --prune-paths early exit

    # --prune-paths: surgical orphan cleanup, exits before any embedding work
    # (so it needs no VOYAGE_API_KEY and never touches the corpus walk).
    if args.prune_paths:
        _prune_paths(args.prune_paths, brain_path, dry_run=args.dry_run, project=project_scope)
        return 0

    # Accumulates every failure across this run — collection-time parse
    # failures (lane 4 of _collect_files, brain-mode only) plus the
    # per-file embed/DB/parse failures appended later in the main loop.
    # Declared here (not after the dry-run/backfill branches) so it is a
    # single list threaded through the whole function and nothing that
    # happens during file discovery is silently dropped.
    errors: list[str] = []
    # Subset of the above: brain-root-relative paths of files that failed to
    # *parse* specifically (not embed/DB failures), in the same relative form
    # stored in brain_documents.file_path. Feeds the stale_rows_retained /
    # --prune-failed reporting — the quarantine read (and opt-in delete) side
    # of a parse failure, since the delete-then-insert upsert never runs when
    # parsing raises.
    parse_failed_paths: list[str] = []

    if workspace_mode:
        workspace_files = _collect_workspace_files(brain_path)
        if not workspace_files:
            raise SystemExit(
                f"Error: empty corpus — no .md/.mdx files found under workspace root: "
                f"{brain_path}"
            )
        files: list[tuple[Path, str, str | None]] = [
            (fp, _classify_doc_type(fp.relative_to(brain_path).as_posix()), project_scope)
            for fp in workspace_files
        ]
    else:
        # Load the manifest (vocab + crawl rules + repo list), then collect files.
        config = _load_brain_config(brain_path)
        files = _collect_files(brain_path, config, errors, parse_failed_paths)
    if args.limit is not None:
        files = files[: args.limit]
        logger.info("--limit %d: processing first %d file(s) only", args.limit, len(files))

    if args.only_paths:
        requested = set()
        for raw in args.only_paths:
            p = Path(raw)
            requested.add(p.resolve())
            requested.add((brain_path / raw).resolve())
        filtered = [t for t in files if t[0].resolve() in requested]
        matched = {t[0].resolve() for t in filtered}
        for raw in args.only_paths:
            if Path(raw).resolve() not in matched and (brain_path / raw).resolve() not in matched:
                logger.warning("--only-paths: %s is not part of the corpus; skipping", raw)
        files = filtered

    # --backfill-dates: surgical authored_at population, exits before any
    # embedding work (no VOYAGE_API_KEY needed, no full-corpus re-index).
    if args.backfill_dates:
        _backfill_dates(files, brain_path, dry_run=args.dry_run)
        return 1 if errors else 0

    if args.dry_run:
        logger.info("Dry run — no DB writes, no API calls.")
        logger.info("Files that would be indexed:")
        for fp, doc_type, project_override in files:
            rel = fp.relative_to(brain_path)
            if project_override:
                logger.info("  [%s] %s (project=%s)", doc_type, rel, project_override)
            else:
                logger.info("  [%s] %s", doc_type, rel)
        logger.info("Total: %d files", len(files))
        if errors:
            logger.warning("Collection errors (%d):", len(errors))
            for err in errors:
                logger.warning("  %s", err)
        if parse_failed_paths:
            _report_and_prune_failed_files(
                parse_failed_paths,
                dry_run=True,
                project=project_scope,
                prune=args.prune_failed,
            )
        return 1 if errors else 0

    # Import DB and service dependencies only when not dry-run
    from database.brain_document import BrainDocument
    from database.session import db_session
    from services.embedding_service import EmbeddingService

    embedding_svc = EmbeddingService()

    total_files = 0
    total_chunks = 0
    total_embeddings = 0
    skipped_files = 0
    # NOTE: `errors` was already declared above (before the dry-run/
    # backfill-dates early returns) so any collection-time parse failures
    # from _collect_files are preserved here rather than reset.

    # Handle --rebuild: delete all non-diagnostic rows
    if args.rebuild:
        with next(db_session()) as session:  # type: ignore[arg-type]
            query = session.query(BrainDocument).filter(BrainDocument.client_slug.is_(None))
            if workspace_mode:
                # Workspace-mode --rebuild only ever touches this workspace's own rows.
                query = query.filter(BrainDocument.project == project_scope)
            else:
                # Brain-mode --rebuild must never wipe a non-manifest workspace's corpus:
                # only rows with no project (brain-family files) or a manifest slug qualify.
                manifest_slugs = list(config.valid_projects)
                query = query.filter(
                    or_(
                        BrainDocument.project.is_(None),
                        BrainDocument.project == "",
                        BrainDocument.project.in_(manifest_slugs),
                    )
                )
            deleted = query.delete(synchronize_session=False)
            session.commit()
            logger.info("--rebuild: deleted %d existing rows", deleted)

    for file_path, doc_type, project_override in files:
        rel_str = str(file_path.relative_to(brain_path))
        total_files += 1
        # authored_at: the real authoring-freshness signal (file mtime), computed
        # once per file and persisted on every upsert below — distinct from
        # indexed_at, which --rebuild resets to now() (block OR.M correction 3).
        authored_at = datetime.fromtimestamp(file_path.stat().st_mtime)

        try:
            # Incremental skip check (skip --rebuild because we already cleared;
            # skip when --force disables the skip so targeted files fully re-embed)
            if not args.rebuild and not args.force:
                with next(db_session()) as session:  # type: ignore[arg-type]
                    existing_query = session.query(BrainDocument).filter(
                        BrainDocument.file_path == rel_str
                    )
                    if workspace_mode:
                        # Scope by project too: two workspaces can share a relative
                        # path, and the skip check must not read the wrong one's row.
                        existing_query = existing_query.filter(
                            BrainDocument.project == project_scope
                        )
                    existing = existing_query.order_by(BrainDocument.indexed_at.desc()).first()
                    if existing and existing.indexed_at is not None:
                        if existing.indexed_at > authored_at:
                            skipped_files += 1
                            continue

            # Read, parse frontmatter, and chunk the body only (no YAML)
            raw_content = file_path.read_text(encoding="utf-8")
            meta, body = parse_document(raw_content, file_path=rel_str)
            norm = normalize_metadata(meta, file_path, brain_path, config)
            if project_override:
                # Sub-repo files (Block OR.O): the manifest slug is the
                # workspace identity and always wins over any frontmatter
                # project: value (sub-repo status.md has none; CLAUDE.md has
                # no frontmatter at all).
                norm["project"] = project_override
                meta = {**meta, "project": project_override}
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
                        # Delete old rows matching file_path + section (workspace mode
                        # additionally scopes by project — two workspaces can share a
                        # relative path and must not delete each other's rows).
                        delete_query = session.query(BrainDocument).filter(
                            BrainDocument.file_path == rel_str,
                            BrainDocument.section == section_header,
                        )
                        if workspace_mode:
                            delete_query = delete_query.filter(
                                BrainDocument.project == project_scope
                            )
                        delete_query.delete(synchronize_session=False)

                        doc = BrainDocument(
                            file_path=rel_str,
                            doc_type=doc_type,
                            section=section_header,
                            content=chunk_text,
                            embedding=embedding,
                            embedding_model=embedding_svc.stamp,
                            indexed_at=datetime.now(),
                            authored_at=authored_at,
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

        except DocumentParseError as parse_err:
            # Distinguishable from the IO/DB errors below: a malformed YAML
            # frontmatter block, not a filesystem or database failure.
            # __str__ already names the path, so log/record it as-is rather
            # than re-prefixing rel_str a second time.
            logger.error("Failed to parse %s: %s", parse_err.file_path, parse_err.cause)
            errors.append(str(parse_err))
            parse_failed_paths.append(rel_str)
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

    if parse_failed_paths:
        _report_and_prune_failed_files(
            parse_failed_paths,
            dry_run=False,
            project=project_scope,
            prune=args.prune_failed,
        )

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
