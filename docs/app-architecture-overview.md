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
- `ContentChunk` — **built** (`app/database/content_chunk.py`, Phase 1 Project D Task 1); `Vector(1024)` embedding column + `is_section_title` flag (drives 2x retrieval weight boost); `doc_id` indexed. Migration `c4d5e6f7a8b9` chains off `b3c4d5e6f7a8`.
- `ChatSession` — **built** (`app/database/chat_session.py`, Phase 1 Project D Task 1); `turns` + `topics_covered` JSON columns; `updated_at` with `onupdate`. Migration `c4d5e6f7a8b9` (same migration as `ContentChunk`).
- Still to add: `AgentEpisode` / `SemanticMemory` (Project G) — built with the project that stores them.

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
| Project A — Task 4 | `workflows/content_pipeline_workflow_nodes/summarizer_node.py`, `prompts/content_summarizer.j2` | `SummarizerNode(AgentNode)` with `SummaryOutput` (9-field Pydantic schema: `title`, `category`, `tl_dr`, `read_time_estimate`, `core_concepts`, `key_insights`, `questions_raised`, `connections_to_my_work`, `further_exploration`). Loads system prompt from `content_summarizer.j2` via `PromptManager`; uses `ModelProvider.CLAUDE_CODE_SDK` / `"sonnet"` (subscription-billing default; revert to `ANTHROPIC` / `claude-opus-4-8` per-node for metered API billing). Calls `run_agent_recorded()` for per-node telemetry. Reads upstream text from `FetchTranscriptNode` or `FetchArticleNode` defensively (empty string on fetch failure). `SummaryOutput` exported for `StorageNode` (Task 5) import. |
| Project A — Task 5 | `workflows/content_pipeline_workflow_nodes/storage_node.py`, `workflows/content_pipeline_workflow_nodes/digest_renderer.py` | `StorageNode(Node)`: embeds summary text at write time via `EmbeddingService().embed_text(...)` (title + tl_dr + core_concepts), persists a `LearningArtifact` row via `GenericRepository` + `db_session` factory (single deployment-agnostic seam, rule 7), writes a static HTML artifact page, and regenerates the category index. Output dir from `CONTENT_DIGEST_DIR` env. `digest_renderer` is a pure-function module: `render_artifact_page` writes `output_dir/<category>/<artifact_id>.html`; `regenerate_category_index` rewrites `output_dir/<category>/index.html`. No JS/search/tagging (D22). |
| Project A — Task 6 | `workflows/content_pipeline_workflow_nodes/blog_decision_router_node.py`, `blog_writer_node.py`, `self_critic_node.py`, `revise_node.py`; `prompts/blog_writer.j2`, `blog_self_critic.j2`, `blog_reviser.j2` | Blog branch: `BlogDecisionRouterNode(BaseRouter)` gates on `event.make_blog` — routes to `BlogWriterNode` when true, terminates (no fallback) when false. Linear chain: `BlogWriterNode → SelfCriticNode → ReviseNode` (no cycle; `ReviseNode` is terminal). All three are `AgentNode` subclasses using `ModelProvider.CLAUDE_CODE_SDK` / `"sonnet"` (subscription-billing default; revert to `ANTHROPIC` / `claude-opus-4-8` per-node for metered API billing) with `run_agent_recorded()` and `PromptManager`-loaded `.j2` prompts. `BlogWriterNode` reads `SummarizerNode` output; `SelfCriticNode` reads the draft; `ReviseNode` threads both draft and critique. |
| Project A — Task 7 | `workflows/content_pipeline_workflow.py`, `core/nodes/router.py` | Full DAG wired: `start=SourceRouterNode`; graph is `SourceRouterNode → (FetchTranscriptNode | FetchArticleNode) → SummarizerNode → StorageNode → BlogDecisionRouterNode → (BlogWriterNode → SelfCriticNode → ReviseNode)`. Both routers carry `is_router=True` in their `NodeConfig`; `ReviseNode` is terminal. Scaffold `initial_node.py` deleted. Also fixes a latent framework bug: `BaseRouter.process()` previously called `next_node.node_name` unconditionally, crashing when a router legitimately returns `None` (terminal branch); the guard `next_node.node_name if next_node else None` is now applied. Two end-to-end integration tests cover digest-only (`make_blog=False`, blog nodes stay PENDING, 1024-dim embedding persisted) and blog-enabled (`make_blog=True`, full linear blog branch runs) paths. |
| Project A — follow-up | `workflows/content_pipeline_workflow_nodes/translate_ptbr_node.py`, `prompts/translate_ptbr.j2`, `workflows/content_pipeline_workflow.py` | PT-BR translation added to the blog branch (reuse-spec port of the site's `claude-translator.ts`). `TranslatePtBrNode(AgentNode)` is now the terminal node — `ReviseNode → TranslatePtBrNode` — translating the finished EN post to Brazilian Portuguese for the brand's PT+EN cadence. `OutputType`: `translated_title`, `translated_body_markdown`, `confidence`, `cultural_notes`, `technical_terms` (nested `TranslatedTerm`). `ModelProvider.ANTHROPIC` / `claude-opus-4-8` (top-tier first run; Project H downgrade candidate). Gated by the existing `make_blog` branch, so digest-only runs skip it. |
| Project B — Task 1 | `workflows/research_agent_workflow.py`, `workflows/research_agent_workflow_nodes/company_research_node.py`, `schemas/research_agent_schema.py`, `prompts/research_agent_brief.j2` | Thin-cut research agent. `CompanyResearchNode(ToolUseNode)` drives a raw Anthropic tool-use loop with two tools: `web_search` (dispatched to `SearchService`/Tavily) and `submit_research_brief` (validates into `ResearchBriefOutput` and stores under `brief` key). System prompt loaded exclusively from `research_agent_brief.j2` via `PromptManager`. `ResearchBriefOutput` fields: `company_name`, `what_they_do`, `likely_time_sinks: list[str]` (min length 1), `automation_hypothesis`. Schema shaped toward `DiagnosticIntakeOutput` (deferred hardened version). Registered as `WorkflowRegistry.RESEARCH_AGENT`. No Celery, storage, or embedding in this cut — those arrive with the hardened Planner→Research→Critic→Revise→Storage chain. |
| Project C — Task 1 | `workflows/proposal_generator_workflow.py`, `workflows/proposal_generator_workflow_nodes/__init__.py`, `workflows/proposal_generator_workflow_nodes/initial_node.py`, `schemas/proposal_generator_schema.py` | Schema + scaffold for the proposal generator. `ProposalGeneratorEventSchema` fields: `company_name`, `industry`, `description`, `language` (default `"PT"`), `intake_notes`, `artifact_id` (auto-UUID), `timestamp` (UTC auto-set). Core output types: `ScoredCandidate` (with `validate_composite` enforcing the formula `(frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)` via `model_validator`), `WorkflowProfile`, and `AutomationRoadmap` (with `validate_candidates_sorted` for descending composite order and `validate_top_profiles_limit` capping `top_profiles` at 3). Registered as `WorkflowRegistry.PROPOSAL_GENERATOR`. Stub `InitialNode` placeholder in place; full node chain wired in Tasks 2–7. |
| Project C — Task 2 | `workflows/proposal_generator_workflow_nodes/company_research_node.py`, `prompts/proposal_research_brief.j2` | `ProposalCompanyResearchNode(CompanyResearchNode)` subclasses Project B's `CompanyResearchNode` without modifying that file. Overrides only `_build_initial_messages` to forward all four `ProposalGeneratorEventSchema` fields (`company_name`, `industry`, `description`, `intake_notes`) and load `proposal_research_brief.j2` via `PromptManager`. All tool definitions (`web_search`, `submit_research_brief`), the tool-use loop, and `ResearchBriefOutput` validation are inherited unchanged. `node_name` is `"ProposalCompanyResearchNode"` — distinct from the base class key, preventing `TaskContext` collision if both nodes appear in the same context. `proposal_research_brief.j2` is a purpose-built template (not a copy of `research_agent_brief.j2`) with industry-specific guidance and optional `intake_notes` injection. 17 hermetic unit tests in `tests/workflows/test_proposal_company_research_node.py` cover subclass identity, prompt template selection, field forwarding, loop termination, and `TaskContext` evidence writing. |
| Project C — Task 3 | `workflows/proposal_generator_workflow_nodes/opportunity_identifier_node.py`, `prompts/proposal_opportunity_identifier.j2` | `OpportunityIdentifierNode(AgentNode)` reads `company_name`, `industry`, `description`, and `intake_notes` from the event plus the structured research brief from `ProposalCompanyResearchNode` output in `TaskContext` (reads via `task_context.get_node_output("ProposalCompanyResearchNode")`); serializes all context into a JSON user prompt; runs the agent; validates the `ScoredCandidate` composite formula via `model_validator` at parse time (wrong composite raises `ValidationError` before `process()` is reached); writes output under `{"result": {"candidates": [...], "recommended": ...}}` to `TaskContext` under the node's name. `ModelProvider.CLAUDE_CODE_SDK` / `"sonnet"`. `proposal_opportunity_identifier.j2` embeds all five rubric axis anchor levels for `frequency`, `time_cost`, and `buildability` (1–5 each) and the binding composite formula — scoring is model-version-stable without Python changes. |
| Project C — Task 4 | `workflows/proposal_generator_workflow_nodes/proposal_writer_node.py`, `prompts/proposal_writer.j2` | `ProposalWriterNode(AgentNode)` — produces the full `AutomationRoadmap` deliverable from scored opportunities. Reads `OpportunityIdentifierNode` output via `get_node_output("OpportunityIdentifierNode")["result"]`; threads `event.language` (default `"PT"`) through the user-prompt JSON. `OutputType` fields mirror `AutomationRoadmap`: `situation_summary`, `candidates: list[ScoredCandidate]`, `top_profiles: list[WorkflowProfile]` (≤ 3), `recommended_workflow`, `engagement_scope`, `price_range_brl: tuple[int, int]`, and optional `body_pt`/`body_en`. `proposal_writer.j2` encodes the deliverable template's four required sections (Situation & Opportunity, Ranked Candidates, Top Workflow Profiles, Recommended First Engagement), the composite scoring rubric axis definitions and weights (`frequency × 0.35 + time_cost × 0.40 + buildability × 0.25`), and PT/EN language dispatch — no scoring logic in Python. `ModelProvider.CLAUDE_CODE_SDK` / `"sonnet"`. |
| Project C — Task 5 | `workflows/proposal_generator_workflow_nodes/proposal_review_node.py`, `proposal_review_router_node.py`, `proposal_revise_node.py`, `storage_node.py`; `prompts/proposal_review.j2`, `prompts/proposal_revise.j2` | Review + router + revise branch. `ProposalReviewNode(AgentNode)`: validates an `AutomationRoadmap` against five Diagnostic delivery criteria (client named ≥3×, one testable deliverable, 4–8 wk timeline, no vague language, investment matches complexity); emits a `CriterionResult` per criterion plus an overall `pass`/`revise` verdict. `ProposalReviewRouterNode(BaseRouter + RouterNode)`: routes `pass` → `StorageNode`, `revise` → `ProposalReviseNode`; handles both Pydantic-model and dict result shapes; returns `None` (no fallback) when result is missing. `ProposalReviseNode(AgentNode)`: reads the original roadmap from `ProposalWriterNode` and review feedback from `ProposalReviewNode`; produces a corrected roadmap JSON payload (`candidates_json`, `top_profiles_json`, `revision_notes`); flows linearly to `StorageNode` with no back-edge (DAG stays acyclic). `StorageNode` stub: minimal pass-through — Task 6 replaces the body with real `BrainDocument` + `EmbeddingService` + `GenericRepository` persistence. Both `.j2` prompts embed the five criteria verbatim; `proposal_revise.j2` includes price-range anchors by scope. 14 unit tests cover verdict emission, router branching (model and dict payloads), and revise-path context forwarding. |
| Project C — Task 6 | `workflows/proposal_generator_workflow_nodes/storage_node.py` | `StorageNode(Node)`: terminal persistence node for the proposal generator. Reads the final `AutomationRoadmap` from `ProposalReviseNode` output (revise branch, reconstructed via `_roadmap_from_revise_output`) or `ProposalWriterNode` output (pass branch, read from `["result"]` key). Builds an embed string from `roadmap.situation_summary` + candidate names, calls `EmbeddingService().embed_text(embed_text)`, and persists a `BrainDocument(doc_type="proposal", section="AutomationRoadmap", file_path=f"proposals/{artifact_id}/roadmap.json")` via `GenericRepository` + `db_session` factory (rule 7 — no deployment logic). Captures `artifact_id` from `task_context.event.artifact_id` before the session commits to prevent `DetachedInstanceError`. Output keys: `artifact_id`, `file_path`, `company_name`, `embedded`, `doc_type`. |
| Project C — Task 7 | `workflows/proposal_generator_workflow.py`, `tests/workflows/test_proposal_generator_workflow.py` | Full `ProposalGeneratorWorkflow` DAG wired: `start=ProposalCompanyResearchNode`; graph is `ProposalCompanyResearchNode → OpportunityIdentifierNode → ProposalWriterNode → ProposalReviewNode → ProposalReviewRouterNode → {StorageNode | ProposalReviseNode → StorageNode}`. `ProposalReviewRouterNode` carries `is_router=True`. Scaffold `initial_node.py` deleted. Key contract standardised: all agent nodes write output under `{"result": ...}` (matching framework convention). `StorageNode._roadmap_from_revise_output()` reconstructs `AutomationRoadmap` from `ProposalReviseNode.OutputType` JSON-string fields (`candidates_json`, `top_profiles_json`). `_serialize()` helper in `ProposalReviseNode` recursively calls `model_dump()` on nested Pydantic models for the revise prompt payload. Integration tests cover both pass and revise routes end-to-end (all agents mocked), DAG acyclicity, registry wiring, and `AutomationRoadmap` constraints (candidates sorted composite-desc, `top_profiles` ≤ 3, PT/EN language bodies). |
| Project D — Task 2 | `workflows/document_ingest_workflow.py`, `workflows/document_ingest_workflow_nodes/{parse_document_node,chunk_document_node,embed_chunks_node,store_chunks_node}.py`, `schemas/document_ingest_schema.py` | `DocumentIngestWorkflow` — linear DAG (no router): `ParseDocumentNode → ChunkDocumentNode → EmbedChunksNode → StoreChunksNode`. `DocumentIngestEventSchema` accepts `content` (raw text) or `content_b64` + `mime_type` (PDF/binary); `doc_id` auto-generated; `chunk_size=500`, `overlap=50` defaults. `ParseDocumentNode`: text pass-through or base64-decode + `fitz.open` PDF extraction; output `{"text": ...}`. `ChunkDocumentNode`: section-aware split on `^#{1,3}` headers via `re.MULTILINE`; emits a standalone `is_section_title=True` chunk per header, then token-window body chunks via `ChunkingService`; global `position` counter; output `{"chunks": [...]}`. `EmbedChunksNode`: single batched `EmbeddingService.embed_batch` call; zips vectors back with `zip(..., strict=True)`; output `{"chunks": [... + "embedding"]}`. `StoreChunksNode`: builds `ContentChunk` ORM objects; captures `doc_id` from event before persist (avoid `DetachedInstanceError`); `_persist` seam uses `GenericRepository` + `db_session` (rule 7); output `{"doc_id", "chunks_stored", "embedded": True}`. Registration in `workflow_registry.py` / `schema_registry.py` deferred to Task 5. 34 tests (22 node-level + 12 workflow/schema). |

The `WorkflowRegistry` enum scaling concern is resolved in practice: each project adds one entry
(`CONTENT_PIPELINE` is the first beyond `customer_care`; `RESEARCH_AGENT` is the second; `PROPOSAL_GENERATOR` is the third).

### ⚠️ STILL TO BUILD (per project, just-in-time)

Deliberately **not** built yet — these arrive with the project that needs them, not before:

- **Remaining vector-column models.** `LearningArtifact` (Phase 1 Project A), `BrainDocument` (brain-rag Layer 1), `ContentChunk` + `ChatSession` (Phase 1 Project D Task 1) now exist. Still to add:
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
