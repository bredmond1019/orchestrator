---
type: Report
title: Implementation Report — brain-rag
description: Implementation report for the brain-rag Layer 1 workstream.
---

# Implementation Report — brain-rag

**Date:** 2026-06-22
**Plan:** planning/brain-rag/tasks.md
**Scope:** Full spec

## What Was Built or Changed

- Created `app/database/brain_document.py` — SQLAlchemy model for brain corpus chunks, with UUID PK, file_path, doc_type, section, content, Vector(1024) embedding, indexed_at, client_slug (nullable), workflow_patterns ARRAY (nullable)
- Updated `app/database/__init__.py` — exports BrainDocument alongside LearningArtifact
- Created `app/alembic/versions/b3c4d5e6f7a8_create_brain_documents_table.py` — Alembic migration creating brain_documents table with all columns
- Updated `app/alembic/env.py` — added `from database.brain_document import *` for autogenerate support
- Created `scripts/index_brain.py` — standalone CLI script with --brain-path, --rebuild, --dry-run args; walks CORPUS, chunks by H2/H3 section, embeds via Voyage AI, upserts into brain_documents; incremental skip by indexed_at vs mtime
- Created `tests/database/test_brain_document.py` — schema tests (13 pass) and round-trip tests (7 skipped on SQLite due to ARRAY type)
- Created `tests/test_index_brain.py` — 25 unit tests covering chunk_by_section, doc_type assignment, incremental skip (mocked DB), dry-run, and _collect_files
- Created `tests/fixtures/brain_docs/career.md`, `brand.md`, `no_headers.md` — markdown fixtures for indexer tests
- Updated `tests/conftest.py` — excluded brain_documents from SQLite create_all (ARRAY not supported)
- Updated `tests/api/test_endpoint.py` — excluded brain_documents from SQLite create_all in endpoint_context fixture
- Created `planning/phase1-projectD/notes.md` — Layer 2 scope note for RetrieveChunksNode corpus parameter
- Updated `planning/master-plan.md` — added Shared Services section referencing brain corpus indexer

## Files Created or Modified

| File | Action |
|---|---|
| app/database/brain_document.py | created |
| app/database/__init__.py | modified |
| app/alembic/versions/b3c4d5e6f7a8_create_brain_documents_table.py | created |
| app/alembic/env.py | modified |
| scripts/index_brain.py | created |
| tests/database/test_brain_document.py | created |
| tests/test_index_brain.py | created |
| tests/fixtures/brain_docs/career.md | created |
| tests/fixtures/brain_docs/brand.md | created |
| tests/fixtures/brain_docs/no_headers.md | created |
| tests/conftest.py | modified |
| tests/api/test_endpoint.py | modified |
| planning/phase1-projectD/notes.md | created |
| planning/master-plan.md | modified |
| planning/brain-rag/sdlc/reports/implement.md | created |

## Validation Output

**Commands run:**
```
uv run python -m pytest tests/ -k "brain" -v
uv run python -m pytest
uv run python -m ruff check app/
uv run python scripts/index_brain.py --brain-path /Users/brandon/Dev/agentic-portfolio --dry-run
```

**Results:**
```
# brain-specific tests
tests/database/test_brain_document.py - 13 passed, 7 skipped
tests/test_index_brain.py - 25 passed

# full suite
398 passed, 7 skipped, 7 warnings

# ruff
All checks passed!

# dry-run (60 files found)
Dry run — no DB writes, no API calls.
Files that would be indexed: [60 files listed]
Total: 60 files
```

Status: PASSED

## Decisions and Trade-offs

- **SQLite ARRAY incompatibility**: BrainDocument uses PostgreSQL's ARRAY type for `workflow_patterns`. SQLite tests cannot create this table. Rather than remove the column or duplicate the model, I added exclusion logic to the two SQLite-backed fixtures (conftest.py and test_endpoint.py) and skip round-trip tests with a clear message. Schema tests (which don't require table creation) all pass. This is consistent with the pgvector Vector column which has the same SQLite limitation.
- **Lazy imports in index_brain.py**: EmbeddingService, db_session, and BrainDocument are imported inside `main()` so that `--dry-run` mode works without requiring a DB connection or API key. Tests patch at the source module path (`services.embedding_service.EmbeddingService`, `database.session.db_session`) since module-level attributes don't exist.
- **Migration is hand-crafted**: The DB is not running in CI, so `alembic revision --autogenerate` cannot be run. The migration is written to match the model exactly, following the pattern of the existing `a1b2c3d4e5f6` migration.
- **Logging capture in tests**: `logging.basicConfig(stream=sys.stdout)` is called at module import time before pytest's `capsys` patch. Dry-run tests use `caplog` (which captures at the log record level) rather than `capsys`/`capfd`.
- **Default brain path**: The script defaults to `../agentic-portfolio` (relative to cwd), which works when run from the python-orchestration-system root. The absolute path is also accepted.

## Follow-up Work

- Layer 2: RetrieveChunksNode corpus parameter (ships with Project D) — scope note is in `planning/phase1-projectD/notes.md`
- Layer 3: MCP server / `/brain/search` endpoint (ships with Project F)
- Integration test against real PostgreSQL + Voyage AI (skipped here; requires live DB + API key)
- `alembic upgrade head` should be run manually when PostgreSQL is available to apply the migration

## git diff --stat

```
 app/alembic/env.py         |  1 +
 app/database/__init__.py   |  6 ++++++
 planning/master-plan.md    |  8 ++++++++
 planning/status.md         |  5 +++++
 tests/api/test_endpoint.py |  8 ++++++-
 tests/conftest.py          | 13 +++++++++++--
 6 files changed, 38 insertions(+), 3 deletions(-) [tracked files only; new files not shown]
```
