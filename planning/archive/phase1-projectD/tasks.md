---
type: TaskSpec
title: Task Spec — Phase 1, Project D (Document Q&A + Session Memory / RAG)
description: Step-by-step task spec for the document ingestion + RAG query workflows, two-stage hybrid retrieval, and session memory.
---

# Task Spec — Phase 1, Project D (Document Q&A + Session Memory / RAG)

## Goal
Ship a full RAG + session-memory capability: ingest a document into embedded chunks, then answer questions grounded in those chunks with two-stage hybrid retrieval and per-session conversation memory.

## Context Pointers

- **Plan:** `planning/master-plan.md` → *Project D — Document Q&A + Session Memory (RAG)* (the authoritative scope). Two flows:
  - **Ingestion:** `ParseDocumentNode → ChunkDocumentNode → EmbedChunksNode → StoreChunksNode`
  - **Query:** `EmbedQuestionNode → RetrieveChunksNode → AssembleContextNode → AnswerNode → UpdateSessionMemoryNode`
- **Project D notes:** `planning/phase1-projectD/notes.md` — `RetrieveChunksNode` must accept a `corpus` parameter for the brain-RAG integration (`brain_documents` table).
- **Reference implementation (carried over from the year-old Rust RAG engine):**
  `rag-engine-rs/src/services/search/two_stage_retrieval.rs` and `.../models/articles/query.rs` — a proven pgvector + keyword-rerank implementation of the exact two-stage pattern. Three ideas to port: (a) semantic→keyword scoped re-rank with additive score fusion; (b) **section-title chunk weighting** (`process_results` applies a 2× weight to title chunks); (c) **assembled context includes the source title + relevance score** per chunk (`chat_server.rs::build_rag_prompt`). Session memory mirrors that engine's per-session conversation-history pattern.
- **Reuse (already in the repo — do NOT rebuild):**
  - `app/services/chunking_service.py` — `ChunkingService.chunk_text(text, chunk_size=500, overlap=50)` and `chunk_document(content, mime_type, ...)` (tiktoken + pymupdf). Token-based, matches the 500/50 spec.
  - `app/services/embedding_service.py` — `EmbeddingService.embed_text` / `embed_batch` (Voyage `voyage-2`, 1024-dim).
  - `app/database/brain_document.py` — `BrainDocument` model (the brain corpus, read by `RetrieveChunksNode` when `corpus="brain"`).
  - `app/database/repository.py` — `GenericRepository` for all persistence (no sessions opened inside nodes; CLAUDE.md rule 7 / D33).
- **Patterns to mirror:** `app/database/learning_artifact.py` (pgvector `Vector(1024)` column style + `EMBEDDING_DIM`), `app/workflows/content_pipeline_workflow.py` (`WorkflowSchema` wiring), `app/workflows/content_pipeline_workflow_nodes/storage_node.py` (embed-at-write + GenericRepository persistence).
- **CLAUDE.md rules in force:** rule 1 (tests ship with every workflow), rule 2 (no hardcoded prompts — `.j2` via `PromptManager`), rule 4 (new workflows = new directories), rule 6 (register in **both** `workflow_registry.py` and `schema_registry.py`), rule 7 (no deployment logic in nodes; persistence via `GenericRepository`), rule 9 (seed `TaskContext` with the real `{"result": ...}` storage structure in tests). Code-style rules: module docstring on line 1, 3.10+ type syntax, `raise ... from e`, no f-strings in logging, `encoding="utf-8"` on `open()`.

> **Dispatch model:** the API routes on `workflow_type` in the event envelope (`POST /events/`), not on distinct URL paths. The master-plan's `/events/ingest_document` and `/events/query` therefore map to **two workflow_type values → two workflows → two schemas → two registry-pair entries.**

