# Implementation Report — phase1-projectD-task2

**Date:** 2026-06-22
**Plan:** planning/phase1-projectD/tasks.md
**Scope:** Task 2

## What Was Built or Changed

- `app/schemas/document_ingest_schema.py` — `DocumentIngestEventSchema` with text/b64 content paths, optional `doc_id` auto-generation, and `model_validator` requiring at least one content field.
- `app/workflows/document_ingest_workflow_nodes/__init__.py` — empty package init.
- `app/workflows/document_ingest_workflow_nodes/parse_document_node.py` — `ParseDocumentNode`: normalises event into raw text (plain text pass-through; base64 decode for text/plain or fitz PDF extraction).
- `app/workflows/document_ingest_workflow_nodes/chunk_document_node.py` — `ChunkDocumentNode`: section-aware chunking — detects markdown headers, emits standalone `is_section_title=True` chunks, tags body chunks with `section_title`, maintains a global `position` counter.
- `app/workflows/document_ingest_workflow_nodes/embed_chunks_node.py` — `EmbedChunksNode`: single batched `EmbeddingService.embed_batch` call; zips vectors back onto chunk dicts.
- `app/workflows/document_ingest_workflow_nodes/store_chunks_node.py` — `StoreChunksNode`: `_persist` seam mirrors `StorageNode`; builds `ContentChunk` ORM objects; captures `doc_id` from event before DB round-trip; stores result with `chunks_stored` count.
- `app/workflows/document_ingest_workflow.py` — `DocumentIngestWorkflow`: linear DAG (Parse → Chunk → Embed → Store), no router.
- `tests/workflows/test_document_ingest_nodes.py` — 22 node-level tests covering: text/b64/PDF parse paths, unsupported MIME rejection, markdown header section tagging, position strictly increasing, no-header case, token window/overlap chunk count, embed_batch called once with correct args, vectors zipped back, ORM object shape, doc_id threading, result field correctness.
- `tests/workflows/test_document_ingest_workflow.py` — 12 workflow/schema tests covering: start node, event schema, four nodes present, linear DAG connections, no routers, WorkflowValidator acceptance, instantiation, schema validation (text/b64/missing both/doc_id generation/defaults).

## Files Created or Modified

| File | Action |
|---|---|
| app/schemas/document_ingest_schema.py | created |
| app/workflows/document_ingest_workflow.py | created |
| app/workflows/document_ingest_workflow_nodes/__init__.py | created |
| app/workflows/document_ingest_workflow_nodes/parse_document_node.py | created |
| app/workflows/document_ingest_workflow_nodes/chunk_document_node.py | created |
| app/workflows/document_ingest_workflow_nodes/embed_chunks_node.py | created |
| app/workflows/document_ingest_workflow_nodes/store_chunks_node.py | created |
| tests/workflows/test_document_ingest_nodes.py | created |
| tests/workflows/test_document_ingest_workflow.py | created |

## Validation Output

**Commands run:**
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
```

**Result:** PASSED

## Decisions and Trade-offs

- **`fitz` import in `parse_document_node.py`**: imported at module level so tests can patch `fitz.open` via `workflows.document_ingest_workflow_nodes.parse_document_node.fitz.open`. This matches the pattern in `chunking_service.py`.
- **Section splitting uses `re.MULTILINE`**: `^(#{1,3})\s+(.*)$` correctly matches headers at the start of any line, not just the start of the string.
- **`zip(..., strict=True)`**: applied in `EmbedChunksNode` per ruff B905; safe because `embed_batch` must return one vector per input text.
- **`_persist` seam on `StoreChunksNode`**: iterates and calls `repo.create(chunk)` per chunk inside a single `db_session` context manager, matching the pattern from `StorageNode`. Tests monkeypatch `_persist` directly.
- **Task 5 scope note**: workflow registration in `workflow_registry.py` and `schema_registry.py` is deferred to Task 5 as specified. The workflow is importable but not yet registered.

## Follow-up Work

- Register `DocumentIngestWorkflow` in `workflow_registry.py` and `schema_registry.py` (Task 5).
- Task 3 implements `RetrieveChunksNode`; Task 4 builds the Q&A query workflow that consumes the `ContentChunk` rows written here.

## git diff --stat

```
(new files — no diff stat; all files are untracked)
```
