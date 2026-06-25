---
type: Plan
title: Task Spec — Frontmatter Indexer Parse/Strip/Enrich + Model Columns + Migration
description: Block B of the frontmatter-improvements program — teach index_brain.py to parse and strip YAML frontmatter, bake a metadata context-prefix into each chunk's embed-text, and persist the six new frontmatter fields as filterable columns on brain_documents.
status: draft
---

# Task Spec — Phase 1, Block B (Frontmatter Indexer Enrich)

**Status:** Done · **Last run:** 2026-06-25

## Goal
Make `index_brain.py` parse frontmatter once per file, strip the YAML from the embedded body, build a metadata context-prefix prepended to each chunk's embed-text (not stored), and persist the parsed fields into six new nullable `BrainDocument` columns via an Alembic migration.

## Context Pointers
- **Source block:** `agentic-portfolio/planning/frontmatter-improvements/plan.md` → *Phase 1 · Block B* (the canonical block contract: Files, Interfaces, Out-of-scope, Acceptance criteria). This block is built in **this** orchestrator repo.
- **Schema being consumed:** `agentic-portfolio/docs/okf-frontmatter.md` (field set + three controlled vocabularies) and decision `D27-enriched-okf-frontmatter`.
- **Files in play (this repo):**
  - `scripts/index_brain.py` — the corpus indexer (currently reads `file_path.read_text()` and hands the full string, YAML included, straight to `chunk_by_section` — so raw frontmatter is embedded today).
  - `app/database/brain_document.py` — the `BrainDocument` model (9 columns today; `workflow_patterns` is the ARRAY-column pattern to mirror).
  - `app/alembic/versions/` — current head is **`c4d5e6f7a8b9`** (confirmed via `alembic heads`); new migration's `down_revision` is this.
  - `tests/test_index_brain.py`, `tests/database/test_brain_document.py`, `tests/fixtures/brain_docs/` — existing test surfaces to extend.