> **`corpus` scope decision (reconcile notes.md):** `RetrieveChunksNode` supports `corpus: Literal["content", "brain"] = "content"`. `"content"` queries the new `content_chunks` table (the documents ingested by this project — the Q&A path). `"brain"` queries `brain_documents`. The `notes.md` reference to a `learning_artifacts` corpus is **deferred to Project F** (which reuses `RetrieveChunksNode` verbatim and adds the artifacts corpus there) — recorded so the node's `corpus` literal is built to extend without rework.

---

## Step-by-Step Tasks

### 1. Data models + migration (`ContentChunk` + `ChatSession`)
- **Primary files (owned):** `app/database/content_chunk.py`, `app/database/chat_session.py`, `app/database/__init__.py` (append exports only), `app/alembic/versions/<rev>_create_content_chunks_and_chat_sessions.py`, `tests/database/test_content_chunk.py`, `tests/database/test_chat_session.py`.
- `ContentChunk`: `id` (UUID PK), `doc_id` (UUID, indexed — groups chunks of one ingested document), `position` (Integer — chunk order), `section_title` (String, nullable — the markdown header the chunk falls under), `is_section_title` (Boolean, default False — true for a standalone heading chunk; drives the retrieval weight boost), `content` (Text), `embedding` (`Vector(EMBEDDING_DIM)`, `EMBEDDING_DIM=1024`), `created_at` (DateTime). Mirror `learning_artifact.py` column style and module-docstring-on-line-1.
- `ChatSession`: `id` (UUID PK = the session id), `doc_id` (UUID — the document this Q&A session is scoped to), `turns` (JSON — ordered list of `{"role": "user"|"assistant", "content": ...}`), `topics_covered` (JSON, default list), `created_at`, `updated_at` (DateTime).
- Generate the Alembic migration for both tables (pgvector `Vector` column on `content_chunks`). Follow the existing migration style; remember the dual-head guard (`alembic merge` if a new head conflicts — see D31/2026-06-22 log).
- Tests: model field/contract tests; per **D31**, mark any test exercising the pgvector `Vector` column `skip` under SQLite with a reason. Do not drop the collected-test count.
- **No `dependsOn`** — foundational; tasks 2–4 import these models.

