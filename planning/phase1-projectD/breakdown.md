---
type: TaskBreakdown
title: Task Breakdown — Phase 1, Project D (Document Q&A + Session Memory / RAG)
description: Atomic, file-level breakdown of the Project D spec, with deepest decomposition on the two flagged tasks (ingestion workflow, query workflow).
---

# Task Breakdown — Phase 1, Project D (Document Q&A + Session Memory / RAG)

## Source Spec
`planning/phase1-projectD/tasks.md`

## Goal
Ship a full RAG + session-memory capability: ingest a document into embedded chunks, then answer questions grounded in those chunks with two-stage hybrid retrieval and per-session conversation memory.

## How to Use
Work top to bottom. Each sub-step is a single atomic action. Run the inline **Verify**
checks as you go — do not batch them at the end. Each check must pass before continuing.
The two flagged tasks (Step 2 — ingestion workflow; Step 4 — query workflow) are decomposed
to node-by-node granularity; the others are decomposed to file granularity.

> **Patterns confirmed by reading the codebase** (apply throughout):
> - **Plain `Node`** (`core/nodes/base.py`): subclass, implement `process(self, task_context: TaskContext) -> TaskContext`; store output with `task_context.update_node(node_name=self.node_name, result=...)` or `output=...`.
> - **`AgentNode`** (`core/nodes/agent.py`): implement `get_agent_config() -> AgentConfig` and `process(...)`; call `self.run_agent_recorded(task_context, user_prompt)` (NOT `self.agent.run_sync`) so telemetry is captured; then `task_context.update_node(node_name=self.node_name, result=result.output)`. Output schema subclasses `AgentNode.OutputType`.
> - **Persistence seam** (`content_pipeline_workflow_nodes/storage_node.py`): a `_persist(self, obj)` method using `with contextmanager(db_session)() as session: GenericRepository(session=session, model=Model).create(obj)`. Tests `patch.object(node, "_persist")`. Capture the row id from the **event** before persist (the `DetachedInstanceError`/`expire_on_commit` lesson).
> - **`{"result": ...}` contract (CLAUDE.md rule 9):** upstream node output is read via `task_context.get_node_output("NodeName")["result"]`. Test seeding MUST mirror this: `ctx.nodes["NodeName"] = {"result": payload}`.
> - **Prompts:** `PromptManager().get_prompt("template_name")` loads `app/prompts/template_name.j2` (no `.j2` in the call). Never hardcode a system prompt (rule 2).
> - **Migration head:** current single head is `020c9f7f89e2` (the merge of `b3c4d5e6f7a8` + `cc3ad971094e`). New migration `down_revision = "020c9f7f89e2"` — do NOT branch a third head.
> - **SQLite tests:** pgvector `Vector` columns compile under in-memory SQLite (see `test_learning_artifact.py`); `ARRAY` does not (`conftest.py` excludes `brain_documents`). `ContentChunk`/`ChatSession` use only `Vector`/`JSON`, so they work under SQLite — model tests create their own engine with a single `__table__` (the `test_learning_artifact.py` pattern). Retrieval/persistence DB calls are mocked in node tests.

---

## Steps

### Step 1: Data models + migration (`ContentChunk` + `ChatSession`)

#### 1.1 Create `app/database/content_chunk.py`
**File:** `app/database/content_chunk.py`
**Action:** create the model module (mirror `app/database/learning_artifact.py` exactly).
- Module docstring on line 1.
- `EMBEDDING_DIM = 1024`.
- Imports: `uuid`, `datetime` from `datetime`, `Vector` from `pgvector.sqlalchemy`, `Boolean, Column, DateTime, Integer, String, Text` from `sqlalchemy`, `UUID` from `sqlalchemy.dialects.postgresql`, `Base` from `database.session`.
- `class ContentChunk(Base)` with `__tablename__ = "content_chunks"` and columns:
  - `id` — `UUID(as_uuid=True)`, `primary_key=True`, `default=uuid.uuid4`
  - `doc_id` — `UUID(as_uuid=True)`, `nullable=False`, `index=True`, doc "Groups all chunks of one ingested document"
  - `position` — `Integer`, `nullable=False`, doc "0-based chunk order within the document"
  - `section_title` — `String(256)`, `nullable=True`, doc "Markdown header this chunk falls under"
  - `is_section_title` — `Boolean`, `default=False`, doc "True for a standalone heading chunk; drives the retrieval 2x weight"
  - `content` — `Text`, `nullable=False`
  - `embedding` — `Vector(EMBEDDING_DIM)`, doc "1024-dim Voyage embedding written at storage time"
  - `created_at` — `DateTime`, `default=datetime.now`

