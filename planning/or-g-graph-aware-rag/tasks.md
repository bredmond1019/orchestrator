---
type: TaskSpec
title: Task Spec — OR.G Graph-aware RAG (edge ingestion + two-stage structural retrieval)
description: Ingest mev's emitted knowledge-graph edges into a Postgres brain_edges table and extend the "brain" retrieval path with a structural neighborhood-expansion stage.
doc_id: or-g-graph-aware-rag-tasks
layer: [engine, brain]
project: orchestrator
status: active
keywords: [graph-aware RAG, brain_edges, structural retrieval, mev emit-graph, related edges, two-stage retrieval]
related: [master-plan, retrieve-chunks-node, brain-document]
---

# Task Spec — Phase Wave 5, Block OR.G

**Status:** In progress (blocked) · **Last run:** 2026-07-03 — BAILED after Task 1 (Pylint R0801 duplicate-code warning in pre-existing `sdlc_flow_workflow_nodes`, out of scope)

## Goal
Ingest mev's `emit-graph` JSON (`related:` edges) into a Postgres `brain_edges` table and extend the `"brain"` retrieval path to a two-stage structural+semantic pipeline that expands the candidate set through the `related:`-neighborhood of the top semantic hits before the existing keyword re-rank.

## Context Pointers
- **Master-plan block:** `planning/master-plan.md` → `### OR.G — Graph-aware RAG` (What / Interfaces / Depends-on / Out-of-scope / Acceptance). This spec carries those through verbatim — do not exceed the Out-of-scope boundary.
- **Edge contract (read-only, mev owns it):** `../mev/docs/cli.md` → `emit-graph` "Output shape" (version `"1"`; `nodes[]` = `{id: "scope:doc_id", scope, doc_id, rel}`; `edges[]` = `{from: "scope:doc_id", to_ref: <raw related: entry, unresolved>, kind: "related"}`; `leaves[]`). `to_ref` is the raw authored `related:` value (bare like `beta`, or already `scope:doc_id`) and must be resolved against the `nodes[]` list at ingest time; unresolved refs are dangling (target left NULL).
- **Retrieval node to extend:** `app/workflows/document_qa_workflow_nodes/retrieve_chunks_node.py` — `_CORPUS_CONFIG["brain"]`, the `retrieve()` semantic→keyword pipeline, and the pure `_fuse_and_rank()`. Keep DB calls in mockable seams (`_semantic_search`, `_keyword_search`, and a new `_structural_expand`); keep `_fuse_and_rank` pure.
- **Model + registration:** `app/database/brain_document.py` (the `related` ARRAY column already exists from Block T; this block makes it *traversable*). New models register in `app/database/__init__.py` and `app/alembic/env.py` (`from database.<model> import *` for autogenerate). Migrations follow the existing `app/alembic/versions/` head chain.
- **Event schema:** `app/schemas/document_qa_schema.py` — `corpus` / `filters` / `include_archived` live here; the structural toggle is added here.
- **Standing rules (`CLAUDE.md`):** every behaviour change ships with tests (rule 1); no deployment logic in nodes (rule 7 — the edge store is injected via `GenericRepository`/`db_session`, never a hardcoded path); OKF frontmatter on new `.md` (rule 10); no data-contract version bump (read path only — this consumes mev's contract, it does not change orchestrator's HTTP/DB contract).

## Step-by-Step Tasks
See `tasks.json` in this directory — the task list is defined there, not here.

## Acceptance Criteria
- A `brain_edges` table exists (migration applies cleanly with `alembic upgrade head`) keyed for traversal by source and target document id, populated from a `mev emit-graph` payload.
- The loader resolves each `edges[].to_ref` against the payload's `nodes[]`: a bare ref (e.g. `beta`) resolves to the matching node's canonical id; an already-scoped ref passes through; an unresolvable ref is stored dangling (target id NULL), never dropped or errored.
- Re-running the loader over an unchanged payload is idempotent (no duplicate edge rows).
- For the `"brain"` corpus, retrieval expands the Stage-1 semantic candidate set through the `related:`-neighborhood of the top semantic hits, then the existing semantic + keyword re-rank orders the union.
- A query whose answer lives in a `related:`-neighbor of the top semantic hit retrieves that neighbor — and that neighbor is *not* returned by the semantic-only path on the same fixture (demonstrable improvement + explainability: structurally-surfaced candidates are marked as such).
- The `"content"` corpus path is unchanged (regression-free); the structural stage is a no-op when the toggle is off or when no edges exist.
- The orchestrator gate holds: `ruff` clean, `pylint app/` 10.00/10, `pytest` green.

## Validation Commands
```
cd app && uv run alembic upgrade head
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest
```
<!-- Add any spec-specific checks above the standard project checks. -->

## Notes
- The block's acceptance names "the Block B eval set" for a measurable retrieval-quality comparison. No committed eval-set artifact exists in-repo, so Task 4 satisfies the intent with a focused fixture-based comparison (neighbor-retrieval that semantic-only misses, plus a parity assertion where no useful neighbor exists) rather than inventing an eval harness. If/when an eval set is committed under `scripts/`/`tests/fixtures/`, extend Task 4 to run against it.
- Neighbor direction: expand along authored `related:` edges outward from the top semantic hits; treat edges as usable in the from→to direction the payload authored (a symmetric/undirected expansion is an allowed superset if it stays regression-free on the `content` path).

## Amendment Log
<!-- Append-only. Pipeline stages append one dated line here when they deviate from the spec. -->
- 2026-07-03 [task 1] Discovered `app/alembic/versions/` is gitignored with an explicit per-filename allowlist; added an allowlist line for the new `*_create_brain_edges_table.py` migration and restored a pre-existing missing entry for `*_add_frontmatter_columns_to_brain_documents.py` so both migrations are actually tracked in git. Not called out in the spec but required for the migration to land at all.
- 2026-07-03 [task 1] Run BAILED after Task 1: `pylint` flagged an R0801 duplicate-code warning in pre-existing `sdlc_flow_workflow_nodes` code, unrelated to this task's changes. Out-of-scope fix — deferred to a human triage/refactor decision rather than retried blind. Tasks 2–5 not started.