### 2. Document ingestion workflow (Parse → Chunk → Embed → Store)
- **Primary files (owned):** `app/workflows/document_ingest_workflow.py`, `app/workflows/document_ingest_workflow_nodes/__init__.py`, `.../parse_document_node.py`, `.../chunk_document_node.py`, `.../embed_chunks_node.py`, `.../store_chunks_node.py`, `app/schemas/document_ingest_schema.py`, `tests/workflows/test_document_ingest_*.py`.
- `DocumentIngestEventSchema`: `doc_id` (optional UUID — generated if absent), `title` (str), `content` (str — raw document text) **or** `content_b64` + `mime_type` (default `text/plain`); `chunk_size`/`overlap` optional overrides (defaults 500/50).
- `ParseDocumentNode`: normalize the event into raw text (decode base64 + dispatch PDF via `ChunkingService.chunk_document`'s parse path, or pass text through). Write the parsed text to `TaskContext`.
- `ChunkDocumentNode`: split via `ChunkingService.chunk_text`. **Section awareness:** detect markdown headers (`#`/`##`/`###`) and tag each chunk's `section_title`; emit a standalone `is_section_title=True` chunk per heading (the title-weighting hook from the Rust engine). Preserve `position` order.
- `EmbedChunksNode`: embed all chunk texts via `EmbeddingService.embed_batch` (one batched call, not per-chunk).
- `StoreChunksNode`: persist `ContentChunk` rows via `GenericRepository` (embedding written at storage time — mirror `content_pipeline` `StorageNode`; capture ids before any commit/close per the `DetachedInstanceError` lesson). No sessions opened in the node beyond the injected factory.
- Wire `WorkflowSchema` (start `ParseDocumentNode`, linear DAG). No router needed.
- Tests: chunking boundary correctness (assert token-window + overlap, section tagging), batched-embed call shape, store path writes N rows with embeddings (agents/services mocked; seed upstream nodes with the real `{"result": ...}` structure per rule 9).
- **`dependsOn`: Task 1.**

### 3. `RetrieveChunksNode` — two-stage hybrid retrieval (build carefully — reused verbatim downstream)
- **Primary files (owned):** `app/workflows/document_qa_workflow_nodes/__init__.py`, `.../retrieve_chunks_node.py`, `tests/workflows/test_retrieve_chunks_node.py`.
- Signature shape: `retrieve(query, corpus="content", k=5, threshold=0.0)`. Port the `rag-engine-rs` two-stage pattern:
  - **Stage 1 (semantic):** embed the query (`EmbeddingService`); pgvector cosine-distance ORDER BY against the corpus table (`content_chunks` for `"content"`, `brain_documents` for `"brain"`), take a wider candidate set (e.g. top-20).
  - **Stage 2 (keyword re-rank):** keyword match (ILIKE / `tsvector`) **scoped to the stage-1 candidate ids**; fuse scores additively (semantic similarity + a fixed boost per keyword hit), as in `two_stage_retrieval.rs`.
  - **Section-title weighting:** apply a 2× weight to `is_section_title` chunks during score aggregation (the `process_results` pattern from `query.rs`).
  - Apply `threshold`, sort with a NaN-safe comparator (`total_cmp` equivalent — the Rust code's explicit guard against `partial_cmp().unwrap()` on NaN), return top-`k`.
- Use `GenericRepository` / the session factory for reads — no node-opened sessions (rule 7).
- Tests: retrieval **ordering** correctness with mocked embeddings (assert the fused ranking), keyword-fusion boost changes order on an exact-term query, section-title boost, `corpus="brain"` hits `brain_documents`, `k`/`threshold` honored.
- **`dependsOn`: Task 1.** (Owns files under `document_qa_workflow_nodes/` disjoint from Task 4's files in the same dir.)

### 4. Document Q&A query workflow (Embed → Retrieve → AssembleContext → Answer → UpdateSessionMemory)
- **Primary files (owned):** `app/workflows/document_qa_workflow.py`, `app/workflows/document_qa_workflow_nodes/embed_question_node.py`, `.../assemble_context_node.py`, `.../answer_node.py`, `.../update_session_memory_node.py`, `app/schemas/document_qa_schema.py`, `app/prompts/document_qa_answer.j2`, `tests/workflows/test_document_qa_*.py`.
- `DocumentQAEventSchema`: `doc_id` (UUID), `question` (str), `session_id` (optional UUID — created if absent), `corpus` (optional, default `"content"`).
- `EmbedQuestionNode`: embed the question (reuse via `RetrieveChunksNode`'s embedding internally is fine, but keep the node for the named DAG — it can stash the vector or simply hand the query to retrieval).
- `RetrieveChunksNode` is consumed here (imported from Task 3) as the retrieval step.
- `AssembleContextNode`: build the grounded prompt context. **Include each chunk's `section_title` + a normalized relevance score** (the `build_rag_prompt` format from the Rust engine). Also load `ChatSession.turns` and assemble prior conversation as a message array (session memory) alongside the retrieved RAG context — both combined here per the plan.
- `AnswerNode` (`AgentNode`): answer grounded in the assembled context using `app/prompts/document_qa_answer.j2` loaded via `PromptManager` (rule 2). Structured or text output per the AgentNode pattern.
- `UpdateSessionMemoryNode`: append the new user question + assistant answer to `ChatSession.turns` (create the session row if new), update `topics_covered`/`updated_at`, persist via `GenericRepository`.
- Wire `WorkflowSchema` (start `EmbedQuestionNode`, linear DAG).
- Tests: RAG-vs-session-memory assembly (assert both retrieved chunks **and** prior turns appear in the assembled context), answer node reads the assembled context, session-memory update appends a turn and persists (rule 9 seeding; agents mocked).
- **`dependsOn`: Task 1, Task 3.**

### 5. Register both workflows + integration
- **Primary files (owned):** `app/workflows/workflow_registry.py`, `app/api/schema_registry.py`.
- Add `DOCUMENT_INGEST` and `DOCUMENT_QA` enum members to `WorkflowRegistry` (pointing at the two workflow classes) and the matching `SCHEMA_MAP` entries (rule 6 — `TestSchemaRegistryCompleteness` enforces this).
- Confirm `app/main` and `worker.config` still import cleanly (the gated import smoke checks).
- **`dependsOn`: Task 2, Task 4** (both workflow classes must exist to import). Shared-file task — isolated into its own wave to avoid a merge collision on the two registry files.

### 6. Documentation
- **Primary files (owned, append-only / additive):** `docs/api-reference.md` (add `##` sections for the new nodes + the two workflows), `docs/app-architecture-overview.md` (append a "What shipped" row).
- Document `RetrieveChunksNode` thoroughly (it is the reused-verbatim component) including the `corpus` parameter and the two-stage algorithm.
- **`dependsOn`: Task 2, Task 3, Task 4.** Declare these files **additive** in the execution plan (the recurring parallel-doc-merge lesson — see status.md Block D / Project A/C deviation logs).

### 7. Validate
- Run the Validation Commands below and confirm all pass. Test count must be **≥ 549** (the current baseline) and must not decrease.

## Acceptance Criteria
- `POST /events/` with `workflow_type="DOCUMENT_INGEST"` validates against `DocumentIngestEventSchema`, chunks the document (500/50 token windows with section tagging), embeds via Voyage, and persists `ContentChunk` rows with embeddings written at storage time.
- `POST /events/` with `workflow_type="DOCUMENT_QA"` validates against `DocumentQAEventSchema` and runs the full query DAG end to end (agents/services mocked in tests).
- `RetrieveChunksNode` performs **two-stage** retrieval (semantic candidate set → keyword-scoped re-rank → additive score fusion), applies the **section-title 2× weight**, honors `k`/`threshold`, sorts NaN-safely, and supports `corpus` ∈ {`"content"`, `"brain"`} hitting `content_chunks` / `brain_documents` respectively.
- `AssembleContextNode` produces a context containing **both** retrieved chunks (with section title + relevance score) **and** the prior `ChatSession` turns; `UpdateSessionMemoryNode` appends the new turn and persists.
- Both workflows are registered in **both** `workflow_registry.py` and `schema_registry.py`; `TestSchemaRegistryCompleteness` passes.
- All prompts are `.j2` files loaded via `PromptManager`; no system prompt is hardcoded in Python.
- New tests cover: chunking boundaries, retrieval ordering (mock embeddings), keyword fusion, section-title weighting, `corpus` switch, RAG-vs-session-memory assembly, and session-memory update.
- All gated validation checks pass; collected test count ≥ 549 and not decreased.

## Validation Commands
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
```

## Notes
- **rag-engine-rs carryover (this session's review):** the three ported ideas — two-stage hybrid retrieval, section-title chunk weighting, and source-title+relevance-score in the assembled context — all trace to the year-old Rust RAG engine and are now baked into Tasks 3 and 4. The Python embedding microservice (`all-MiniLM-L6-v2` Flask) and the multi-field separate-embeddings-per-article scheme from that repo were **deliberately not ported** (Voyage `EmbeddingService` already covers embeddings; single-embedding-per-chunk with title weighting is sufficient for the competence checkpoint).
- **Competence checkpoint** follows Project D (master-plan): ingest an SMB's docs, answer questions over them. Keep the ingest path mime-flexible (text + PDF via the existing `ChunkingService`).
- **Project H input:** note which nodes are local-friendly (chunking, embedding, retrieval) vs. frontier-dependent (`AnswerNode`) as you build, for the eval harness later.
