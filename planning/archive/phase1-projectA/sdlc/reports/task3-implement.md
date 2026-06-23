# Implementation Report — phase1-projectA-task3

**Date:** 2026-06-20
**Plan:** planning/phase1-projectA/tasks.md
**Scope:** Task 3

## What Was Built or Changed
- `FetchTranscriptNode` — reads `task_context.event.url`, calls `TranscriptService().fetch_transcript(url)`, stores raw text + `fetch_status="ok"`; catches the service's `ValueError`/`RuntimeError` and records `fetch_status="failed"` without crashing the pipeline.
- `FetchArticleNode` — calls `ArticleExtractionService().extract(url)` (trafilatura-first/Firecrawl-fallback already in the service, D24) and propagates `text`/`title`/`fetch_status` ("ok"|"fallback_used"|"failed") from the returned `ArticleResult`. The service never raises.
- `SourceRouterNode(BaseRouter)` + `YouTubeRouter(RouterNode)` — classifies `event.url` by hostname; YouTube (`youtube.com`/`youtu.be`, any subdomain) routes to `FetchTranscriptNode`, fallback routes to `FetchArticleNode`. Follows the `ticket_router_node.py` shape (stamps `{"next_node": ...}`).
- New test file covering router routing (YouTube / article / unknown-fallback) and each fetch node's success + graceful-failure paths with mocked services.

## Files Created or Modified
| File | Action |
|---|---|
| app/workflows/content_pipeline_workflow_nodes/source_router_node.py | created |
| app/workflows/content_pipeline_workflow_nodes/fetch_transcript_node.py | created |
| app/workflows/content_pipeline_workflow_nodes/fetch_article_node.py | created |
| tests/workflows/content_pipeline/__init__.py | created |
| tests/workflows/content_pipeline/test_fetch_nodes.py | created |

## Validation Output
**Commands run:**
```
uv run python -m ruff check app/
uv run python -m pylint app/
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
uv run python -m pytest
```
**Result:** PASSED

(ruff: all checks passed; pylint: 10.00/10; imports OK; pytest: 269 passed — includes 11 new fetch-node tests.)

## Decisions and Trade-offs
- Hostname classification uses `urllib.parse.urlparse(...).hostname` plus a suffix check rather than naive substring matching, so a non-YouTube URL that merely contains "youtube.com" in a path/query does not misroute. Unparseable strings yield an empty host and fall through to the article fallback (matching the spec's "unknown -> article fallback").
- `FetchTranscriptNode` stores `title=None` for shape-parity with `FetchArticleNode` so the downstream summarizer/storage can read a uniform output dict regardless of source.
- Catch is narrowed to `(ValueError, RuntimeError)` — the exact exceptions `TranscriptService.fetch_transcript` documents — rather than a broad `except`, keeping unexpected errors visible.

## Follow-up Work
- Workflow wiring (`start=SourceRouterNode`, router `is_router=True`, connections) is Task 7; these nodes are standalone until then. No deferred work within Task 3 scope.

## git diff --stat
```
 .../fetch_article_node.py                          |  28 +++++
 .../fetch_transcript_node.py                       |  41 +++++++
 .../source_router_node.py                          |  48 ++++++++
 tests/workflows/content_pipeline/__init__.py       |   0
 .../workflows/content_pipeline/test_fetch_nodes.py | 131 +++++++++++++++++++++
 5 files changed, 248 insertions(+)
```
