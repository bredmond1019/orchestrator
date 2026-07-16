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
"""

import argparse
import logging
import os
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import frontmatter
from sqlalchemy import or_

# ---------------------------------------------------------------------------
# Corpus derivation (manifest-driven; HQ Restructure Block I)
# ---------------------------------------------------------------------------
# The corpus is no longer a hand-maintained list. It is derived from the brain
# structure described by ``brain.toml``: the ``docs/`` and ``planning/`` subtrees
# of the brain root and each sub-brain tier (``core/``, ``portfolio/`` …), plus
# each scope's ``README.md`` + ``CLAUDE.md``.
#
# Per Bastion program Block OR.O, each gitignored project repo named in the
# manifest (``repo_path != "."``) additionally contributes its OWN
# ``planning/`` subtree + root ``CLAUDE.md`` as its own workspace-scoped
# corpus, keyed by that repo's manifest ``slug`` (stamped into the
# ``BrainDocument.project`` column, overriding any frontmatter ``project:``
# value — the slug is the workspace identity, not the file's own metadata).
# Their ``docs/`` and source trees remain out of scope (that is Block O/P
# territory respectively) — only ``planning/`` + root ``CLAUDE.md`` are added.
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
    """The brain root plus every immediate sub-brain tier directory.

    A sub-brain is an immediate child directory that has a ``docs/`` or
    ``planning/`` subtree and is neither a skipped dir nor a gitignored project
    repo named in the manifest (so ``core/`` is a root but ``core/orchestrator``
    and the top-level ``learn-ai``/``base-template`` repos are not).
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


def _collect_files(brain_path: Path, config: BrainConfig) -> list[tuple[Path, str, str | None]]:
    """Return (absolute_path, doc_type, project_override) triples for the corpus.

    Crawls the ``docs/`` and ``planning/`` subtrees plus the README/CLAUDE of the
    brain root and each sub-brain tier, honouring ``[crawl].skip_dirs`` and
    skipping underscore-prefixed and ephemeral files — these entries carry no
    project override (``None``; ``project`` is read from each file's own
    frontmatter as before). It then adds each gitignored sub-repo's own
    ``planning/`` subtree + root ``CLAUDE.md`` (Block OR.O), each stamped with
    that repo's manifest slug as the project override — sub-repo ``docs/`` and
    source are never reached.
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

    result.extend(_sub_repo_files(brain_path, config, seen))
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


def main(argv: list[str] | None = None) -> None:
    """Entry point for the brain corpus indexer."""
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
        return

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
        files = _collect_files(brain_path, config)
    if args.limit is not None:
        files = files[: args.limit]
        logger.info("--limit %d: processing first %d file(s) only", args.limit, len(files))

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

        try:
            # Incremental skip check (skip --rebuild because we already cleared)
            if not args.rebuild:
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
                        mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                        if existing.indexed_at > mtime:
                            skipped_files += 1
                            continue

            # Read, parse frontmatter, and chunk the body only (no YAML)
            raw_content = file_path.read_text(encoding="utf-8")
            meta, body = parse_document(raw_content)
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
