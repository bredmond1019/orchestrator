---
type: Report
title: Review Report — frontmatter-retrieval-filters
description: SDLC review verdict for Block C — keyword-boost on keywords column and optional metadata filters for brain corpus retrieval.
---

# Review Report — frontmatter-retrieval-filters

**Date:** 2026-06-25
**Spec:** planning/frontmatter-retrieval-filters/tasks.md
**Scope:** Full spec
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| A query term present only in the `keywords` column earns the keyword boost on the `"brain"` corpus. | MET | `_keyword_search` iterates `config.get("keyword_extra_fields", [])` and ORs in `func.array_to_string(extra_col, " ").ilike(f"%{t}%")` per term; `TestKeywordExtraFields.test_brain_keyword_search_ors_in_keywords_column` covers it. |
| `filters={"project": ...}`, `filters={"layer": ...}`, and `filters={"status": ...}` each scope the `"brain"` results; a `deprecated` (or otherwise out-of-filter) fixture row is excluded. | MET | `_apply_metadata_filters` applies WHERE clauses; `TestSemanticSearchFilters.test_scalar_filter_excludes_non_matching_rows` verifies exclusion at the `_semantic_search` seam. |
| The `"brain"` `filter_fields` map treats `layer` as an array (`.overlap`) and `project`/`status` as scalars (`==`). | MET | `_apply_metadata_filters` branches on `filter_fields[field] == "array"` → `.overlap([value])` else `col == value`; `_CORPUS_CONFIG["brain"]["filter_fields"]` declares `"layer": "array"`, `"project": "scalar"`, `"status": "scalar"`. |
| The `"content"` corpus retrieval path is unchanged — same query construction, no `keywords` OR-clause, filters ignored (regression test proves it). | MET | `"content"` entry in `_CORPUS_CONFIG` has no `keyword_extra_fields` or `filter_fields`; `TestKeywordExtraFields.test_content_corpus_keyword_search_unchanged` asserts no `array_to_string` in filter args; `TestSemanticSearchFilters.test_content_corpus_retrieve_unaffected_by_filters` covers filters ignored. |
| `filters` is optional everywhere (`retrieve`, `_semantic_search`, the event schema); omitting it reproduces current behavior exactly. | MET | All three entry points default `filters=None`; `TestSemanticSearchFilters.test_filters_none_produces_same_result_as_no_filters` and `test_retrieve_without_filters_passes_none_to_semantic_search` confirm no-op behavior. |
| No `status`-aware soft re-ranking in `_fuse_and_rank` (out of scope — hard filters only); no MCP exposure. | MET | `_fuse_and_rank` uses only distance, `is_section_title` weight, and keyword boost — no status branching. No MCP changes in any modified file. |
| The full gated check suite (below) passes; `pylint app/` is `10.00/10`; pytest collection count does not drop. | MET | All fresh gating checks pass (see below); pylint rated `10.00/10`; 755 tests passed (no drop). |

## Fresh Test Results

```
ruff:
uv run python -m ruff check app/
-> All checks passed!

pylint:
uv run python -m pylint app/
-> Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)

pytest:
uv run python -m pytest
-> 755 passed, 8 skipped, 7 warnings in 2.09s

db-session-import:
cd app && uv run python -c 'import database.session'
-> OK

db-repository-import:
cd app && uv run python -c 'import database.repository'
-> OK

standing-rules (f-string-in-logging, open-without-encoding, param-named-id):
-> clean / clean / clean (no violations)
```

All gating checks exit 0.

## Verdict: PASS

All seven acceptance criteria are fully met. The implementation correctly extends `_CORPUS_CONFIG["brain"]` with `keyword_extra_fields` and `filter_fields`, adds the `_apply_metadata_filters` helper, updates `_keyword_search` and `_semantic_search` to use them, threads `filters` through `process()` → `retrieve()` → `_semantic_search()` with `getattr` defensive read, and adds `filters: dict | None` to `DocumentQAEventSchema`. The `"content"` corpus entry is byte-for-byte unchanged. Every fresh gating check passes: ruff clean, pylint `10.00/10`, pytest `755 passed`, DB imports clean, and no CLAUDE.md standing-rule violations.

## Issues Found

None.

## Next Steps

Implementation is ready to proceed to the document/wrap-up phase.
