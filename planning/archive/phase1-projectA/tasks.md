# Task Spec — Phase 1, Project A: Content Pipeline

## Goal
Build the `content_pipeline` workflow: a source-routed pipeline that turns a YouTube URL or article URL into a categorized, embedded `LearningArtifact` plus a static-HTML personal digest (always), and — only when `make_blog=true` — a self-corrected blog draft.

## Context Pointers
- **Plan (the *what*):** `planning/master-plan.md` → "Block 1 — Project A" (lines ~207–216).
- **Plan (the *how*):** `planning/Agentic_Engineering_Projects_and_Learning_Plan.md` → "Project A — Content Pipeline" (lines ~228–287). Read the End-result node list, Build notes, and the Tests section — they define the node set, the `SummaryOutput` fields, the trafilatura-first/Firecrawl-fallback rule, and the embed-at-write-time requirement.
- **Decisions:** D21 (knowledge-feed-first, digest-always/blog-on-flag), D22 (MVP boundary — ingestion + store + dumb display *only*; no search/tagging/sync UI), D24 (trafilatura-first, Firecrawl-fallback, `max_calls` guard). Do **not** build search/"what I know"/tagging — those are Projects F/G.
- **Repo conventions (`CLAUDE.md`):** every workflow ships with tests (rule 1); no hardcoded prompts — all `.j2` in `app/prompts/`, loaded via `PromptManager` (rule 2); register new workflows (rule 6 — already done in scaffold); no deployment/persistence logic inside nodes except via injected repository/services (rule 7); Python 3.10+ type syntax, module docstring on line 1, `raise ... from e`, no f-strings in logging, `open(..., encoding="utf-8")` (Code style rules).
- **Reference pattern (do not modify):** `app/workflows/customer_care_workflow.py` + its `*_nodes/` — the canonical `AgentNode` (`generate_response_node.py`), `BaseRouter`/`RouterNode` (`ticket_router_node.py`), and `ParallelNode` (`analyze_ticket_node.py`) shapes.
- **Reuse, don't rebuild:** `services/transcript_service.py` (`TranscriptService.fetch_transcript`), `services/article_extraction_service.py` (`ArticleExtractionService.extract` → `ArticleResult{text,title,fetch_status}`), `services/embedding_service.py` (`EmbeddingService.embed_text` → `list[float]`, 1024-dim Voyage), `services/chunking_service.py`. pgvector extension is already enabled (`app/alembic/versions/12a5c7643ab9_*`).
- **Entry point — no new endpoint needed.** The API is a generic dispatcher: clients POST to `/events/` with `{"workflow_type": "CONTENT_PIPELINE", "data": {"url": ..., "make_blog": ...}}`. `CONTENT_PIPELINE` is already in `workflow_registry.py` and `api/schema_registry.py` — **leave both untouched.** The plan's "`POST /events/content`" is shorthand for this dispatch.

## Scaffold state (starting point)
- `app/workflows/content_pipeline_workflow.py` — stub wiring a single `InitialNode`.
- `app/workflows/content_pipeline_workflow_nodes/{__init__.py (empty), initial_node.py (no-op)}`.
- `app/schemas/content_pipeline_schema.py` — empty `ContentPipelineEventSchema(BaseModel)`.
- `tests/workflows/test_content_pipeline_workflow.py` — scaffold smoke tests asserting the stub state (empty schema, `start is InitialNode`). These assertions become wrong as real work lands; Task 1 and Task 7 are the only tasks that edit this file (serialized by dependency — see below).

