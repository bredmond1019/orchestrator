# Implementation Report — phase0-blockD-task1

**Date:** 2026-06-10
**Plan:** planning/tasks/phase0-blockD/tasks.md
**Scope:** Task 1 — Add New Dependencies

## What Was Built or Changed
- Added seven runtime dependencies to `pyproject.toml` via `uv add` (which also resolved and locked `uv.lock`):
  - `voyageai` — EmbeddingService (Task 3)
  - `youtube-transcript-api` — TranscriptService (Task 4)
  - `trafilatura` — ArticleExtractionService default path (Task 5)
  - `firecrawl-py` — ArticleExtractionService fallback + future CrawlSiteNode (Task 5)
  - `tavily-python` — SearchService (Task 6)
  - `anthropic` — explicit pin (was transitive via pydantic-ai); ToolUseNode (Task 8)
  - `pymupdf` — PDF parsing for ChunkingService / Project D (Task 7)

## Files Created or Modified
| File | Action |
|---|---|
| pyproject.toml | modified |
| uv.lock | modified |

## Validation Output
**Commands run:**
```
uv add voyageai youtube-transcript-api trafilatura firecrawl-py tavily-python anthropic pymupdf
uv run python -c "import voyageai, tavily, trafilatura, anthropic, fitz"
uv run python -c "import youtube_transcript_api, firecrawl"
cd app && uv run python -c "from main import app; from worker.config import celery_app"
uv run ruff check app/
```
**Results:**
```
IMPORTS OK            # voyageai, tavily, trafilatura, anthropic, fitz
EXTRA IMPORTS OK      # youtube_transcript_api, firecrawl
APP IMPORTS OK        # main:app and worker.config:celery_app import cleanly
ruff: Found 2 errors  # both pre-existing, in files NOT touched by this task:
                      #   app/core/nodes/agent.py:29:7
                      #   app/database/repository.py:16:25
```
Status: PASSED

The two ruff errors are baseline lint debt in files this task did not modify
(`agent.py`, `repository.py`). Task 1's scope (dependency additions to
`pyproject.toml` / `uv.lock`) introduces no new lint findings. These are slated
for later tasks in the block that touch the relevant code.

## Decisions and Trade-offs
- `anthropic` was already present transitively via `pydantic-ai`; per spec it is now
  pinned explicitly so the version is locked directly in our manifest rather than
  floating with a transitive resolution.
- Used the exact single `uv add` invocation from the breakdown (Step 1.1) so the
  resolver computes one consistent lock rather than seven incremental relocks.
- Did not implement Tasks 2–11 — this worktree is scoped to Task 1 only.

## Follow-up Work
- Tasks 2–11 (pgvector migration, the five services, ToolUseNode, Project A scaffold,
  clean API contract) are handled in their own task worktrees.
- Pre-existing ruff errors in `app/core/nodes/agent.py` and `app/database/repository.py`
  remain; out of scope for a dependency-only task.

## git diff --stat
```
 pyproject.toml |   7 +
 uv.lock        | 930 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++-
 2 files changed, 936 insertions(+), 1 deletion(-)
```
