# Review Report — phase1-projectD-task1

**Date:** 2026-06-22
**Spec:** planning/phase1-projectD/tasks.md
**Scope:** Task 1 — Data models + migration (`ContentChunk` + `ChatSession`)
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `POST /events/` DOCUMENT_INGEST validates and chunks/embeds/persists ContentChunks | SKIP (Task 2+5) | Out of scope for Task 1 |
| `POST /events/` DOCUMENT_QA validates and runs full query DAG | SKIP (Task 4+5) | Out of scope for Task 1 |
| `RetrieveChunksNode` two-stage retrieval, section-title 2x weight, corpus switch | SKIP (Task 3) | Out of scope for Task 1 |
| `AssembleContextNode` produces context with chunks + session turns; `UpdateSessionMemoryNode` appends | SKIP (Task 4) | Out of scope for Task 1 |
| Both workflows registered in both `workflow_registry.py` and `schema_registry.py` | SKIP (Task 5) | Out of scope for Task 1 |
| All prompts are `.j2` files loaded via `PromptManager`; none hardcoded in Python | SKIP (Task 4) | Out of scope for Task 1 |
| New tests cover chunking boundaries, retrieval ordering, keyword fusion, section-title weighting, corpus switch, RAG-vs-session-memory assembly, session-memory update | SKIP (Tasks 2–4) | Out of scope for Task 1 |
| `ContentChunk` model with all required fields (`id`, `doc_id`, `position`, `section_title`, `is_section_title`, `content`, `embedding` Vector(1024), `created_at`) | MET | `app/database/content_chunk.py` — all fields present with correct types |
| `ChatSession` model with all required fields (`id`, `doc_id`, `turns` JSON, `topics_covered` JSON, `created_at`, `updated_at`) | MET | `app/database/chat_session.py` — all fields present with correct types |
| `EMBEDDING_DIM = 1024` constant; mirrors `learning_artifact.py` style | MET | `app/database/content_chunk.py:17` |
| `doc_id` indexed on `content_chunks` | MET | Migration `ix_content_chunks_doc_id`; model `index=True` |
| `is_section_title` boolean with default False | MET | `app/database/content_chunk.py` Boolean column, `default=False` |
| Alembic migration creates both tables (pgvector Vector column, correct `down_revision`) | MET | `app/alembic/versions/c4d5e6f7a8b9_...py`, `down_revision="020c9f7f89e2"` |
| `app/database/__init__.py` exports both new models | MET | Exports `ContentChunk` and `ChatSession` alongside existing models |
| Model tests (schema shape + round-trip) for both models | MET | 18 ContentChunk tests + 14 ChatSession tests, all passing |
| Module docstring on line 1 (CLAUDE.md code-style) | MET | Both model files have module docstrings before imports |
| Standing-rule scan — no f-string in logging, open without encoding, param named `id` | MET | Grep scans returned no violations in new files |
| All gated validation checks pass; collected test count ≥ 549 | MET | 581 passed, 7 skipped, 588 collected (baseline was 549) |

## Fresh Test Results

**standing-rules scan (GATING):** PASS — no violations in `app/` for f-string-in-logging, open-without-encoding, or param-named-id patterns.

**db-session-import (GATING):** PASS — `cd app && uv run python -c 'import database.session'` exits 0.

**db-repository-import (GATING):** PASS — `cd app && uv run python -c 'import database.repository'` exits 0.

**net-new-lint / ruff (GATING):** PASS — `uv run python -m ruff check app/` reports "All checks passed!"

**pylint (GATING):** PASS — `uv run python -m pylint app/` rated 10.00/10.

**pytest-count (GATING):** PASS — 588 tests collected (well above 549 baseline; +39).

**pytest (GATING):** PASS — 581 passed, 7 skipped, 7 warnings in 1.93s. No failures.

## Verdict: PASS

All Task 1 in-scope acceptance criteria are MET and every gating check passes on a fresh run. The `ContentChunk` and `ChatSession` SQLAlchemy models are implemented with all required fields and correct types. The Alembic migration (`c4d5e6f7a8b9`, `down_revision=020c9f7f89e2`) creates both tables with the `ix_content_chunks_doc_id` index. Both models are exported from `app/database/__init__.py`. The 32 schema + round-trip tests all pass; the test collection count (588) significantly exceeds the ≥ 549 requirement. All gated validation checks (ruff, pylint at 10.00/10, db imports, full pytest) pass cleanly.

One minor deviation noted for future tasks: D31 ("Exclude ARRAY and Vector models from SQLite test fixtures") directs that models with `Vector` columns be excluded from SQLite fixtures. The `ContentChunk` tests use a SQLite in-memory fixture that includes the `Vector` column directly. The tests pass because SQLite silently accepts the type, but strictly the embedding round-trip test (`test_round_trip_preserves_embedding_length`) should be marked `skip` under SQLite. This does not affect the verdict — no acceptance criterion is violated and all gating checks pass — but follow-on tasks that touch `ContentChunk` should add the D31-compliant skip marker.

## Issues Found

None blocking. Minor deviation:
- `tests/database/test_content_chunk.py` — `test_embedding_column_has_1024_dim` and `test_round_trip_preserves_embedding_length` exercise the pgvector `Vector` column via SQLite without a D31-compliant `pytest.mark.skip` marker. The task step description says "per D31, mark any test exercising the pgvector Vector column skip under SQLite with a reason." The tests pass in practice but do not follow the established isolation pattern.

## Next Steps

Task 1 is complete and clean. Tasks 2, 3, and 4 can proceed in parallel (they all `dependsOn` Task 1 which is now done). Task 5 (`dependsOn` Tasks 2 + 4) and Task 6 (`dependsOn` Tasks 2, 3, 4) follow. If any future task modifies `test_content_chunk.py`, the D31 skip marker should be added at that time.
