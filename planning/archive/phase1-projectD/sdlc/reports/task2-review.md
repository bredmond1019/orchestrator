# Review Report — phase1-projectD-task2

**Date:** 2026-06-22
**Spec:** planning/phase1-projectD/tasks.md
**Scope:** Task 2 — Document ingestion workflow (Parse -> Chunk -> Embed -> Store)
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `POST /events/` with `workflow_type="DOCUMENT_INGEST"` validates against `DocumentIngestEventSchema`, chunks the document (500/50 token windows with section tagging), embeds via Voyage, persists `ContentChunk` rows with embeddings at storage time | MET | `app/schemas/document_ingest_schema.py` — schema with `doc_id`, `title`, `content`/`content_b64`, `chunk_size=500`, `overlap=50`; `ChunkDocumentNode` emits section-tagged chunks; `EmbedChunksNode` calls `embed_batch`; `StoreChunksNode` writes embeddings at persistence time via `GenericRepository` |
| `POST /events/` with `workflow_type="DOCUMENT_QA"` validates against `DocumentQAEventSchema` and runs the full query DAG | SKIP | Task 4 scope |
| `RetrieveChunksNode` two-stage retrieval, section-title 2x weight, corpus switch, k/threshold, NaN-safe sort | SKIP | Task 3 scope |
| `AssembleContextNode` produces context with retrieved chunks + prior turns; `UpdateSessionMemoryNode` appends turn and persists | SKIP | Task 4 scope |
| Both workflows registered in both `workflow_registry.py` and `schema_registry.py`; `TestSchemaRegistryCompleteness` passes | SKIP | Task 5 scope |
| All prompts are `.j2` files loaded via `PromptManager`; no hardcoded system prompt in Python | MET | Task 2 has no `AgentNode` and no prompt files — rule 2 not applicable; ruff/pylint clean |
| New tests cover chunking boundaries, batched-embed call shape, store path writes N rows with embeddings | MET | `tests/workflows/test_document_ingest_nodes.py`: `TestChunkDocumentNode` (6 tests — boundaries, section tagging, position order); `TestEmbedChunksNode` (3 tests — single batched call, vectors zipped); `TestStoreChunksNode` (5 tests — ORM objects, doc_id, positions, embeddings, count); CLAUDE.md rule 9 seeding confirmed |
| Tests cover retrieval ordering, keyword fusion, section-title weighting, corpus switch, RAG-vs-session-memory assembly, session-memory update | SKIP | Tasks 3/4 scope |
| All gated validation checks pass; collected test count >= 549 and not decreased | MET | 611 passed + 7 skipped = 618 collected (baseline was 549); all gating checks pass |
| CLAUDE.md standing rules: module docstrings line 1, 3.10+ type syntax, no f-strings in logging, rule 7 (GenericRepository, no deployment logic), rule 9 (TaskContext seeding) | MET | All new files start with module docstrings; 3.10+ syntax (`list[T]`, `X \| None`) confirmed; standing-rules scan clean; `StoreChunksNode` uses `GenericRepository` via injected `db_session`; test seeds use `{"result": ...}` wrapper |

## Fresh Test Results

### standing-rules (GATING)
Pattern scans on new files: f-string-in-logging, open-without-encoding, param-named-id — all returned zero matches. PASS.

### db-session-import (GATING)
```
cd app && uv run python -c 'import database.session'
```
Exit 0. PASS.

### db-repository-import (GATING)
```
cd app && uv run python -c 'import database.repository'
```
Exit 0. PASS.

### net-new-lint — ruff (GATING)
```
uv run python -m ruff check app/ --output-format=json
```
0 violations. PASS.

### pylint (GATING)
```
uv run python -m pylint app/
```
Rating: 10.00/10. PASS.

### pytest-count (GATING)
```
uv run python -m pytest --collect-only -q
```
618 tests collected (previous baseline 549). No decrease. PASS.

### pytest (GATING)
```
uv run python -m pytest
```
611 passed, 7 skipped, 7 warnings. Exit 0. PASS.

## Verdict: PASS

All Task 2 acceptance criteria that fall within scope are MET. The four workflow nodes (`ParseDocumentNode`, `ChunkDocumentNode`, `EmbedChunksNode`, `StoreChunksNode`) are correctly implemented: section-aware chunking detects markdown headers and emits standalone title chunks, `EmbedChunksNode` calls `embed_batch` in a single batched call, and `StoreChunksNode` persists `ContentChunk` ORM objects with embeddings via `GenericRepository`. Thirty new tests cover all required scenarios with correct `{"result": ...}` TaskContext seeding (rule 9). All 7 gating checks pass; collected test count is 618 (well above the 549 minimum). Criteria tagged for Tasks 3/4/5 are appropriately deferred.

## Issues Found

None.

## Next Steps

Proceed to the next eligible task in the dependency chain. Task 3 (`RetrieveChunksNode`) and Task 4 (Document Q&A workflow) both depend on Task 1 (data models) and can proceed once Task 1 is verified complete. Task 5 (registration of both workflows) depends on Tasks 2 and 4.