- **Dependency:** `python-frontmatter>=1.1.0` is already in `pyproject.toml` — reuse it, do not add a new parser.
- **CLAUDE.md rules that apply:** Core-hardening guards (don't reintroduce import-time engine, etc.); code-style rules (module docstring line 1; `list[T]`/`X | None` syntax; no f-strings in logging; `open(...)` with `encoding`; `raise ... from e`); migrations under `app/alembic/` are never hand-edited *except* the new generated file, which is authored here.

## Step-by-Step Tasks

### 1. Add the six frontmatter columns to BrainDocument + Alembic migration
- In `app/database/brain_document.py`, add six **`nullable=True`** columns mirroring the existing `workflow_patterns` ARRAY pattern:
  - `doc_id = Column(String(256), nullable=True, doc=...)`
  - `layer = Column(ARRAY(String), nullable=True, doc=...)`
  - `project = Column(String(128), nullable=True, doc=...)`
  - `status = Column(String(32), nullable=True, doc=...)`
  - `keywords = Column(ARRAY(String), nullable=True, doc=...)`
  - `related = Column(ARRAY(String), nullable=True, doc=...)`
- Generate a new Alembic migration file under `app/alembic/versions/` with `down_revision = "c4d5e6f7a8b9"` (re-confirm with `cd app && uv run alembic heads` before authoring; if the head differs, use the actual head and note it in the Amendment Log). Author both `upgrade()` and `downgrade()`:
  - `upgrade()`: `add_column` for all six; create **GIN** indexes on `layer` and `keywords` (array columns), **btree** indexes on `project`, `status`, and `doc_id`.
  - `downgrade()`: drop the five indexes and six columns in reverse order.
- Extend `tests/database/test_brain_document.py` to assert the six new columns exist on the model (column presence + type checks consistent with the existing SQLite-skip pattern — note SQLite can't create the PG ARRAY columns, so guard the same way the existing fixture does).
- **Primary files:** `app/database/brain_document.py`, `app/alembic/versions/<rev>_add_frontmatter_columns_to_brain_documents.py`, `tests/database/test_brain_document.py`.

### 2. Teach index_brain.py to parse, strip, enrich, and persist frontmatter
- Add three module-level functions to `scripts/index_brain.py`:
  - `parse_document(text: str) -> tuple[dict, str]` — use `python-frontmatter` (`frontmatter.loads`) to return `(metadata, body)` with the YAML stripped from `body`. A file with no frontmatter returns `({}, original_text)`.
  - `normalize_metadata(meta: dict, file_path: Path, brain_path: Path) -> dict` — typed defaults; coerce a bare-string `layer` to a one-element list; derive `doc_id` from the filename stem when absent; **warn (log), never raise** on out-of-vocabulary `layer`/`project`/`status` values (the controlled sets from `docs/okf-frontmatter.md`); cap/normalize `keywords` and `related` to lists of strings.
  - `build_context_prefix(meta: dict) -> str` — build a compact prefix from the **semantic** fields only (`type`, `title`, `description`, `layer`, `project`, `keywords`); **exclude** `status`, `doc_id`, `related`; emit only non-empty fields; return `""` when nothing semantic is present.
- Change the per-file loop in `main()`:
  - Call `parse_document` on the raw file text; chunk the **body only** (no YAML) via `chunk_by_section`.
  - Build the prefix once per file; the text passed to `embedding_svc.embed_batch` is `prefix + chunk` (prefix + a separator), but the value stored in `content` stays the **clean chunk** (no prefix, no YAML).
  - Pass the normalized fields (`doc_id`, `layer`, `project`, `status`, `keywords`, `related`) into the `BrainDocument(...)` constructor.
  - Keep `--dry-run`, the incremental mtime-skip, and `--rebuild` paths working unchanged in behavior (dry-run still makes no DB/API calls).
- Extend `tests/test_index_brain.py` and add fixtures under `tests/fixtures/brain_docs/` (one doc with rich frontmatter, one with a bare-string `layer`, one with no frontmatter) covering: no `---`/`keywords:` leaks into stored `content`; the text handed to `embed_batch` starts with the prefix while stored `content` does not; out-of-vocab values warn but still index; docs without the new fields still index with defaults; incremental skip + `--rebuild` still work.
- **Depends on Task 1** (the constructor references the new columns). **Primary files:** `scripts/index_brain.py`, `tests/test_index_brain.py`, `tests/fixtures/brain_docs/*.md`.

### 3. Validate
- Run the Validation Commands listed below and confirm all pass. Confirm `cd app && uv run alembic upgrade head` applies the new migration cleanly against a live PG (or note it as an operator-gated step if no DB is reachable in the run environment).

## Acceptance Criteria
- A fixture doc with frontmatter indexes with **no `---` and no `keywords:` line leaking** into the stored `content`.
- The text passed to `embed_batch` **starts with the context-prefix**, while the stored `content` does **not** contain the prefix.
- All six new columns are present on `BrainDocument`, populate on insert, and are `nullable=True`.
- A doc **without** the new frontmatter fields still indexes (defaults: `doc_id` from filename stem, others null/empty).
- Out-of-vocabulary `layer`/`project`/`status` values **warn but do not raise** and the doc still indexes.
- `--dry-run`, incremental mtime-skip, and `--rebuild` all retain their existing behavior.
- `build_context_prefix` excludes `status`, `doc_id`, and `related`.
- `cd app && uv run alembic upgrade head` applies cleanly; `down_revision` chains to `c4d5e6f7a8b9`.
- The full gated check suite (below) passes; `pylint app/` is `10.00/10`; pytest collection count does not drop.

## Validation Commands
```
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
cd app && uv run alembic upgrade head
```

## Notes
<filled in as work happens>

## Amendment Log
<!-- Append-only. Pipeline stages append one dated line here when they deviate from the spec. -->
_No amendments yet._