## Parallel-merge file ownership (read before decomposing further)
Each task owns a **distinct set of files** so `/sdlc-block` waves merge cleanly. New node files live under `app/workflows/content_pipeline_workflow_nodes/`; each node task also adds its **own** new test file under `tests/workflows/content_pipeline/` (the package `__init__.py` is empty and nodes are imported by path, so adding files never collides). The only pre-existing shared file is `tests/workflows/test_content_pipeline_workflow.py`, edited by Task 1 (one assertion) then Task 7 (full rewrite) — safe because Task 7 `dependsOn` Task 1 and runs in a later wave. **Never net-decrease test count** (the `pytest-count` gate fails on a drop): when replacing a scaffold smoke test, replace it with an equal-or-greater number of real tests.

## Step-by-Step Tasks

### 1. Event schema  *(owns: `app/schemas/content_pipeline_schema.py`; edits one assertion in `tests/workflows/test_content_pipeline_workflow.py`)*  — deps: none
- Fill in `ContentPipelineEventSchema`: `url: str` (required), `make_blog: bool = False`. Mirror `customer_care_schema.py` conventions — add an `artifact_id: UUID = Field(default_factory=uuid4)` and a `timestamp` default if useful for storage/identity, but keep it minimal.
- In `test_content_pipeline_workflow.py`, replace `test_event_schema_is_pydantic_stub` (which asserts `model_dump() == {}`) with a real test asserting the new fields and the `make_blog` default — **net test count must not drop.** Leave the registration / `start is InitialNode` / instantiation smoke tests untouched (still true at this point).