#### 1.2 Create `app/database/chat_session.py`
**File:** `app/database/chat_session.py`
**Action:** create the model module.
- Module docstring on line 1.
- Imports: `uuid`, `datetime`, `JSON, Column, DateTime`, `UUID` from postgresql dialect, `Base`.
- `class ChatSession(Base)` with `__tablename__ = "chat_sessions"` and columns:
  - `id` — `UUID(as_uuid=True)`, `primary_key=True`, `default=uuid.uuid4`, doc "The Q&A session id"
  - `doc_id` — `UUID(as_uuid=True)`, `nullable=False`, doc "The document this session is scoped to"
  - `turns` — `JSON`, `default=list`, doc "Ordered list of {role, content} conversation turns"
  - `topics_covered` — `JSON`, `default=list`, doc "Topics surfaced across the conversation"
  - `created_at` — `DateTime`, `default=datetime.now`
  - `updated_at` — `DateTime`, `default=datetime.now`, `onupdate=datetime.now`

#### 1.3 Export both models from `app/database/__init__.py`
**File:** `app/database/__init__.py`
**Action:** add imports and extend `__all__` (append-only).
- Add `from database.chat_session import ChatSession` and `from database.content_chunk import ContentChunk`.
- Extend `__all__` to `["BrainDocument", "ChatSession", "ContentChunk", "LearningArtifact"]`.

#### 1.4 Create the Alembic migration
**File:** `app/alembic/versions/c4d5e6f7a8b9_create_content_chunks_and_chat_sessions.py`
**Action:** create the migration (mirror `b3c4d5e6f7a8_create_brain_documents_table.py`).
- `revision = "c4d5e6f7a8b9"`, `down_revision = "020c9f7f89e2"`.
- `upgrade()`: `op.create_table("content_chunks", ...)` with columns matching 1.1 (`embedding` = `Vector(1024)`, nullable=True), then `op.create_index("ix_content_chunks_doc_id", "content_chunks", ["doc_id"])`; `op.create_table("chat_sessions", ...)` with columns matching 1.2 (`turns`/`topics_covered` = `sa.JSON()`).
- `downgrade()`: drop the index then both tables.

#### 1.5 Create `tests/database/test_content_chunk.py`
**File:** `tests/database/test_content_chunk.py`
**Action:** create model tests (mirror `tests/database/test_learning_artifact.py`).
- `session` fixture: `create_engine("sqlite:///:memory:")`, `Base.metadata.create_all(engine, tables=[ContentChunk.__table__])`.
- `repo` fixture: `GenericRepository(session, ContentChunk)`.
- `_make_chunk(**overrides)` helper: `doc_id=uuid.uuid4()`, `position=0`, `section_title="Intro"`, `is_section_title=False`, `content="hello world"`, `embedding=[0.01]*EMBEDDING_DIM`.
- `TestSchema`: `test_table_name` == "content_chunks"; `test_expected_columns_present` ⊇ {id, doc_id, position, section_title, is_section_title, content, embedding, created_at}; `test_id_is_primary_key`; `test_embedding_column_has_1024_dim` (`.type.dim == EMBEDDING_DIM`); `test_is_section_title_is_boolean`.
- `TestRoundTrip`: `test_create_assigns_uuid_id`; `test_round_trip_preserves_position_and_section`; `test_round_trip_preserves_embedding_length`; `test_count_reflects_created_rows`.

#### 1.6 Create `tests/database/test_chat_session.py`
**File:** `tests/database/test_chat_session.py`
**Action:** create model tests.
- `session`/`repo` fixtures over `ChatSession.__table__`.
- `TestSchema`: table name == "chat_sessions"; columns ⊇ {id, doc_id, turns, topics_covered, created_at, updated_at}; `turns` is `JSON`; `id` is PK.
- `TestRoundTrip`: create with `turns=[{"role":"user","content":"hi"}]`, fetch, assert `turns` round-trips; `test_topics_covered_defaults_to_list` (create without topics, assert `[]` or `None` per the default chosen).

