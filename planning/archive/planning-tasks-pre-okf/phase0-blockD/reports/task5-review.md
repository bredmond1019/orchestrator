# Review Report — phase0-blockD-task5

**Date:** 2026-06-10
**Spec:** planning/tasks/phase0-blockD/tasks.md
**Scope:** Task 5 — ArticleExtractionService
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `uv run pytest` passes with all new service and node tests included (no skips) | MET | Fresh run: 177 passed, 0 failed, 2 warnings |
| `uv run ruff check app/` reports zero errors | MET | "All checks passed!" |
| `uv run pylint app/` passes (score >= previous baseline) | MET | 10.00/10 (previous 10.00/10, +0.00) |
| `ArticleExtractionService` and `ArticleResult` import cleanly | MET | `from services.article_extraction_service import ArticleExtractionService, ArticleResult` exits 0 |
| `ArticleResult` Pydantic model with `text`, `title | None`, `fetch_status` fields | MET | `app/services/article_extraction_service.py:17-22` |
| Default trafilatura path: `fetch_url` + `extract` | MET | `app/services/article_extraction_service.py:46-50` |
| Firecrawl fallback gated on `FIRECRAWL_API_KEY` env var | MET | `app/services/article_extraction_service.py:52` — `self._firecrawl_key and FirecrawlApp is not None` |
| Fallback disabled silently when `FIRECRAWL_API_KEY` absent | MET | `tests/services/test_article_extraction_service.py:74-84` confirms; no raise |
| On total failure: return `fetch_status="failed"`, never raise | MET | `app/services/article_extraction_service.py:57-58`; broad `except` in `_extract_with_firecrawl` |
| Service is stateless (no `max_calls` guard) | MET | No call-count state in `article_extraction_service.py` |
| Exported from `app/services/__init__.py` | MET | `app/services/__init__.py:3-7` — `ArticleExtractionService`, `ArticleResult` in `__all__` |
| Tests cover: trafilatura success, fallback triggered, fallback skipped without key, fallback failure, graceful failure | MET | 7 tests in `tests/services/test_article_extraction_service.py` |
| No system prompt hardcoded in Python | MET | Service contains no prompts; no `.j2` needed |
| No `if running_locally:` or deployment conditionals in any new service | MET | Confirmed by code inspection |

## Fresh Test Results

```
============================= test session starts ==============================
platform darwin -- Python 3.12.4, pytest-9.0.3, pluggy-1.6.0
collected 177 items

tests/api/test_endpoint.py ..                                            [  1%]
tests/core/test_nodes_parallel.py ..........                             [  6%]
tests/core/test_nodes_router.py .......................                  [ 19%]
tests/core/test_schema.py ..................                             [ 29%]
tests/core/test_task.py .......................                          [ 42%]
tests/core/test_validate.py .......................                      [ 55%]
tests/core/test_workflow.py ..................                           [ 66%]
tests/database/test_repository.py .............................          [ 82%]
tests/services/test_article_extraction_service.py .......                [ 86%]
tests/services/test_prompt_loader.py ....................                [ 97%]
tests/workflows/test_content_pipeline_workflow.py ....                   [100%]

=============================== warnings summary ===============================
2 pydantic field-shadowing UserWarnings (non-blocking, pre-existing)

======================= 177 passed, 2 warnings in 1.11s ========================
```

## Verdict: PASS

All 14 acceptance criteria for Task 5 are fully met. The `ArticleExtractionService` is correctly implemented with a trafilatura-first extraction path, a Firecrawl fallback gated on the presence of `FIRECRAWL_API_KEY`, and a never-raise contract that returns `fetch_status="failed"` on total failure. The `ArticleResult` Pydantic model carries all required fields. The service is stateless (no call-count guard, consistent with Project B discipline). Exports from `app/services/__init__.py` are correct. Seven unit tests covering all specified scenarios pass. The full suite of 177 tests passes with ruff at zero errors and pylint at 10.00/10.

## Issues Found

None.

## Next Steps

No fixes required. This worktree is ready to merge into main.
