# Documentation Report — phase0-blockD-task5

**Date:** 2026-06-10
**Spec:** planning/tasks/phase0-blockD/tasks.md
**Verdict gate:** PASS (confirmed)

## Docs Patched

| Doc File | Section Updated | Change Summary |
|---|---|---|
| `docs/api-reference.md` | Table of Contents | Added entry 11 for `ArticleExtractionService` (renumbered entries 11–13 to 12–14) |
| `docs/api-reference.md` | New `## ArticleExtractionService` section | Full class-level reference for `ArticleResult` model fields, `extract()` method, extraction path logic, Firecrawl fallback gating, and export path |
| `docs/configuration.md` | Section 2 env-var table | Added `FIRECRAWL_API_KEY` row (Optional, `ArticleExtractionService` Firecrawl fallback) |

## Docs Flagged NEEDS_REVIEW

- `docs/app-architecture-overview.md` — The `app/services/` layer gained a new stateless extraction service. The architecture overview may benefit from a brief mention of the trafilatura/Firecrawl extraction pattern, but this is a high-level narrative doc and the change is additive rather than structural, so human review should decide whether a sentence is warranted.

## Docs Clean (no changes needed)

- `docs/agentic-workflows/sdlc-orchestration.md` — No references to `ArticleExtractionService`; pipeline orchestration doc is unaffected.