**Verify:** `uv run python -m pytest tests/database/test_content_chunk.py tests/database/test_chat_session.py -q` → all pass. Then `cd app && uv run python -c 'from database import ChatSession, ContentChunk'` → exit 0.

---

### Step 2: Document ingestion workflow (Parse → Chunk → Embed → Store) — [flagged: deep decomposition]

#### 2.1 Create `app/schemas/document_ingest_schema.py`
**File:** `app/schemas/document_ingest_schema.py`
**Action:** create the event schema (mirror `content_pipeline_schema.py` style).
- `class DocumentIngestEventSchema(BaseModel)` fields:
  - `doc_id: UUID = Field(default_factory=uuid4, description="Stable identity for this document's chunks")`
  - `title: str = Field(..., description="Human-readable document title")`
  - `content: str | None = Field(default=None, description="Raw document text (text path)")`
  - `content_b64: str | None = Field(default=None, description="Base64 document bytes (binary path, e.g. PDF)")`
  - `mime_type: str = Field(default="text/plain", description="MIME type for the binary path")`
  - `chunk_size: int = Field(default=500)`, `overlap: int = Field(default=50)`
- Add a `model_validator` (mode="after") asserting at least one of `content` / `content_b64` is set.

#### 2.2 Create `app/workflows/document_ingest_workflow_nodes/__init__.py`
**File:** `app/workflows/document_ingest_workflow_nodes/__init__.py`
**Action:** empty package init (match the other `_workflow_nodes/__init__.py` files — they are empty).

#### 2.3 Create `ParseDocumentNode`
**File:** `app/workflows/document_ingest_workflow_nodes/parse_document_node.py`
**Action:** plain `Node` subclass.
- `process`: read `event = task_context.event`. If `event.content` is set, `text = event.content`. Else decode `base64.b64decode(event.content_b64)` → if `mime_type == "text/plain"` decode utf-8; if `application/pdf` call `ChunkingService().chunk_document(...)`? No — keep parse separate: use `fitz`-free path by delegating PDF extraction to a small helper. **Simpler:** for the binary path call a new `ChunkingService` text-extraction — but `ChunkingService` only exposes `chunk_text`/`chunk_document` (parse+chunk fused). To keep the named DAG, ParseDocumentNode extracts raw text: for `text/plain` decode; for `application/pdf` use `fitz.open(stream=..., filetype="pdf")` and join page text (same call `chunk_document` makes internally). Import `fitz` at module top.
- Store `task_context.update_node(node_name=self.node_name, result={"text": text})`.

#### 2.4 Create `ChunkDocumentNode`
**File:** `app/workflows/document_ingest_workflow_nodes/chunk_document_node.py`
**Action:** plain `Node` subclass with section-aware chunking (the rag-engine-rs title-weighting hook).
- Read `text = task_context.get_node_output("ParseDocumentNode")["result"]["text"]`.
- Read `chunk_size`/`overlap` from `task_context.event`.
- Split `text` into sections by markdown headers (regex `^(#{1,3})\s+(.*)$` per line). For each section: emit one `is_section_title=True` chunk holding the header text (`section_title` = header), then run `ChunkingService().chunk_text(section_body, chunk_size, overlap)` and emit `is_section_title=False` chunks each tagged with that `section_title`. Text before the first header gets `section_title=None`.
- Maintain a global `position` counter across all emitted chunks (preserve order).
- Store `result={"chunks": [{"position", "section_title", "is_section_title", "content"}, ...]}`.

#### 2.5 Create `EmbedChunksNode`
**File:** `app/workflows/document_ingest_workflow_nodes/embed_chunks_node.py`
**Action:** plain `Node` subclass.
- Read chunks from `ChunkDocumentNode` output.
- One batched call: `vectors = EmbeddingService().embed_batch([c["content"] for c in chunks])`.
- Zip vectors back onto each chunk dict under `"embedding"`.
- Store `result={"chunks": chunks_with_embeddings}`. (Construct `EmbeddingService()` inside `process` so tests can patch `workflows.document_ingest_workflow_nodes.embed_chunks_node.EmbeddingService`.)

