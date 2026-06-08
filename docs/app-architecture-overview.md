# App Architecture Overview
## Codebase Analysis for Agentic Engineering Projects

*Reviewed: May 2026 · Scope: `app/` directory*

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
Pydantic model that carries all state through the pipeline. Every node reads from it and writes to it via `task_context.update_node(node_name, **kwargs)`.

**Why it's excellent:** This is exactly the "state passing" pattern from Project 4. The `nodes` dict functions as a ledger of everything the pipeline has computed so far — any downstream node can read any upstream node's result. This is more flexible than explicit parameter threading.

**No changes needed.**

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

**Extension needed:** Add `ToolUseAgentNode` subclass for tool-calling agents (Project 2+).

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

**What's missing for the learning plan:**
- pgvector support (the `supabase/postgres:15.8.1` image *already has pgvector installed* — you just need to enable the extension and add vector columns)
- New models: `ContentChunk`, `LearningArtifact`, `AgentEpisode`, `SemanticMemory`
- Embedding service (Voyage AI)

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

### ⚠️ THINGS THAT NEED TO BE BUILT

These are gaps between the current codebase and the learning plan's requirements:

#### 1. pgvector + Embeddings Layer
The Supabase postgres image already ships with pgvector. You need:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
Then:
- New Alembic migration with `vector` column types
- `services/embedding_service.py` — Voyage AI client wrapper
- New models: `ContentChunk(id, doc_id, position, content, embedding vector(1024))`

#### 2. `ToolUseNode` (raw Anthropic agentic loop)
The pydantic-ai `AgentNode` handles tool calls internally. For Projects 2–3 where understanding the tool loop is the educational goal, write a `ToolUseNode` that exposes:
```python
class ToolUseNode(Node):
    tools: list[dict]  # Anthropic tool definitions
    
    def run_with_tools(self, messages: list, system: str) -> str:
        client = anthropic.Anthropic()
        while True:
            response = client.messages.create(...)
            if response.stop_reason == "end_turn":
                return ...
            # process tool calls, append results, continue
```

#### 3. New Database Models
Per the learning plan's storage requirements:
- `LearningArtifact` — source_url, type, title, content, embedding
- `ContentChunk` — doc_id, position, content, embedding  
- `AgentEpisode` — session_id, summary, outcome, tags, embedding
- `SemanticMemory` — fact, confidence, evidence, created_at

#### 4. YouTube Transcript Service
```python
# services/transcript_service.py
# Wraps youtube-transcript-api, handles chunking for long videos
```

#### 5. Web Search Service (Tavily)
```python
# services/search_service.py
# Tavily client wrapper, returns clean dicts for use in ToolUseNode
```

#### 6. Long-Content Chunking Service
```python
# services/chunking_service.py
# Splits transcripts/PDFs into overlapping token-sized chunks
```

#### 7. Multi-Workflow Registry
The current `WorkflowRegistry` enum has one entry. Each project adds a new entry. This scales fine — just extend the enum.

---

## The One Design Decision to Make Now

**Do you use pydantic-ai's `AgentNode` or raw Anthropic SDK for agent calls?**

| Approach | Pros | Cons |
|---|---|---|
| **pydantic-ai `AgentNode`** | Multi-provider, clean structured output, less boilerplate, production-ready | Hides the agentic loop (less educational), abstracts away tool use details |
| **Raw Anthropic SDK** | Full control, you learn the exact API mechanics, matches learning plan code examples | More boilerplate, Anthropic-only unless you abstract yourself |
| **Both** (recommended) | Educational `ToolUseNode` for projects where the loop is the lesson; `AgentNode` for projects where it's infrastructure | Slightly more surface area |

**Recommendation:** Use `AgentNode` for structured classification/generation tasks (FilterSpam, Summarizer, BlogWriter). Write a raw `ToolUseNode` for Project 2 (Research Agent) because *feeling the tool loop* is the lesson. After Project 2, you'll understand it; use `AgentNode` thereafter.

---

## Dependency Notes

Current `pyproject.toml` has everything needed except:
- `voyageai` — for embeddings
- `youtube-transcript-api` — for Project 0
- `tavily-python` — for Project 2 web search
- `pymupdf` — for Project 1 PDF ingestion
- `anthropic` — direct SDK (pydantic-ai pulls it as a transitive dep, but good to pin explicitly)

The `supabase/postgres` Docker image includes pgvector. No Docker changes needed for vector support — just a migration.
