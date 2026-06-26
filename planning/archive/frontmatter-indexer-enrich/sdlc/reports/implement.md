---
type: Report
title: Implementation Report — frontmatter-indexer-enrich
description: Implement report for Phase 1 Block B — frontmatter parse/strip/enrich + model columns + migration.
---

# Implementation Report — frontmatter-indexer-enrich

**Date:** 2026-06-25
**Plan:** planning/frontmatter-indexer-enrich/tasks.md
**Scope:** Full spec

## What Was Built or Changed

- `app/database/brain_document.py` — Added six nullable OKF frontmatter columns: `doc_id`, `layer`, `project`, `status`, `keywords`, `related`, mirroring the existing `workflow_patterns` ARRAY pattern.
- `app/alembic/versions/d1e2f3a4b5c6_add_frontmatter_columns_to_brain_documents.py` — New Alembic migration with `down_revision = "c4d5e6f7a8b9"`. `upgrade()` adds all six columns plus GIN indexes on `layer`/`keywords` and btree indexes on `doc_id`/`project`/`status`. `downgrade()` reverses in order.
- `scripts/index_brain.py` — Added `parse_document()`, `normalize_metadata()`, and `build_context_prefix()` module-level functions. Updated `main()` loop to parse frontmatter once per file, chunk the body only (no YAML), prepend the semantic prefix to embed texts (not to stored `content`), and pass all six normalized fields into the `BrainDocument(...)` constructor.
- `tests/database/test_brain_document.py` — Extended `TestSchema` with 7 new column-presence/type/nullable tests for all six new fields. Extended `TestRoundTrip.test_round_trip_nullable_fields_default_to_none` to assert all new fields default to `None`.
- `tests/test_index_brain.py` — Added four new test classes: `TestParseDocument` (6 tests), `TestNormalizeMetadata` (11 tests), `TestBuildContextPrefix` (12 tests), `TestFrontmatterIntegration` (3 integration tests). Updated imports.
- `tests/fixtures/brain_docs/rich_frontmatter.md` — New fixture with all OKF frontmatter fields populated.
- `tests/fixtures/brain_docs/bare_string_layer.md` — New fixture with `layer` as a bare string (tests coercion to list).

## Files Created or Modified

| File | Action |
|---|---|
| `app/database/brain_document.py` | modified |
| `app/alembic/versions/d1e2f3a4b5c6_add_frontmatter_columns_to_brain_documents.py` | created |
| `scripts/index_brain.py` | modified |
| `tests/database/test_brain_document.py` | modified |
| `tests/test_index_brain.py` | modified |
| `tests/fixtures/brain_docs/rich_frontmatter.md` | created |
| `tests/fixtures/brain_docs/bare_string_layer.md` | created |
| `planning/frontmatter-indexer-enrich/sdlc/reports/implement.md` | created |

## Validation Output

**Commands run:**
```
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
cd app && uv run alembic upgrade head
```

**Results:**
```
$ uv run python -m ruff check app/
All checks passed!

$ uv run python -m pylint app/
-------------------------------------------------------------------
Your code has been rated at 10.00/10 (previous run: 9.99/10, +0.01)

$ uv run python -m pytest --tb=short
================== 746 passed, 8 skipped, 7 warnings in 2.33s ==================

$ cd app && uv run python -c 'import database.session'
(no output — success)

$ cd app && uv run python -c 'import database.repository'
(no output — success)

$ cd app && uv run alembic upgrade head
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 020c9f7f89e2 -> c4d5e6f7a8b9, create_content_chunks_and_chat_sessions
INFO  [alembic.runtime.migration] Running upgrade c4d5e6f7a8b9 -> d1e2f3a4b5c6, add_frontmatter_columns_to_brain_documents
```

Status: PASSED

## Decisions and Trade-offs

- **`import frontmatter` at module top:** The `python-frontmatter` import is at module level in `index_brain.py` (not a lazy import like `tiktoken`). This is correct: frontmatter parsing is needed for every file in both live and dry-run modes (dry-run now also calls `parse_document` implicitly through the loop — though the existing dry-run path returns before the loop, so the import is harmless there). The dependency is confirmed in `pyproject.toml`.
- **OKF controlled vocabularies hardcoded in script:** The valid sets for `layer`, `project`, and `status` are defined as module-level `frozenset` constants in `index_brain.py`. These mirror `docs/okf-frontmatter.md` and D27. They are documented with a comment pointing to the source; any vocabulary expansion requires updating them here as well. This matches the "warn, never raise" pattern required by the spec.
- **No prefix for dry-run:** The dry-run path returns before reaching the frontmatter parsing loop, so `parse_document`/`normalize_metadata`/`build_context_prefix` are not exercised in dry-run. This is by design — dry-run is intended to list files, not process them.
- **Integration test uses CORPUS-matched paths:** The integration tests place fixture files at corpus-matched paths (`docs/brand.md`, `docs/career.md`) rather than arbitrary paths, because `_collect_files` only returns files that match CORPUS entries. This is a test authoring constraint, not a production limitation.
- **`down_revision` confirmed:** `cd app && uv run alembic heads` returned `c4d5e6f7a8b9 (head)` before authoring the migration, confirming the spec's stated value was correct.

## Follow-up Work

- The alembic migration is confirmed applied cleanly against the live local PG. Production deployment of the migration is an operator step.
- The OKF controlled vocabularies in `_VALID_PROJECTS` and `_VALID_LAYERS` should be kept in sync with `docs/okf-frontmatter.md` as the vocabulary evolves.

## git diff --stat

```
 app/database/brain_document.py        |  34 ++++
 scripts/index_brain.py                | 189 +++++++++++++++++-
 tests/database/test_brain_document.py |  42 ++++
 tests/test_index_brain.py             | 348 ++++++++++++++++++++++++++++++++++
 4 files changed, 610 insertions(+), 3 deletions(-)
```