#### 2.6 Create `StoreChunksNode`
**File:** `app/workflows/document_ingest_workflow_nodes/store_chunks_node.py`
**Action:** plain `Node` subclass with a `_persist` seam (mirror `storage_node.py`).
- `_persist(self, chunks: list[ContentChunk])`: `with contextmanager(db_session)() as session: repo = GenericRepository(session=session, model=ContentChunk); for c in chunks: repo.create(c)` (or add+commit batched).
- `process`: read embedded chunks; `doc_id = task_context.event.doc_id` (capture before persist); build `ContentChunk(doc_id=doc_id, position=..., section_title=..., is_section_title=..., content=..., embedding=...)` per chunk; call `self._persist(...)`; store `result={"doc_id": str(doc_id), "chunks_stored": len(chunks), "embedded": True}`.

#### 2.7 Create `DocumentIngestWorkflow`
**File:** `app/workflows/document_ingest_workflow.py`
**Action:** `Workflow` subclass (mirror `content_pipeline_workflow.py` structure, linear DAG, no router).
- `workflow_schema = WorkflowSchema(description=..., event_schema=DocumentIngestEventSchema, start=ParseDocumentNode, nodes=[NodeConfig(ParseDocumentNode, [ChunkDocumentNode]), NodeConfig(ChunkDocumentNode, [EmbedChunksNode]), NodeConfig(EmbedChunksNode, [StoreChunksNode]), NodeConfig(StoreChunksNode, [])])`.

#### 2.8 Create `tests/workflows/test_document_ingest_nodes.py`
**File:** `tests/workflows/test_document_ingest_nodes.py`
**Action:** node-level tests (seed `TaskContext` with the `{"result": ...}` contract).
- `ParseDocumentNode`: text path returns the text; pdf path patches `fitz.open` and asserts joined page text.
- `ChunkDocumentNode`: input with two markdown headers → assert a `is_section_title=True` chunk per header, body chunks tagged with the right `section_title`, `position` strictly increasing, and token-window/overlap honored (assert chunk count for a known-length input).
- `EmbedChunksNode`: patch `EmbeddingService`, assert `embed_batch` called **once** with the list of chunk contents and vectors attached.
- `StoreChunksNode`: `patch.object(node, "_persist")`; assert N `ContentChunk` objects passed with correct `doc_id`/`position`/`embedding`; assert `result["chunks_stored"] == N` and `doc_id` is the event's.

#### 2.9 Create `tests/workflows/test_document_ingest_workflow.py`
**File:** `tests/workflows/test_document_ingest_workflow.py`
**Action:** workflow wiring test — assert `DocumentIngestWorkflow.workflow_schema.start is ParseDocumentNode`, the four nodes are present, connections are linear, and `WorkflowValidator` accepts it (mirror `test_content_pipeline_workflow.py`).

**Verify:** `uv run python -m pytest tests/workflows/test_document_ingest_nodes.py tests/workflows/test_document_ingest_workflow.py -q` → all pass.

---

### Step 3: `RetrieveChunksNode` — two-stage hybrid retrieval

#### 3.1 Create `app/workflows/document_qa_workflow_nodes/__init__.py`
**File:** `app/workflows/document_qa_workflow_nodes/__init__.py`
**Action:** empty package init.

#### 3.2 Create `RetrieveChunksNode` with mockable DB seams + a pure fusion function
**File:** `app/workflows/document_qa_workflow_nodes/retrieve_chunks_node.py`
**Action:** plain `Node` subclass. Structure the algorithm so the DB calls are isolated (mockable) and the fusion logic is pure (unit-testable) — this is the reused-verbatim component, build it carefully.
- `process`: read `query` (from `task_context.event.question`), `corpus = getattr(event, "corpus", "content")`; call `self.retrieve(query, corpus=corpus, k=5)`; store `result={"chunks": [...]}` (normalized dicts: `{"content", "section_title", "score", "source"}`).
- `retrieve(self, query, corpus="content", k=5, threshold=0.0)`: `vector = EmbeddingService().embed_text(query)`; `candidates = self._semantic_search(vector, corpus, limit=20)`; `keyword_ids = self._keyword_search(query, [c["id"] for c in candidates], corpus)`; `return self._fuse_and_rank(candidates, keyword_ids, k, threshold)`.
- `_semantic_search(self, vector, corpus, limit)`: pick model (`ContentChunk` for "content", `BrainDocument` for "brain") and content/section field names; run pgvector `embedding.cosine_distance(vector)` ordered query via the `db_session` factory; return list of `{"id", "content", "section_title", "is_section_title", "distance"}` (for brain map `section`→`section_title`, `is_section_title`=False). This method is patched in tests.
- `_keyword_search(self, query, candidate_ids, corpus)`: ILIKE over the content/title field scoped to `candidate_ids`; return the set of matching ids. Patched in tests.
- `_fuse_and_rank(self, candidates, keyword_ids, k, threshold)` — **pure, no DB**: for each candidate `score = (1.0 - distance) * (2.0 if is_section_title else 1.0) + (1.0 if id in keyword_ids else 0.0)`; drop scores `< threshold`; sort by score desc using a NaN-safe key (e.g. `key=lambda c: (math.isnan(c["score"]) ... )` or filter NaN — replicate the Rust `total_cmp` guard, never a naive sort that can mis-handle NaN); return top-`k` normalized dicts.