### 2. `LearningArtifact` model + migration  *(owns: `app/database/learning_artifact.py`, a new `app/alembic/versions/*.py`, one import line in `app/alembic/env.py`, `tests/database/test_learning_artifact.py`)*  — deps: none
- Add a `LearningArtifact` SQLAlchemy model (same `Base` as `database/event.py`): `id` (UUID pk), `source_url`, `source_type` ("youtube"|"article"), `title`, `category`, `tl_dr`, `summary` (JSON — the full structured `SummaryOutput`), `embedding` (pgvector `Vector(1024)` — use `pgvector.sqlalchemy.Vector`), `fetch_status`, `make_blog` (bool), `created_at`. JSON columns for the structured fields, mirroring `event.py`'s column style.
- Import the model in `app/alembic/env.py` (next to `from database.event import *`) so autogenerate/metadata sees it.
- Add an Alembic migration creating the `learning_artifacts` table (hand-author the `op.create_table` with the `Vector` column, following the existing version file's structure; `down_revision` = the pgvector revision `12a5c7643ab9`). Verify `alembic upgrade head` applies cleanly.
- Test: model imports, table name, columns/types present, instantiation round-trips through `GenericRepository` against the test DB (follow `tests/database/test_repository.py`).

### 3. Source router + fetch nodes  *(owns: `source_router_node.py`, `fetch_transcript_node.py`, `fetch_article_node.py`, `tests/workflows/content_pipeline/test_fetch_nodes.py`)*  — deps: Task 1
- `FetchTranscriptNode(Node)` — reads `task_context.event.url`, calls `TranscriptService().fetch_transcript(url)`, stores raw text via `task_context.update_node(...)`. On the service's `ValueError`/`RuntimeError`, store a `fetch_status="failed"` marker and don't crash the pipeline.
- `FetchArticleNode(Node)` — the one genuinely new node. Calls `ArticleExtractionService().extract(url)`, stores `text`/`title`/`fetch_status` from the returned `ArticleResult`. The service never raises; propagate `fetch_status` ("ok"|"fallback_used"|"failed") into node output. (trafilatura-first/Firecrawl-fallback already lives in the service — D24.)
- `SourceRouterNode(BaseRouter)` + `RouterNode` subclasses — classify `event.url` as YouTube (`youtube.com`/`youtu.be`) vs article and route to the matching fetch node; fallback = `FetchArticleNode`. Follow the `ticket_router_node.py` shape (router stamps `{"next_node": ...}`).
- Tests: YouTube URL → routes to transcript node; article URL → routes to article node; unknown → article fallback; each fetch node's success path (mock the service) and graceful-failure path (assert no raise, `fetch_status` set).

### 4. Summarizer node + prompt  *(owns: `summarizer_node.py`, `app/prompts/content_summarizer.j2`, `tests/workflows/content_pipeline/test_summarizer_node.py`)*  — deps: Task 1
- `SummarizerNode(AgentNode)` with a nested `OutputType` (the `SummaryOutput` schema) fields per the plan: `title`, `category` (free-string classified into a small starting set `ai_engineering`/`physics_relativity`/`music`/`other` — *not* a rigid enum), `tl_dr` (one line), `read_time_estimate`, `core_concepts`, `key_insights`, `questions_raised`, `connections_to_my_work`, `further_exploration`.
- `get_agent_config()` loads the system prompt via `PromptManager().get_prompt("content_summarizer")` and uses a top-tier Anthropic model (`ModelProvider.ANTHROPIC`, current Claude — per CONTEXT model strategy "top-tier everywhere on first run-through"). Call `self.run_agent_recorded(task_context, user_prompt)` (not `agent.run_sync`) so per-node token telemetry is captured.
- `process()` reads the upstream fetched text (transcript or article) from `task_context`, runs the agent, stores the result. Define `SummaryOutput` in this module (Storage imports it in Task 5).
- `content_summarizer.j2`: the structured-summary system prompt, biased toward agentic/harness/AI-architecture/RAG-memory topics *and* the personal categories (physics/relativity, music) per Build notes. No hardcoded prompt text in Python.
- Tests: with a mocked agent, assert the node populates a `SummaryOutput` with the expected fields and reads the correct upstream text.

### 5. Storage node (persist + embed + render)  *(owns: `storage_node.py`, an HTML-render helper e.g. `app/workflows/content_pipeline_workflow_nodes/digest_renderer.py`, `tests/workflows/content_pipeline/test_storage_node.py`)*  — deps: Task 2, Task 4
- `StorageNode(Node)` — for **every** item (digest-only included): (a) embed the summary text at write time via `EmbeddingService().embed_text(...)`; (b) persist a `LearningArtifact` row (embedding + structured summary + source/category/fetch_status) through an **injected `GenericRepository`/session** — never open a session inside the node (rule 7; persistence is injected, mirroring how the worker injects `on_progress`); (c) write a static HTML page for the item into the right category folder and regenerate that category's index page.
- HTML rendering helper: deliberately dumb static HTML (one page per item + per-category index). No JS, no search box, no tagging — D22. Output dir comes from config/env, not hardcoded to a deployment path (rule 7).
- Reads `SummaryOutput` via `task_context.get_node_output("SummarizerNode")` (import the type from Task 4's module for typing).
- Tests (mock embedding service + repository + a tmp output dir): assert embedding written at write time, `LearningArtifact` created with the embedding, HTML page written, category index regenerated. Note how the node receives its repository (injection point) — surface it in the test so Task 7 wires it the same way.

### 6. Blog branch (writer → self-critic → revise) + blog router  *(owns: `blog_decision_router_node.py`, `blog_writer_node.py`, `self_critic_node.py`, `revise_node.py`, `app/prompts/{blog_writer,blog_self_critic,blog_reviser}.j2`, `tests/workflows/content_pipeline/test_blog_branch.py`)*  — deps: Task 4
- `BlogDecisionRouterNode(BaseRouter)` — routes to `BlogWriterNode` when `event.make_blog` is true; fallback = `None` (digest-only path terminates after storage — `BaseRouter.route` returning `None` ends the run).
- `BlogWriterNode(AgentNode)` — drafts a blog post in Brandon's voice from the `SummaryOutput`; voice guidance lives in `blog_writer.j2` (a long-term asset, reused in Project C). `SelfCriticNode(AgentNode)` — critiques the draft. `ReviseNode(AgentNode)` — applies the critique. **Linear** writer→critic→revise (the validator forbids cycles — no loop-back). All three use `run_agent_recorded` and load prompts via `PromptManager`.
- Tests: blog router routes to writer only when `make_blog=true` (and to `None`/terminal otherwise); the three agent nodes run in order with mocked agents and thread the draft through critique→revision.

### 7. Workflow wiring + integration tests  *(owns: `app/workflows/content_pipeline_workflow.py`, deletes `initial_node.py`, rewrites `tests/workflows/test_content_pipeline_workflow.py`)*  — deps: Tasks 3, 4, 5, 6
- Rewrite `ContentPipelineWorkflow.workflow_schema`: `start=SourceRouterNode`; wire `SourceRouterNode` (router) → fetch nodes; each fetch node → `SummarizerNode`; `SummarizerNode` → `StorageNode`; `StorageNode` → `BlogDecisionRouterNode` (router); `BlogDecisionRouterNode` → `BlogWriterNode`; `BlogWriterNode` → `SelfCriticNode` → `ReviseNode`. Mark the two routers `is_router=True` in their `NodeConfig` (per `customer_care_workflow.py`). Fill in `description`s.
- Delete `initial_node.py` (the scaffold no-op) and remove its references.
- Wire `StorageNode`'s repository injection at the workflow/worker boundary consistent with Task 5's injection point — confirm the framework stays deployment-agnostic (no persistence decisions inside nodes).
- Rewrite `test_content_pipeline_workflow.py`: keep the registration test; replace the `InitialNode` structural assertions with the new graph (start node, router flags, connection map, `WorkflowValidator` passes — no cycles). Add **two integration tests** running the full chain with all agents/services mocked: (a) `make_blog=false` → digest-only path runs fetch→summarize→store and the blog nodes do **not** run; (b) `make_blog=true` → blog nodes also run. **Net test count must not drop** vs the scaffold smoke tests being replaced.

### 8. Validate
- Run the Validation Commands below and confirm all pass (lint clean, full suite green, app + worker import, migration applies).

## Acceptance Criteria
- POSTing `{"workflow_type":"CONTENT_PIPELINE","data":{"url":"<youtube-or-article>","make_blog":false}}` to `/events/` runs `SourceRouterNode → fetch → SummarizerNode → StorageNode` and produces a `LearningArtifact` row **with a non-null 1024-dim embedding written at write time** plus a static HTML digest page and a regenerated category index — and the blog nodes do **not** execute.
- With `make_blog=true`, the same chain additionally runs `BlogWriterNode → SelfCriticNode → ReviseNode` (linear, no cycle) and writes a blog draft.
- YouTube URLs route to the transcript fetch node; article URLs route to the article fetch node; extraction failures set `fetch_status` and never crash the pipeline.
- All prompts are `.j2` files in `app/prompts/` loaded via `PromptManager` — zero prompt strings hardcoded in Python.
- No persistence/session or deployment-path logic lives inside any node (injected repository/services + config-supplied output dir only); `customer_care` is untouched.
- `WorkflowValidator` passes for the assembled graph (no cycles, all connections resolve).
- `uv run python -m pytest` passes with **more** tests than before this spec (every new node + 2 integration tests), and the `pytest-count` gate never decreases across tasks.
- `alembic upgrade head` applies the `learning_artifacts` migration cleanly; ruff + pylint clean; `import main` and `import worker.config` succeed.

## Validation Commands
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
cd app && alembic upgrade head
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
```

## Notes
- Registry (`workflow_registry.py`) and `api/schema_registry.py` already wire `CONTENT_PIPELINE` — do not edit them.
- Model strategy: top-tier Anthropic on this first run-through (CONTEXT / D19); local-model swaps come later via Project H. Voyage embeddings are the standing default.
- Deliberately **out of scope** (D22): search box, tagging UI, "what I already know" intelligence, cross-device sync, weekly EPUB-to-Kindle, one-tap capture app. Those are Projects F/G or just-in-time upgrades.
