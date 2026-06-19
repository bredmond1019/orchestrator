# Implementation Report — phase0-blockD-task5

**Date:** 2026-06-10
**Plan:** planning/tasks/phase0-blockD/tasks.md
**Scope:** Task 5 — ArticleExtractionService

## What Was Built or Changed
- Created `app/services/article_extraction_service.py` with `ArticleResult` (Pydantic model: `text`, `title`, `fetch_status`) and `ArticleExtractionService`.
  - Default path: `trafilatura.fetch_url` + `trafilatura.extract`.
  - Fallback path: Firecrawl `scrape_url` (markdown), gated on `FIRECRAWL_API_KEY` env var; disabled silently when absent.
  - Never raises on extraction failure — returns `fetch_status="failed"` and logs the failure.
  - Stateless: no `max_calls` guard (that belongs in the calling node per Project B discipline).
- Exported `ArticleExtractionService` and `ArticleResult` from `app/services/__init__.py`.
- Added `tests/services/test_article_extraction_service.py` (7 tests).

## Files Created or Modified
| File | Action |
|---|---|
| app/services/article_extraction_service.py | created |
| app/services/__init__.py | modified |
| tests/services/test_article_extraction_service.py | created |
| planning/tasks/phase0-blockD/reports/task5-implement.md | created |

## Validation Output
**Commands run:**
```
uv run pytest tests/services/test_article_extraction_service.py -v
uv run pytest
uv run ruff check app/
uv run pylint app/services/article_extraction_service.py
```
**Results:**
```
tests/services/test_article_extraction_service.py — 7 passed
Full suite: 177 passed, 2 warnings
ruff check app/ — All checks passed!
pylint app/services/article_extraction_service.py — rated 10.00/10
```
Status: PASSED

## Decisions and Trade-offs
- The breakdown's source snippet imported `FirecrawlApp` inline inside `extract()`, but its own test patches `services.article_extraction_service.FirecrawlApp` (a module-level attribute). Those two are inconsistent — an inline `from firecrawl import FirecrawlApp` is a local name that the patch cannot reach. I resolved this by importing `FirecrawlApp` at module level inside a guarded `try/except ImportError` (sets it to `None` if firecrawl is missing). This makes the patch target valid, keeps the fallback disabled gracefully when the dependency is absent, and preserves the stateless design. `firecrawl-py` is already a hard runtime dep in `pyproject.toml`, so the guard is defensive rather than load-bearing.
- Extracted the Firecrawl fallback into a private `_extract_with_firecrawl` helper to keep `extract()` flat and readable.
- The broad `except Exception` is intentional (the service must never crash the pipeline) and carries a `# pylint: disable=broad-exception-caught` since pylint is a scored gate; ruff's selected rule set does not flag it.
- Added tests beyond the breakdown's three: fallback-skipped-without-key, fallback-failure-returns-failed, fallback-empty-content, and a no-call-on-success assertion.

## Follow-up Work
- `app/services/__init__.py` will gain additional exports from sibling Task 3/4/6/7 services; merges of those worktrees will append to `__all__`.

## git diff --stat
```
 app/services/__init__.py | 8 ++++++++
 1 file changed, 8 insertions(+)
```
(New files `app/services/article_extraction_service.py` and `tests/services/test_article_extraction_service.py` are untracked and not shown by `git diff --stat`.)