#### 3.3 Create `tests/workflows/test_retrieve_chunks_node.py`
**File:** `tests/workflows/test_retrieve_chunks_node.py`
**Action:** tests targeting `_fuse_and_rank` (pure) and `retrieve` (with `_semantic_search`/`_keyword_search`/`EmbeddingService` patched).
- `test_semantic_ranking_orders_by_distance` — feed candidates with known distances, no keyword hits, assert order.
- `test_keyword_boost_changes_order` — two candidates close in distance; the one in `keyword_ids` ranks first.
- `test_section_title_chunk_weighted_2x` — a section-title chunk with worse distance outranks a body chunk once the 2x weight applies.
- `test_threshold_filters_low_scores` — assert sub-threshold candidates are dropped.
- `test_top_k_respected` — 20 candidates in, `k=5` out.
- `test_nan_distance_does_not_crash` — a NaN distance is handled (filtered or sorted last), no exception.
- `test_corpus_brain_uses_brain_document` — patch `_semantic_search` and assert `retrieve(query, corpus="brain")` requests the brain model path (assert the corpus arg threads through).

**Verify:** `uv run python -m pytest tests/workflows/test_retrieve_chunks_node.py -q` → all pass.

---

### Step 4: Document Q&A query workflow (Embed → Retrieve → AssembleContext → Answer → UpdateSessionMemory) — [flagged: deep decomposition]

#### 4.1 Create `app/schemas/document_qa_schema.py`
**File:** `app/schemas/document_qa_schema.py`
**Action:** `class DocumentQAEventSchema(BaseModel)`:
- `doc_id: UUID = Field(..., description="Document to answer over")`
- `question: str = Field(..., description="The user question")`
- `session_id: UUID = Field(default_factory=uuid4, description="Q&A session id; new if absent")`
- `corpus: str = Field(default="content", description="'content' or 'brain'")`

#### 4.2 Create `EmbedQuestionNode`
**File:** `app/workflows/document_qa_workflow_nodes/embed_question_node.py`
**Action:** plain `Node`. Embed `event.question` via `EmbeddingService().embed_text(...)`; store `result={"question": event.question, "embedding": vector}`. (Keeps the named DAG step; `RetrieveChunksNode` may re-embed or read this — for simplicity it re-embeds, and this node documents the question for downstream assembly.)

#### 4.3 Create the answer prompt template
**File:** `app/prompts/document_qa_answer.j2`
**Action:** create the `.j2` with frontmatter (`description`, `author`) and a system-prompt body instructing the model to answer strictly from the provided context, cite section titles, and say "I don't have that in the document" when the context is insufficient. No variables required in the system prompt (context is passed as the user prompt by `AnswerNode`).

#### 4.4 Create `AssembleContextNode`
**File:** `app/workflows/document_qa_workflow_nodes/assemble_context_node.py`
**Action:** plain `Node` — combines RAG context + session memory (the rag-engine-rs `build_rag_prompt` format + per-session history).
- Read retrieved chunks from `RetrieveChunksNode` output.
- Build a context block; for each chunk emit `f"Section: {section_title or 'General'} (relevance: {score:.2f})\n{content}"` joined by blank lines (port of `chat_server.rs` format, including the relevance score).
- Load prior turns: a `_load_session(self, session_id)` seam returns the `ChatSession` (or None) via `GenericRepository`; format prior `turns` as a readable transcript. Patched in tests.
- Store `result={"context": context_block, "history": prior_turns, "question": question}`.

