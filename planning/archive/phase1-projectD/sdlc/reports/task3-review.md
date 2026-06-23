---
type: ReviewReport
title: Review Report — phase1-projectD-task3
description: Verdict and criterion check for Task 3 (RetrieveChunksNode) of phase1-projectD.
---

# Review Report — phase1-projectD-task3

**Date:** 2026-06-22
**Spec:** planning/phase1-projectD/tasks.md
**Scope:** Task 3 — RetrieveChunksNode two-stage hybrid retrieval
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `POST /events/` with `workflow_type="DOCUMENT_INGEST"` validates against schema, chunks, embeds, and persists ContentChunk rows | SKIP | Task 2 scope — not Task 3's files |
| `POST /events/` with `workflow_type="DOCUMENT_QA"` validates and runs full query DAG end to end | SKIP | Task 4/5 scope — not Task 3's files |
| `RetrieveChunksNode` performs two-stage retrieval (semantic candidate set → keyword-scoped re-rank → additive score fusion) | MET | `retrieve_chunks_node.py`: `_semantic_search` (top-20 pgvector), `_keyword_search` (ILIKE scoped to candidate_ids), `_fuse_and_rank` (additive: similarity + keyword_boost) |
| Applies section-title 2× weight | MET | `_fuse_and_rank`: `title_weight = 2.0 if c.get("is_section_title") else 1.0`; tested in `TestFuseAndRank::test_section_title_chunk_weighted_2x` |
| Honors `k`/`threshold` | MET | `_fuse_and_rank` filters by `threshold`, returns `scored[:k]`; tested in `test_threshold_filters_low_scores`, `test_top_k_respected`, `TestRetrieve::test_top_k_observed`, `test_threshold_applied` |
| Sorts NaN-safely | MET | `if math.isnan(distance): continue` before sort; tested in `test_nan_distance_does_not_crash`, `test_nan_only_candidates_returns_empty` |
| Supports `corpus` ∈ {"content", "brain"} hitting `content_chunks` / `brain_documents` | MET | `_CORPUS_CONFIG` dict dispatches to `ContentChunk` or `BrainDocument`; tested in `test_corpus_brain_threads_through`, `test_semantic_search_called_with_vector_and_corpus` |
| `AssembleContextNode` produces context with retrieved chunks + prior ChatSession turns | SKIP | Task 4 scope |
| `UpdateSessionMemoryNode` appends turn and persists | SKIP | Task 4 scope |
| Both workflows registered in both registries; `TestSchemaRegistryCompleteness` passes | SKIP | Task 5 scope |
| All prompts are .j2 files loaded via PromptManager; no hardcoded system prompts | SKIP | Task 4 scope (Task 3 has no prompts — retrieval only) |
| New tests cover retrieval ordering, keyword fusion, section-title weighting, corpus switch | MET | `TestFuseAndRank` (12 tests), `TestRetrieve` (7 tests), `TestProcess` (3 tests) — 22 tests total covering all required scenarios |
| All gated validation checks pass; test count ≥ 549 and not decreased | MET | 603 passed, 7 skipped (610 collected — up from baseline 549+); all gating checks exit 0 |
| CLAUDE.md rule 9: TaskContext seeded with real `{"result": ...}` structure | MET | `test_process_stores_result_in_task_context` uses `ctx.get_node_output("RetrieveChunksNode")` and asserts `"result"` key + `output["result"]["chunks"]` |
| CLAUDE.md rule 7: No deployment logic in nodes; persistence via GenericRepository / session factory | MET | Node uses `contextmanager(db_session)()` for read queries; no sessions opened beyond injected factory |
| CLAUDE.md code style: module docstring on line 1, 3.10+ types, raise-from-e | MET | Module docstring is line 1 in `retrieve_chunks_node.py`; uses `list[dict]`, `set`, `str | None` throughout; no bare `raise` detected |

## Fresh Test Results

**standing-rules (GATING):** PASS — no f-strings in logging, no bare `open()`, no `id` parameter name violations in Task 3 files.

**db-session-import (GATING):** PASS
```
cd app && uv run python -c 'import database.session'  → exit 0
```

**db-repository-import (GATING):** PASS
```
cd app && uv run python -c 'import database.repository'  → exit 0
```

**net-new-lint (GATING):** PASS — ruff reports 0 violations.

**pylint (GATING):** PASS — 10.00/10

**pytest-count (GATING):** PASS — 610 tests collected (≥ 549 baseline, increased by 22 from Task 3).

**pytest (GATING):** PASS — 603 passed, 7 skipped, 0 failed.

## Verdict: PASS

All Task 3 acceptance criteria are met. `RetrieveChunksNode` correctly implements the two-stage hybrid retrieval pattern ported from the Rust RAG engine: pgvector semantic candidate set (top-20), ILIKE keyword re-rank scoped to candidate IDs, additive score fusion, section-title 2× weight, NaN-safe sorting, k/threshold enforcement, and corpus dispatch to both `content_chunks` and `brain_documents`. The 22 new tests cover every required scenario (ordering, keyword fusion, section-title weighting, corpus switch, threshold, NaN safety, TaskContext contract). All gating checks pass clean. Criteria for Tasks 2, 4, 5, and 6 are correctly skipped as out of scope.

## Issues Found

None.

## Next Steps

Task 3 is complete. Proceed to Task 4 (Document Q&A query workflow: EmbedQuestionNode, AssembleContextNode, AnswerNode, UpdateSessionMemoryNode), which depends on Task 3's `RetrieveChunksNode`.
