---
type: Architecture
title: App Architecture Overview
description: Codebase analysis of the FastAPI -> Celery -> Workflow DAG -> TaskContext architecture for agentic engineering projects.
---

# App Architecture Overview
## Codebase Analysis for Agentic Engineering Projects

*Reviewed: May 2026 · Updated: June 2026 (Phase 0 Block D — shared services layer, `ToolUseNode`, pgvector, clean API contract) · Scope: `app/` directory*

---

## High-Level Summary

This codebase is a **production-ready event-driven AI pipeline framework**. It is not a demo — it is infrastructure. The core abstractions (Workflow, Node, TaskContext, AgentNode) are clean, composable, and directly applicable to every project in the learning plan. The domain-specific code (Customer Care workflow) is just one example sitting on top of that infrastructure and is fully replaceable.

The mental model: **this is the scaffold, not the content**. Every project in the learning plan is a new workflow you build using these building blocks.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         INFRASTRUCTURE                               │
│                                                                     │
│  FastAPI ──► Endpoint ──► GenericRepository ──► PostgreSQL          │
│      │                                                              │
│      └──► Celery Task Queue ──► Worker ──► WorkflowRegistry        │
│                                                     │               │
│                            Redis (broker/backend) ◄─┘               │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         CORE ENGINE                                  │
│                                                                     │
│  Workflow (DAG orchestrator)                                        │
│    ├── WorkflowSchema (node graph definition)                       │
│    ├── WorkflowValidator (DAG integrity: cycle detection, BFS)      │
│    └── run() → TaskContext                                          │
│                                                                     │
│  Node (abstract base: Chain of Responsibility)                      │
│    ├── AgentNode (pydantic-ai wrapper: multi-provider AI calls)     │
│    ├── ParallelNode (ThreadPoolExecutor for concurrent nodes)       │
│    └── BaseRouter + RouterNode (conditional branching)              │
│                                                                     │
│  TaskContext (Pydantic model — shared state across all nodes)       │
│    ├── event: Any (the trigger event, parsed to schema)             │
│    ├── nodes: Dict[str, Any] (each node's output, keyed by name)   │
│    └── metadata: Dict (workflow-level config, node registry)       │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         SUPPORT SERVICES                             │
│                                                                     │
│  PromptManager (Jinja2 + frontmatter — .j2 template files)         │
│  GenericRepository (SQLAlchemy CRUD: create/get/update/delete)      │
│  DatabaseUtils (connection string from env vars)                    │
│  WorkflowInitCommand (`createworkflow` CLI scaffolding tool)        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Component-by-Component Analysis

### ✅ CORE ENGINE — Keep and extend aggressively

#### `core/workflow.py` — `Workflow` class
The orchestrator. Reads a `WorkflowSchema` (a DAG declaration), walks it node by node, passes `TaskContext` through the chain, handles routing. Validates the graph before running.

**Why it's excellent:** The `while current_node_class:` loop at the heart of `run()` is exactly the agentic pipeline loop — it's the same pattern described in Project 4 (Orchestrator), already built and validated. Every project in the learning plan maps onto this.

**Limitation:** The validator enforces strict DAGs (no cycles). Self-correction loops (Project 2's critic → revise pattern) cannot be implemented as cycles in a single workflow. **Solution:** Use sub-workflows (a `CorrectiveWorkflow` that runs as a unit inside a parent node) or run them as separate `Workflow.run()` calls chained in a parent node.

---

#### `core/task.py` — `TaskContext`
Pydantic model that carries all state through the pipeline. Nodes write via `task_context.update_node(node_name, **kwargs)`. Nodes read via `task_context.get_node_output(node_name)` — preferred over direct `task_context.nodes[node_name]` access in router nodes because it raises a descriptive `KeyError` that names the missing node and lists all completed nodes, making workflow ordering errors immediately diagnosable.

**Why it's excellent:** This is exactly the "state passing" pattern from Project 4. The `nodes` dict functions as a ledger of everything the pipeline has computed so far — any downstream node can read any upstream node's result. This is more flexible than explicit parameter threading.

---

#### `core/nodes/base.py` — `Node` ABC
One abstract method: `process(task_context: TaskContext) -> TaskContext`. Clean. Every agent, every transformer, every side-effect handler is a Node.

**No changes needed.**

---

#### `core/nodes/agent.py` — `AgentNode`
The most important node type. Wraps `pydantic-ai`'s `Agent` class with:
- Multi-provider support: OpenAI, Azure OpenAI, Anthropic, Gemini, Ollama, AWS Bedrock
- Typed `OutputType` (structured output via Pydantic)
- Typed `DepsType` (context injection into system prompts)

**Critical design note:** This uses `pydantic-ai`, not the raw Anthropic SDK. The learning plan code examples use `anthropic.Anthropic()` directly. You have two options:
1. **Use pydantic-ai for all agents** (recommended) — switch `ModelProvider.ANTHROPIC` with `model_name="claude-opus-4-7"`. You get structured output, multi-provider, and a cleaner interface at the cost of one abstraction layer.
2. **Use raw Anthropic SDK** in a custom `AnthropicAgentNode` — useful if you want to implement tool use loops yourself (educational value) or if you need fine-grained control over streaming/caching.

**Limitation for learning:** `AgentNode.__init__` calls `Agent()` from pydantic-ai which wraps the tool loop for you. For Projects 2–4 where the learning goal *is* the agentic tool loop, you may want to implement a bare `ToolUseNode` that uses `anthropic.Anthropic()` directly and manages the `while stop_reason == "tool_use"` loop yourself. This is educational — do it at least once.

**Extension — done (Block D):** the bare `ToolUseNode` (raw `anthropic.Anthropic()`, explicit
`while stop_reason == "tool_use"` loop, bounded by `max_iterations`) now lives in `core/nodes/tool_use.py`.
See its entry under "Shared Services Layer" below and the signature in [api-reference.md](api-reference.md).

---

#### `core/nodes/parallel.py` — `ParallelNode`
Runs multiple nodes concurrently via `ThreadPoolExecutor`. Used in the Customer Care workflow to run FilterSpam, DetermineIntent, and ValidateTicket simultaneously.

**Why it's excellent:** Directly maps to Project 2's research agent (parallel web search + arXiv search), Project 4's multi-agent pipeline (parallel analysis passes), and the Socratic Tutor's curiosity threads running while the spine continues.

**Limitation:** Results from parallel nodes are returned as a list of `TaskContext` objects but the current implementation doesn't merge them back into the main context — the calling `AnalyzeTicketNode.process()` just calls `execute_nodes_in_parallel()` and discards the list. Each parallel node writes to the shared `task_context` directly (it's mutable), which works but isn't clean with thread safety. **Solution when extending:** Have each parallel node write to a uniquely keyed slot in `task_context.nodes` and merge after.

---

#### `core/nodes/router.py` — `BaseRouter` / `RouterNode`
Declarative routing: define a list of `RouterNode` instances, each returning the next node class if its condition is met, or `None` to fall through. The first match wins; a `fallback` handles the no-match case.

**Why it's excellent:** This is exactly the routing you need for every conditional branch in the learning plan: "did research find enough information?" → critic vs. finalize; "is this a billing question?" → invoice node; "does the tutor need to chase a curiosity thread?" → research branch vs. continue spine.

**No changes needed.** Just write new `RouterNode` subclasses.

---

#### `core/schema.py` — `WorkflowSchema` / `NodeConfig`
Declarative graph definition. `WorkflowSchema(start=X, nodes=[NodeConfig(node=X, connections=[Y, Z], is_router=True)])` is all you need to define a multi-node pipeline.

**Why it's excellent:** Forces you to think about your workflow as a graph before writing any agent code. The `createworkflow` CLI even scaffolds this for you.

**No changes needed.**

---

#### `core/validate.py` — `WorkflowValidator`
DFS cycle detection + BFS reachability check. Runs on every `Workflow.__init__()`. Prevents misconfigured graphs from running silently.

**No changes needed.**

---

### ✅ INFRASTRUCTURE — Solid foundation, needs targeted extensions

#### `database/` — SQLAlchemy + PostgreSQL
- `DatabaseUtils`: env-var-driven connection string
- `session.py`: `db_session()` generator, `Base`, lazy `_get_engine()` (engine created on first call, not at import time)
- `repository.py`: Generic CRUD repository — `create`, `get`, `get_all`, `update`, `delete`, `get_latest`, `count`
- `event.py`: `Event` model (UUID pk, `workflow_type`, `data` JSON, `task_context` JSON, timestamps)

**What's reusable:** `DatabaseUtils`, `db_session`, `GenericRepository` — all of it. Every new model (content chunks, learning artifacts, agent episodes) follows the same pattern.

**Status (post Block D):**
- pgvector — extension now **enabled** by migration (`supabase/postgres:15.8.1` ships it); vector *columns* still to add per project.
- `EmbeddingService` (Voyage AI) — **built** (`app/services/embedding_service.py`).
- `LearningArtifact` — **built** (`app/database/learning_artifact.py`, Phase 1 Project A Task 2); `Vector(1024)` embedding column backed by pgvector. Migration `a1b2c3d4e5f6` chains off the pgvector extension revision.
- `BrainDocument` — **built** (`app/database/brain_document.py`, brain-rag Layer 1); `Vector(1024)` embedding + `ARRAY(String)` workflow_patterns; populated by `scripts/index_brain.py`. Migration `b3c4d5e6f7a8` chains off `a1b2c3d4e5f6`. Query path (RetrieveChunksNode corpus parameter) ships with Project D.
- Still to add: `ContentChunk` (Project D) and `AgentEpisode` / `SemanticMemory` (Project G) — built with the project that stores them.

---

#### `worker/` — Celery + Redis
The async task queue. Events are accepted by FastAPI, persisted to DB, queued via Celery, and processed by the worker which runs the workflow.

**Why it matters:** This is what makes the YouTube pipeline (Project 0), research agent (Project 2), and every long-running pipeline work without blocking the HTTP response. The accept-and-delegate pattern is the right architecture for anything that takes more than ~500ms.

**No structural changes needed.** Just add new `@celery_app.task` functions for new workflow types.

---

#### `services/prompt_loader.py` — `PromptManager`
Jinja2 templates with YAML frontmatter. Store prompts as `.j2` files, render them with variables at runtime. `PromptManager.get_prompt("template_name", var1=x, var2=y)`.

**Why it's excellent:** Separates prompts from code. All 8 projects need multiple system prompts — this prevents prompt strings from polluting Python files. The frontmatter metadata (description, author, model target) is also useful for documentation.

**No changes needed.** Just add new `.j2` files for each project's prompts.

---

#### `core/commands/init_workflow.py` — `createworkflow` CLI
Scaffolds a new workflow directory, workflow class, and schema in seconds. Run `uv run createworkflow` (or `python -m core.commands.init_workflow`).

**Use this.** It saves 15 minutes of boilerplate per project.

---

### ❌ DOMAIN CODE — Do not extend; treat as reference implementation only

The Customer Care workflow is a **worked example**, not a foundation to build on. Its only value is showing you how the core abstractions are used in practice:

| File | Status | Notes |
|---|---|---|
| `workflows/customer_care_workflow.py` | Reference only | Shows WorkflowSchema + parallel + router composition |
| `workflows/customer_care_workflow_nodes/*.py` | Reference only | Shows AgentNode, ParallelNode, RouterNode implementations |
| `schemas/customer_care_schema.py` | Reference only | Shows event schema pattern |
| `prompts/*.j2` | Reference only | Shows PromptManager template format |
| `api/endpoint.py` | Modify | Replace `CustomerCareEventSchema` with a generic event dispatcher |

---

### ✅ SHARED SERVICES LAYER — built in Phase 0, Block D

Most of what this section originally listed as "to build" now exists. Phase 0 Block D added a
first-class **services layer** (`app/services/`) alongside the core engine, plus a raw-SDK node type,
the pgvector extension, the first project scaffold, and a clean generic API contract. Precise
class-level signatures live in [api-reference.md](api-reference.md); env vars in
[configuration.md](configuration.md). What shipped:

| Built | Where | Notes |
|---|---|---|
| pgvector **extension** | Alembic migration (`enable_pgvector_extension`) | `CREATE EXTENSION IF NOT EXISTS vector;` — extension only; vector *columns* come with the models below |
| `EmbeddingService` | `services/embedding_service.py` | Voyage AI; provider/model/dims are constructor params — the config-swap seam Project H evaluates (a local model slots in without code changes) |
| `TranscriptService` | `services/transcript_service.py` | YouTube transcript fetch + delegate-to-`ChunkingService` |
| `ArticleExtractionService` | `services/article_extraction_service.py` | trafilatura-first, Firecrawl fallback for JS pages; returns `ArticleResult`, never raises |
| `SearchService` | `services/search_service.py` | Tavily wrapper → typed `SearchResult` list for tool-use loops |
| `ChunkingService` | `services/chunking_service.py` | `tiktoken` token-boundary chunking; PDF via `pymupdf` |
| `ToolUseNode` | `core/nodes/tool_use.py` | raw Anthropic SDK tool loop (the "educational loop" below) — abstract base; subclass + implement `handle_tool_call`; bounded by `max_iterations`; model from `TOOL_USE_MODEL` env |
| Generic API contract | `api/endpoint.py`, `api/health.py`, `api/schema_registry.py`, `api/models.py` | `EventPayload` dispatcher (schema looked up by `workflow_type`, `422` on unknown), `GET /health`, typed `TaskAcceptedResponse` — the brain's HTTP surface that shells drive (D16 Layer 3) |
| Project A — Task 1 | `workflows/content_pipeline_workflow*`, `schemas/content_pipeline_schema.py` | `ContentPipelineEventSchema` has real fields: `url: str` (required), `make_blog: bool = False`, `artifact_id: UUID` (auto-generated), `timestamp: datetime` (UTC auto-set); registered as `WorkflowRegistry.CONTENT_PIPELINE` |
| Project A — Task 3 | `workflows/content_pipeline_workflow_nodes/source_router_node.py`, `fetch_transcript_node.py`, `fetch_article_node.py` | `SourceRouterNode(BaseRouter)` routes by URL hostname: YouTube (`youtube.com`/`youtu.be`) → `FetchTranscriptNode`; all others → `FetchArticleNode` (fallback). `FetchTranscriptNode` calls `TranscriptService.fetch_transcript`, catches `ValueError`/`RuntimeError`, sets `fetch_status="failed"` without crashing. `FetchArticleNode` calls `ArticleExtractionService.extract` (trafilatura-first/Firecrawl-fallback, D24) and propagates `text`/`title`/`fetch_status` from `ArticleResult`. |
| Project A — Task 4 | `workflows/content_pipeline_workflow_nodes/summarizer_node.py`, `prompts/content_summarizer.j2` | `SummarizerNode(AgentNode)` with `SummaryOutput` (9-field Pydantic schema: `title`, `category`, `tl_dr`, `read_time_estimate`, `core_concepts`, `key_insights`, `questions_raised`, `connections_to_my_work`, `further_exploration`). Loads system prompt from `content_summarizer.j2` via `PromptManager`; uses `ModelProvider.ANTHROPIC` / `claude-opus-4-8`. Calls `run_agent_recorded()` for per-node telemetry. Reads upstream text from `FetchTranscriptNode` or `FetchArticleNode` defensively (empty string on fetch failure). `SummaryOutput` exported for `StorageNode` (Task 5) import. |
| Project A — Task 5 | `workflows/content_pipeline_workflow_nodes/storage_node.py`, `workflows/content_pipeline_workflow_nodes/digest_renderer.py` | `StorageNode(Node)`: embeds summary text at write time via `EmbeddingService().embed_text(...)` (title + tl_dr + core_concepts), persists a `LearningArtifact` row via `GenericRepository` + `db_session` factory (single deployment-agnostic seam, rule 7), writes a static HTML artifact page, and regenerates the category index. Output dir from `CONTENT_DIGEST_DIR` env. `digest_renderer` is a pure-function module: `render_artifact_page` writes `output_dir/<category>/<artifact_id>.html`; `regenerate_category_index` rewrites `output_dir/<category>/index.html`. No JS/search/tagging (D22). |
| Project A — Task 6 | `workflows/content_pipeline_workflow_nodes/blog_decision_router_node.py`, `blog_writer_node.py`, `self_critic_node.py`, `revise_node.py`; `prompts/blog_writer.j2`, `blog_self_critic.j2`, `blog_reviser.j2` | Blog branch: `BlogDecisionRouterNode(BaseRouter)` gates on `event.make_blog` — routes to `BlogWriterNode` when true, terminates (no fallback) when false. Linear chain: `BlogWriterNode → SelfCriticNode → ReviseNode` (no cycle; `ReviseNode` is terminal). All three are `AgentNode` subclasses using `ModelProvider.ANTHROPIC` / `claude-opus-4-8` with `run_agent_recorded()` and `PromptManager`-loaded `.j2` prompts. `BlogWriterNode` reads `SummarizerNode` output; `SelfCriticNode` reads the draft; `ReviseNode` threads both draft and critique. |
| Project A — Task 7 | `workflows/content_pipeline_workflow.py`, `core/nodes/router.py` | Full DAG wired: `start=SourceRouterNode`; graph is `SourceRouterNode → (FetchTranscriptNode | FetchArticleNode) → SummarizerNode → StorageNode → BlogDecisionRouterNode → (BlogWriterNode → SelfCriticNode → ReviseNode)`. Both routers carry `is_router=True` in their `NodeConfig`; `ReviseNode` is terminal. Scaffold `initial_node.py` deleted. Also fixes a latent framework bug: `BaseRouter.process()` previously called `next_node.node_name` unconditionally, crashing when a router legitimately returns `None` (terminal branch); the guard `next_node.node_name if next_node else None` is now applied. Two end-to-end integration tests cover digest-only (`make_blog=False`, blog nodes stay PENDING, 1024-dim embedding persisted) and blog-enabled (`make_blog=True`, full linear blog branch runs) paths. |
| Project A — follow-up | `workflows/content_pipeline_workflow_nodes/translate_ptbr_node.py`, `prompts/translate_ptbr.j2`, `workflows/content_pipeline_workflow.py` | PT-BR translation added to the blog branch (reuse-spec port of the site's `claude-translator.ts`). `TranslatePtBrNode(AgentNode)` is now the terminal node — `ReviseNode → TranslatePtBrNode` — translating the finished EN post to Brazilian Portuguese for the brand's PT+EN cadence. `OutputType`: `translated_title`, `translated_body_markdown`, `confidence`, `cultural_notes`, `technical_terms` (nested `TranslatedTerm`). `ModelProvider.ANTHROPIC` / `claude-opus-4-8` (top-tier first run; Project H downgrade candidate). Gated by the existing `make_blog` branch, so digest-only runs skip it. |

The `WorkflowRegistry` enum scaling concern is resolved in practice: each project adds one entry
(`CONTENT_PIPELINE` is the first beyond `customer_care`).

### ⚠️ STILL TO BUILD (per project, just-in-time)

Deliberately **not** built yet — these arrive with the project that needs them, not before:

- **Remaining vector-column models.** `LearningArtifact` (Phase 1 Project A) and `BrainDocument` (brain-rag Layer 1) now exist. Still to add:
  `ContentChunk(doc_id, position, content, embedding vector(1024))` with Project D;
  `AgentEpisode` / `SemanticMemory` (multi-peer) with Project G.
- **`ParallelNode` result-merge.** Still the known gap (see ParallelNode above) — fix it in Project E,
  where parallel passes first need their outputs merged back via uniquely-keyed slots.

---

## The One Design Decision (resolved: **Both**)

> **Resolved in Block D.** Both node types now exist: `AgentNode` (pydantic-ai) and `ToolUseNode`
> (raw Anthropic SDK). Use the matrix below to choose per node — `AgentNode` for structured
> classification/generation, `ToolUseNode` where *feeling the tool loop* is the point (Project B).

**Do you use pydantic-ai's `AgentNode` or raw Anthropic SDK for agent calls?**

| Approach | Pros | Cons |
|---|---|---|
| **pydantic-ai `AgentNode`** | Multi-provider, clean structured output, less boilerplate, production-ready | Hides the agentic loop (less educational), abstracts away tool use details |
| **Raw Anthropic SDK** | Full control, you learn the exact API mechanics, matches learning plan code examples | More boilerplate, Anthropic-only unless you abstract yourself |
| **Both** (recommended) | Educational `ToolUseNode` for projects where the loop is the lesson; `AgentNode` for projects where it's infrastructure | Slightly more surface area |

**Recommendation:** Use `AgentNode` for structured classification/generation tasks (FilterSpam, Summarizer, BlogWriter). Write a raw `ToolUseNode` for Project 2 (Research Agent) because *feeling the tool loop* is the lesson. After Project 2, you'll understand it; use `AgentNode` thereafter.

---

## Dependency Notes

These were all **added in Block D** and are now in `pyproject.toml` / `uv.lock`:
- `voyageai` — embeddings (`EmbeddingService`)
- `youtube-transcript-api` — transcripts (`TranscriptService`)
- `trafilatura` + `firecrawl-py` — article extraction, default + JS fallback (`ArticleExtractionService`)
- `tavily-python` — web search (`SearchService`)
- `pymupdf` — PDF parsing (`ChunkingService`)
- `anthropic` — direct SDK, now pinned explicitly (`ToolUseNode`; pydantic-ai also pulls it transitively)

The `supabase/postgres` Docker image includes pgvector, and the extension is now enabled by migration.
No Docker changes were needed for vector support — vector *columns* are added per project (see "Still to build").