#### 4.5 Create `AnswerNode`
**File:** `app/workflows/document_qa_workflow_nodes/answer_node.py`
**Action:** `AgentNode` subclass.
- `class AnswerOutput(AgentNode.OutputType)`: `answer: str`, `cited_sections: list[str] = Field(default_factory=list)`.
- `get_agent_config`: `system_prompt=PromptManager().get_prompt("document_qa_answer")`, `output_type=AnswerOutput`, `deps_type=None`, `model_provider=ModelProvider.CLAUDE_CODE_SDK`, `model_name="sonnet"` (match `SummarizerNode`).
- `process`: read assembled context; build the user prompt as `history + context + question`; `result = self.run_agent_recorded(task_context, user_prompt)`; `task_context.update_node(node_name=self.node_name, result=result.output)`.

#### 4.6 Create `UpdateSessionMemoryNode`
**File:** `app/workflows/document_qa_workflow_nodes/update_session_memory_node.py`
**Action:** plain `Node` with a `_persist`/`_load` seam.
- Read `question` and the `AnswerNode` answer.
- `_load_session(session_id)` → existing `ChatSession` or None. If None, create `ChatSession(id=event.session_id, doc_id=event.doc_id, turns=[], topics_covered=[])`.
- Append `{"role":"user","content":question}` and `{"role":"assistant","content":answer}` to `turns`; optionally extend `topics_covered` from `cited_sections`.
- `_persist(session)` via `GenericRepository` (`create` if new, `update`/`merge` if existing) using the `db_session` factory.
- Store `result={"session_id": str(event.session_id), "turns": len(session.turns)}`.

#### 4.7 Create `DocumentQAWorkflow`
**File:** `app/workflows/document_qa_workflow.py`
**Action:** `Workflow` subclass, linear DAG.
- Imports `RetrieveChunksNode` from Step 3 plus the four nodes above.
- `workflow_schema = WorkflowSchema(description=..., event_schema=DocumentQAEventSchema, start=EmbedQuestionNode, nodes=[NodeConfig(EmbedQuestionNode, [RetrieveChunksNode]), NodeConfig(RetrieveChunksNode, [AssembleContextNode]), NodeConfig(AssembleContextNode, [AnswerNode]), NodeConfig(AnswerNode, [UpdateSessionMemoryNode]), NodeConfig(UpdateSessionMemoryNode, [])])`.

#### 4.8 Create `tests/workflows/test_document_qa_nodes.py`
**File:** `tests/workflows/test_document_qa_nodes.py`
**Action:** node tests (seed `{"result": ...}`; patch DB/agent seams).
- `EmbedQuestionNode`: patch `EmbeddingService`, assert vector stored.
- `AssembleContextNode`: seed `RetrieveChunksNode` result with two chunks (with `section_title` + `score`); patch `_load_session` to return a session with one prior turn; assert the assembled `context` contains **both** chunk section titles + relevance scores **and** the prior turn (the RAG-vs-session-memory assembly criterion).
- `AnswerNode`: patch `self.agent`/`run_agent_recorded` to return a fake `AnswerOutput`; assert `result` stored under `AnswerNode` with `{"result": ...}`.
- `UpdateSessionMemoryNode`: `patch.object(node, "_load_session", return_value=None)` and `patch.object(node, "_persist")`; assert a new `ChatSession` is persisted with two appended turns; then a second test where `_load_session` returns an existing session and assert turns are appended (not replaced).

#### 4.9 Create `tests/workflows/test_document_qa_workflow.py`
**File:** `tests/workflows/test_document_qa_workflow.py`
**Action:** workflow wiring test — `start is EmbedQuestionNode`, five nodes present, linear connections, `WorkflowValidator` accepts.

**Verify:** `uv run python -m pytest tests/workflows/test_document_qa_nodes.py tests/workflows/test_document_qa_workflow.py -q` → all pass.

---

### Step 5: Register both workflows + integration

#### 5.1 Register workflows in `app/workflows/workflow_registry.py`
**File:** `app/workflows/workflow_registry.py`
**Action:** add `from workflows.document_ingest_workflow import DocumentIngestWorkflow` and `from workflows.document_qa_workflow import DocumentQAWorkflow`; add enum members `DOCUMENT_INGEST = DocumentIngestWorkflow` and `DOCUMENT_QA = DocumentQAWorkflow`.

#### 5.2 Register schemas in `app/api/schema_registry.py`
**File:** `app/api/schema_registry.py`
**Action:** import `DocumentIngestEventSchema` and `DocumentQAEventSchema`; add `WorkflowRegistry.DOCUMENT_INGEST.name: DocumentIngestEventSchema` and `WorkflowRegistry.DOCUMENT_QA.name: DocumentQAEventSchema` to `SCHEMA_MAP` (CLAUDE.md rule 6 — `TestSchemaRegistryCompleteness` enforces this).

**Verify:** `cd app && uv run python -c 'import main'` → exit 0; `cd app && uv run python -c 'import worker.config'` → exit 0; `uv run python -m pytest tests/api/test_endpoint.py -q` → `TestSchemaRegistryCompleteness` passes.

---

### Step 6: Documentation

#### 6.1 Append node + workflow sections to `docs/api-reference.md`
**File:** `docs/api-reference.md`
**Action:** append (do not rewrite existing rows; declare additive) `##` sections for `DocumentIngestWorkflow`, `DocumentQAWorkflow`, and each new node. Document `RetrieveChunksNode` thoroughly — the `corpus` parameter, the two-stage semantic→keyword algorithm, the section-title 2x weight, and the `k`/`threshold` params (it is reused verbatim downstream). Update the TOC if present.

#### 6.2 Append a "What shipped" row to `docs/app-architecture-overview.md`
**File:** `docs/app-architecture-overview.md`
**Action:** append one row for Project D (additive — the recurring parallel-doc-merge point; keep both rows on any conflict).

**Verify:** `grep -c "RetrieveChunksNode" docs/api-reference.md` → ≥ 1; fence-balance check (even count of ```` ``` ````).

---

### Step 7: Validate

#### 7.1 Run the full validation suite
**Action:** run every command in **Validation Commands** below, in order; confirm all pass and the collected test count is ≥ 549 and not decreased from the previous run.

**Verify:** `uv run python -m pytest` → 0 failures; `uv run python -m pylint app/` → 10.00/10 (or no net-new violations); `uv run python -m ruff check app/` → clean.

---

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
- **Migration head is load-bearing.** The current single head is `020c9f7f89e2` (a merge node). The new migration MUST set `down_revision = "020c9f7f89e2"` or it creates a third head and `alembic upgrade head` fails (the dual-head problem already hit once — see status.md 2026-06-22 / D31). If a concurrent migration lands first, run `alembic merge` rather than re-parenting.
- **SQLite test reach.** `ContentChunk` (Vector) and `ChatSession` (JSON) compile under in-memory SQLite, so model tests follow the `test_learning_artifact.py` single-table-engine pattern. They do NOT need the `conftest.py` `_POSTGRES_ONLY_TABLES` exclusion (that is only for `ARRAY`). Retrieval and persistence DB calls are mocked in node tests (`_semantic_search`/`_keyword_search`/`_persist`/`_load_session`), so no live pgvector is exercised in the suite — the two-stage SQL itself is validated manually/at integration time, not in unit tests. Note this gap explicitly when documenting.
- **Disjoint file ownership / parallel-merge safety:**
  - Steps 3 and 4 both create files under `app/workflows/document_qa_workflow_nodes/` but **different files** (Step 3 owns `retrieve_chunks_node.py`; Step 4 owns the other four nodes). Step 4 `dependsOn` Step 3 (it imports `RetrieveChunksNode`), so they serialize into different waves — no collision.
  - Step 5 edits the two shared registry files (`workflow_registry.py`, `schema_registry.py`); it `dependsOn` Steps 2 and 4 and runs alone in its wave — no other task touches those files.
  - Step 1's edit to `app/database/__init__.py` is the only write to that file in the block (append-only).
  - Step 6's doc files are **additive** — declare them so in the execution plan; expect (and hand-resolve "keep both rows") on `docs/app-architecture-overview.md` per the recurring lesson.
- **`run_agent_recorded`, not `run_sync`.** `AnswerNode` must call `self.run_agent_recorded(task_context, user_prompt)` so per-node telemetry (input/usage/output) is captured by the framework — the data contract bastion reads (D30). Calling `self.agent.run_sync` directly silently drops telemetry.
- **`corpus` reconciliation:** per the spec, `"content"` → `content_chunks` (this project's ingested docs), `"brain"` → `brain_documents`. The `notes.md` `learning_artifacts` corpus is deferred to Project F. Build the `_semantic_search` corpus dispatch as a small mapping so a third corpus is a one-line add, not a refactor.
