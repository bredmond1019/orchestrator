# Agentic Engineering Projects & Learning Plan
## Brandon's Path to Expert Agentic & Harness Engineer

*Updated: May 2026 · Status: Active*
*Incorporates: existing Python orchestration framework, codebase analysis, test plan (Option A)*

---

## How to Use This Document

This is your single technical reference. It covers:
- The **Python Agentic Orchestration System** you already built (your infrastructure foundation)
- A **Phase 0 codebase orientation** to do before any project
- **7 projects (A–G)** building progressively harder agentic patterns, sequenced by *sellable competence*, plus **Project H** (model evaluation) and a **Rust CLI** parallel track
- **Three internal-tool / product ideas** that ride on top of these projects

### The organizing principle

Projects are ordered by one question: **"Does this teach me something I'll sell — or that makes me demonstrably expert?"** Not by any single product's dependency graph. The old plan was sequenced to assemble one specific app (a Socratic tutor) at the end. That app now lives in a separate, archived document and is not referenced here. This plan exists for one thing: making you an expert agentic/harness engineer whose work is good enough to sell as a service *and* to land a senior role.

### You are not starting from zero

Before the project library: you have already shipped, solo and in production, an **Internal Support Dashboard** (100+ daily cross-functional users, 24–48hr support wait-time reduction, still in daily use) and a **Helpscout Support Automation** (RAG + vector + semantic search in production). You contributed heavily to a production healthcare AI tool (**AI Scribe**) through and past launch. Several projects below are not new competencies — they are clean, defensible, owned-end-to-end rebuilds of patterns you've already proven. Project D especially. Treat those as portfolio refreshes that let you say "I've shipped this in production," not as first attempts.

### The rules

1. **Ship each project.** It has to work end-to-end and be demonstrable. Incomplete projects don't teach patterns.
2. **Every project ships with its own tests.** The core engine is locked down in Phase 0 (see Test Plan, Option A). From Project A onward, a new workflow means new tests — no exceptions. This is core agentic-engineering practice: you and your agents must be able to validate that the system works.
3. **Build the thinnest thing that teaches the pattern.** Then expand only when a real need (a prospect, a client, a downstream project) forces it. Restraint is what keeps this a path to expertise instead of an infinite build.
4. **Learning content is AI/agentic/harness engineering** — the TAC course, orchestration and agent talks, harness/agentic-coding material. You feed this through Project A and absorb it as you build. (No physics; that's personal-time material in a different document.)

---

---

# PART 1: YOUR EXISTING INFRASTRUCTURE
## The Python Agentic Orchestration System

*Before touching any project, understand what you already have. This section is your codebase reference. It reflects the actual code as reviewed, not an idealized version.*

---

## What You Already Built

**Production-ready event-driven AI pipeline infrastructure.** Not a demo, not a starter kit. The core abstractions (Workflow, Node, TaskContext, AgentNode) are clean, composable, and apply to every project here. The Customer Care workflow shipped with it is a **reference implementation only** — you read it to learn the patterns, you do not extend it, and (per Option A) you do not test it.

**Mental model:** this system is the scaffold. Every project is a new workflow attached to it.

---

## System Architecture

```
+---------------------------------------------------------------------+
|                         INFRASTRUCTURE                               |
|                                                                      |
|  FastAPI --> Endpoint --> GenericRepository --> PostgreSQL           |
|      |                                                               |
|      +--> Celery Task Queue --> Worker --> WorkflowRegistry          |
|                                                     |                |
|                            Redis (broker/backend) <-+                |
+---------------------------------------------------------------------+
                                  |
                                  v
+---------------------------------------------------------------------+
|                         CORE ENGINE                                  |
|                                                                      |
|  Workflow (DAG orchestrator)                                         |
|    +-- WorkflowSchema (node graph definition)                        |
|    +-- WorkflowValidator (DAG integrity: DFS cycles, BFS reach)      |
|    +-- run() -> TaskContext                                          |
|                                                                      |
|  Node (abstract base: Chain of Responsibility)                       |
|    +-- AgentNode (pydantic-ai wrapper: multi-provider AI calls)      |
|    +-- ParallelNode (ThreadPoolExecutor for concurrent nodes)        |
|    +-- BaseRouter + RouterNode (conditional branching)               |
|                                                                      |
|  TaskContext (Pydantic model -- shared state across all nodes)       |
|    +-- event: Any (the trigger event, parsed to schema)              |
|    +-- nodes: Dict[str, Any] (each node's output, keyed by name)    |
|    +-- metadata: Dict (workflow-level config, node registry)        |
+---------------------------------------------------------------------+
                                  |
                                  v
+---------------------------------------------------------------------+
|                         SUPPORT SERVICES                             |
|                                                                      |
|  PromptManager (Jinja2 + frontmatter -- .j2 template files)         |
|  GenericRepository (SQLAlchemy CRUD: create/get/update/delete)       |
|  DatabaseUtils (connection string from env vars)                     |
|  WorkflowInitCommand (`createworkflow` CLI scaffolding tool)         |
+---------------------------------------------------------------------+
```

---

## Component Reference

### `core/workflow.py` — The Orchestrator [KEEP, extend aggressively]
Reads a `WorkflowSchema` (DAG), walks it node by node, passes `TaskContext` through, handles routing, validates the graph before running. The `while current_node_class:` loop in `run()` is the agentic pipeline loop — already built and validated.

**Key limitation:** the validator enforces strict DAGs — no cycles. Self-correction loops (critic → revise → critic) cannot be a cycle. **Solution:** implement self-correction as a linear chain (`CriticNode → ReviseNode`) or as a sub-workflow that runs as a unit inside a parent node, or chained `Workflow.run()` calls in a parent node.

### `core/task.py` — TaskContext [NO CHANGES NEEDED]
Pydantic model carrying all state. Nodes read/write via `task_context.update_node(node_name, **kwargs)`. The `nodes` dict is a ledger; any downstream node reads any upstream result by key. **Convention:** always key by node class name — `task_context.nodes["SummarizerNode"]["summary"]`.

### `core/nodes/base.py` — Node ABC [NO CHANGES NEEDED]
One abstract method: `process(task_context) -> task_context`. Everything is a Node.

### `core/nodes/agent.py` — AgentNode [USE FOR MOST PROJECTS]
Wraps pydantic-ai's `Agent`. **Already supports multiple providers** — OpenAI, Azure, Anthropic, Gemini, Ollama, AWS Bedrock — out of the box. Typed `OutputType` (structured output) and `DepsType` (context injection).

- **Switch the default provider** before building. Examples ship with `ModelProvider.OPENAI`; use `ModelProvider.ANTHROPIC`, `model_name="claude-opus-4-7"`.
- **Local models are a one-line change** (`ModelProvider.OLLAMA`) thanks to pydantic-ai. Useful later for cheap/frequent narrow tasks; don't optimize prematurely.

| Use | When |
|---|---|
| `AgentNode` (pydantic-ai) | Structured output, production pipelines, agent-call-as-infrastructure |
| Raw `anthropic.Anthropic()` via `ToolUseNode` | Project B only — where learning the tool loop is the goal |

Rule: write the raw `while stop_reason == "tool_use"` loop exactly **once** (Project B). After that you understand it; use `AgentNode` forever after.

### `core/nodes/parallel.py` — ParallelNode [USE, fix-on-first-use]
Runs nodes concurrently via `ThreadPoolExecutor`.

**Known gap (from code review):** parallel results aren't merged back into the main context — the calling node currently discards the returned list, and parallel nodes mutate the shared `task_context` directly (works, but not thread-clean). **Fix when you first genuinely use parallelism (Project E):** have each parallel node write to a uniquely keyed slot and merge after.

### `core/nodes/router.py` — BaseRouter / RouterNode [NO CHANGES NEEDED]
Declarative conditional routing. List of `RouterNode` instances; first match wins; `fallback` on no-match. Write new subclasses per branch.

### `core/schema.py` — WorkflowSchema / NodeConfig [NO CHANGES NEEDED]
Declarative graph definition. Forces graph-thinking before agent code. `createworkflow` scaffolds it.

### `core/validate.py` — WorkflowValidator [NO CHANGES NEEDED]
DFS cycle detection + BFS reachability, on every `Workflow.__init__()`.

### `services/prompt_loader.py` — PromptManager [CRITICAL HABIT]
Jinja2 + YAML frontmatter `.j2` files. **Never hardcode a system prompt in Python. Always a `.j2` file.** Prompts are assets; iterate the file, not the code.

### `worker/` — Celery + Redis [USE FOR ALL LONG-RUNNING PIPELINES]
Accept-and-delegate: FastAPI accepts, persists, queues; worker runs the workflow. Each new workflow adds a `@celery_app.task`. No structural changes.

### `database/` — SQLAlchemy + PostgreSQL [EXTEND WITH NEW MODELS]
`DatabaseUtils`, `db_session`, `GenericRepository` all reusable. **Missing, build as projects need them:** pgvector (one migration; extension already in the Supabase image), then `ContentChunk` (Project D), `LearningArtifact` (Project A), `AgentEpisode` + `SemanticMemory` (Project G).

### Customer Care workflow — REFERENCE ONLY [DO NOT EXTEND, DO NOT TEST]
A worked example of how the abstractions compose. Read `AnalyzeTicketNode` (parallel), `TicketRouterNode` (routing), `GenerateResponseNode` (AgentNode + PromptManager) when confused about wiring a pattern. Build new workflows alongside it, never on top of it.

---

## Infrastructure Gaps to Close First (Phase 0, Foundation Block D)

Build once, reuse everywhere:

1. **pgvector migration** — `CREATE EXTENSION IF NOT EXISTS vector;` then vector columns via Alembic.
2. **EmbeddingService (Voyage AI)** — `voyage-2`, 1024 dims. (Anthropic has no standalone embedding endpoint; Voyage is built by ex-Anthropic researchers, works well with Claude, generous free tier.)
3. **TranscriptService** — wraps youtube-transcript-api, handles long-video chunking.
4. **SearchService (Tavily)** — clean structured results for the tool loop.
5. **ChunkingService** — overlapping token-sized chunks for transcripts/PDFs.
6. **ToolUseNode (raw Anthropic)** — for Project B; manages the tool loop manually with a `max_iterations` guard.

**New dependencies:** `voyageai`, `youtube-transcript-api`, `tavily-python`, `pymupdf`, and pin `anthropic` explicitly. (Test tooling lives in the Test Plan.)

---

---

# PART 2: PHASE 0 — CODEBASE ORIENTATION
## Do This Before Any Project. Non-Negotiable.

**Goal:** own the framework mentally, not just use it. Engineers who skip this learn *how* to use the framework but not *why* it's built that way — and the why is exactly what lets you adapt it when a client's problem doesn't fit the existing patterns.

### Step 1 — Read the core engine line by line
`core/workflow.py` (how `run()` walks the graph; why validation is in `__init__` not `run()`), `core/task.py` (what `TaskContext` carries; the `update_node` convention; why it's passed by reference), `core/nodes/agent.py` (how `AgentConfig` maps to a pydantic-ai `Agent`; where the provider switch happens). Then `parallel.py`, `router.py`, `schema.py`, `validate.py`, `prompt_loader.py`.

### Step 2 — Draw the architecture from memory
Close all files. Draw the three tiers (Infrastructure / Core Engine / Support Services) with every component and connection on your whiteboard. Can't? Read again.

### Step 3 — Run the Customer Care workflow end-to-end
`docker compose up -d`, POST an event, watch the Celery worker, inspect the `task_context` JSON in Postgres. Trace every call — which node ran, what it wrote, how the router decided.

### Step 4 — Answer these five without looking
1. A workflow has 5 nodes. Node 3 needs data Node 1 produced. How does it access it?
2. Two nodes run in parallel then merge. Which node type, and what's the thread-safety consideration?
3. Branch: if content is "spam" go to A, else B. How?
4. Iterate a system prompt without restarting the server — how does PromptManager enable this?
5. A request hits your API. Walk every step until the result is stored in the DB.

If you can answer all five and draw the diagram, Phase 0 orientation is done. (Test infrastructure + core hardening happen alongside this — see Test Plan.)

---

---

# PART 3: THE PROJECT LIBRARY (A–G)

*Sequenced by sellable competence. Every project ships with tests.*

---

## Project A — Content Pipeline (YouTube → Summary → Blog)
### Fastest full rep. Also your content-marketing engine.

**Pattern:** linear pipeline + self-correction loop. **Reuse downstream:** `LearningArtifact` model, the `SelfCriticNode → ReviseNode` pattern, your voice prompt.

### Why first
Fastest way to exercise the whole `Workflow → Node → TaskContext → AgentNode → PromptManager` chain end-to-end, and it produces something you need anyway: a pipeline that turns AI/agentic/harness-engineering videos into structured summaries and blog drafts, building a searchable corpus while you learn. The self-critic loop is the real lesson; the wiring is fast.

### End result
POST a URL to `/events/content`. Celery runs:
1. `FetchTranscriptNode` — fetch + clean transcript
2. `SummarizerNode` — structured JSON summary (AgentNode, structured output)
3. `BlogWriterNode` — draft in your voice
4. `SelfCriticNode` — critique the draft
5. `ReviseNode` — final revised draft
6. `StorageNode` — markdown to disk + `LearningArtifact` row **with embedding at write time**

### Build notes
- Scaffold with `createworkflow`.
- `SummaryOutput` schema: title, core_concepts, key_insights, questions_raised, connections_to_my_work, further_exploration.
- **Summarizer prompt focus areas:** agentic engineering patterns & orchestration, harness engineering & agentic coding workflows, AI system architecture, building an AI practice in São Paulo.
- **Voice prompt is a long-term asset.** Feed `blog_writer.j2` 2–3 pieces of writing you admire; have it extract the patterns. Reused in Project C and all external content.
- **Self-critic loop stays linear** in the DAG (validator forbids cycles). Critic asks specific questions: does the hook make a concrete observation? does each section make exactly one point? any vague/hand-wavy technical claim?
- **Store embeddings at write time** in `StorageNode` — deferring this hurts in Project F.
- Transcript gaps happen; add error handling (Whisper local as a fallback for missing captions, optional).

### Tests ship with it
New workflow → tests for each node (mocked agents), the storage path, and one integration test of the full chain with agents mocked.

---

## Project B — Research Agent (thin first, then hardened)
### The tool loop, written by hand. Once. Your prospecting tool.

**Pattern:** raw agentic tool loop + self-correction. **Reuse downstream:** the tool loop feeds Project C's `CompanyResearchNode`; this is also the seed of the #3 intelligence-synthesis product.

### Why this is the most sellable competence
"Research a company, find the automation opportunity" *is* the consulting motion. Building it makes you able to walk into an unfamiliar business and see the work. It's also literally your prospecting tool.

### Thin cut first (build this, stop here until a prospect needs more)
A single `ToolUseNode` (raw `anthropic.Anthropic()` — write the `while stop_reason == "tool_use"` loop yourself; the `max_iterations` guard is not optional) plus Tavily. Input a company name; output a structured brief: what they do, where they likely bleed time, one automation hypothesis. **No Celery, no critic, no storage. ~50 lines.** You run it before a real conversation so you walk in already understanding their world.

### Hardened version (only when a real prospect makes you want it)
1. `PlannerNode` (AgentNode) — research plan
2. `ResearchNode` (ToolUseNode) — `web_search` + `arxiv_search`/source tools
3. `CriticNode` (AgentNode) — gaps, unsupported claims
4. `ReviseNode` (AgentNode)
5. `StorageNode` — `LearningArtifact` + embedding

### Build notes
- **This is the one project where you bypass `AgentNode`.** Feel the loop: the cycle, tool-result injection, termination. After this, you've earned the abstraction.
- Tavily over raw search APIs — built for agents, far better signal-to-noise.

### Tests ship with it
The tool loop with a mocked client (assert it injects results and terminates on `end_turn` and on `max_iterations`), plus node tests for the hardened version when you build it.

---

## Project C — Client Proposal Generator
### Your first real business tool. The competence-checkpoint skill, trained.

**Pattern:** research → structured output → review/revise with routing. **Business value: high** — use it on real prospects.

### Why it matters
The `OpportunityIdentifierNode` prompt *is* the skill of seeing automation in a business you don't know — which is exactly the "three workflows in 30 minutes" checkpoint. Building this trains the thing that makes you ready to sell *or* interview.

Note also that the structured-output-against-a-schema work here (`Opportunity`/`OpportunitiesOutput`) is the *same skill* you exercised in production on AI Scribe, auto-filling customizable forms and charting notes from transcript analysis. You've done this at production scale; this is you owning the pattern end-to-end on your own infrastructure.

### End result
Input: company name, industry, brief description.
1. `CompanyResearchNode` (ToolUseNode from Project B — first real reuse)
2. `OpportunityIdentifierNode` (AgentNode) — 3 opportunities with scores
3. `OpportunityRouterNode` (RouterNode) — picks the highest-value one
4. `ProposalWriterNode` (AgentNode) — scoped proposal in **PT and EN**
5. `ProposalReviewNode` (AgentNode) — validates against explicit criteria
6. `ReviseNode` — addresses feedback if needed
7. `StorageNode`

### Build notes
- `Opportunity` schema: name, problem_statement, proposed_solution, estimated_value (e.g. "R$15K–25K/yr in time saved"), build_complexity (low/med/high), fit_score (0–1). `OpportunitiesOutput`: opportunities, recommended, rationale.
- **Review criteria** (this is the review-and-revise pattern): names client ≥3×? exactly one specific testable deliverable? realistic timeline (4–8 wks first project)? avoids vague language ("AI-powered solution", "leverage synergies")? investment matches complexity? Each PASS/FAIL with a line reference; router sends to `ReviseNode` on "revise", to `StorageNode` on "pass".
- **One recommendation, not three.** The router decides before the writer sees it.
- The proposal prompt is the real work; the framework just orchestrates.
- Run it on the two warm leads as practice (see Master Plan → Prospects). Output is ~80% ready; that's valuable, don't wait for perfection.

### Tests ship with it
Node tests (mocked agents), the router's pass/revise branching, and the structured-output schema validation.

---

## Project D — Document Q&A + Session Memory (RAG)
### The most common SMB request. Framed for business documents.

**Pattern:** full RAG + session memory. **Reuse downstream:** `RetrieveChunksNode` (verbatim later), `ContentChunk` + `ChatSession` models. Seed of the #1 client-memory product.

### Why it matters
RAG over a client's own documents — SOPs, product catalogs, internal wikis, policy docs — is the single most common SMB automation ask. Build it now, framed for *business documents*, not textbooks.

**You have already shipped this in production.** Your Helpscout Support Automation used RAG, vector search, and semantic search to read a ticket, search help docs and the customer database, and summarize for the rep — architected by you, solo. So Project D is **reinforcement and a clean portfolio refresh of a proven competence, not first contact with the pattern.** When a São Paulo SMB asks for document-aware automation, you're describing something you've delivered, not something you hope to. Write it up that way.

### End result
**Ingestion** (`/events/ingest_document`): `ParseDocumentNode → ChunkDocumentNode → EmbedChunksNode → StoreChunksNode`.
**Query** (`/events/query`): `EmbedQuestionNode → RetrieveChunksNode → AssembleContextNode → AnswerNode → UpdateSessionMemoryNode`.

### Build notes
- Models: `ContentChunk(doc_id, position, section_title, content, embedding)`, `ChatSession(doc_id, turns JSONB, topics_covered, timestamps)`.
- **Build `RetrieveChunksNode` carefully** — cosine-distance top-k; reused verbatim downstream.
- Chunk size: 500 tokens / 50 overlap starting point; tune on a real business doc.
- **The distinction to internalize:** RAG retrieves from the document; session memory tracks the conversation. Both are context, assembled together in `AssembleContextNode`. This is the foundation of every stateful agent — and it's the conceptual groundwork for Project G.
- `TaskContext` lives for one request; session memory must persist to `ChatSession` and load at query start.

### Tests ship with it
Retrieval correctness (mock embeddings, assert ordering), the RAG-vs-session-memory assembly, ingestion chunking boundaries.

### Competence checkpoint
After Project D, test yourself honestly against "three automatable workflows in 30 minutes." If yes → ready for a paid diagnostic. If no → name exactly what's missing, and be suspicious if the answer is "one more project."

---

## Project E — Specialization Refactor
### Architectural judgment. The before/after is the whole point.

**Pattern:** specialized nodes + parallelism. **Kept separate from Project A on purpose.**

### Why it's separate
If you wrote Project A in its final specialized form, you'd skip the lesson. You build the naive single-pass pipeline, feel its limits on real output, then refactor and watch quality change. That experience is what lets you *explain to a client or interviewer* why specialization matters — expert judgment, not a copied pattern.

### The refactor
**Before:** `Fetch → Summarizer → BlogWriter → SelfCritic → Revise → Storage`
**After:** `Fetch → [ConceptExtractorNode ‖ StructureAnalystNode] → BlogDraftNode → VoiceMatchNode → SelfCritic → Revise → Storage`

`ConceptExtractor` and `StructureAnalyst` read the transcript independently → `ParallelNode`.

### Build notes
- **Fix the `ParallelNode` merge gap here** (see Part 1): each parallel node writes a uniquely keyed slot; merge after. This is the first time you genuinely need parallelism, so it's the right place to fix it.
- Run the same video through old and new pipelines; compare outputs. The quality delta is the lesson.
- Write the comparison (what broke when nodes got narrower, what improved, where the right level of specialization sits) — strong LinkedIn material.

### Tests ship with it
The parallel merge (assert both slots present and correctly combined), plus the new specialized nodes.

---

## Project F — Semantic Search Over Your Corpus
### Reuse + the tool you'll actually use to learn.

**Pattern:** semantic retrieval at corpus scale. **Mostly Project D components.** Seed of the #1 client-memory product.

### End result
`GET /knowledge/search?q=...` returns top-3 relevant `LearningArtifact`s with excerpts and source URLs; optional synthesis (a single `AgentNode` consolidating top-k into one answer).

### Build notes
- The payoff for storing embeddings at write time since Project A — the whole corpus is searchable, and grows every time you run Project A.
- Prove semantic (not keyword) retrieval to yourself: search "agents communicating" and confirm you get results tagged "multi-agent orchestration."
- **Practical use:** before each new study session, query "what have I learned about context engineering / harnesses / orchestration?" This is the tool you'll genuinely use.

### Tests ship with it
Ranking/ordering with mocked embeddings; the synthesis node with a mocked agent.

---

## Project G — Agent Memory System (Episodic → Semantic)
### The hardest. The most differentiating. The centerpiece. Budget a full block.

**Pattern:** episodic→semantic consolidation, confidence decay, contradiction handling. **Reuse downstream:** `MemoryLoaderNode` (verbatim), the whole module. Underpins the #1 (client/account memory) and #5 (expert second brain) product ideas.

### Why this is the capstone now
Durable agent memory that gets smarter across sessions, decays confidence over time, and handles contradictions gracefully is frontier-adjacent and the thing most teams get wrong. Given that the goal is *expertise*, this is the most valuable thing in the plan. It's reusable infrastructure that slots into any client project and is the foundation of two of your three product ideas.

### End result
A memory module attachable to any workflow:
1. **Write episode** (after each turn): "User asked about X. I answered with Y. They understood Z but struggled with W."
2. **Consolidation job** (Celery, session-end + nightly): reads recent episodes, extracts durable facts.
3. **Memory loader** (session start): loads top-k relevant facts into context.

### Models
- `AgentEpisode(session_id, summary ~40 tokens, outcome [understood|partial|confused|bookmarked], tags, embedding, occurred_at)`
- `SemanticMemory(fact, confidence 0–1, evidence_episode_ids, decay_factor default 0.95/wk, timestamps, embedding)`

### The consolidation prompt — the real work
Extract 3–5 durable, **specific and falsifiable** facts. Assign confidence by evidence strength. **If a fact contradicts an existing one, lower the old fact's confidence rather than overwriting — learning is non-monotonic.** Focus on misconceptions, strong intuitions, preferred explanation styles, mastered concepts, persistent confusions. Return valid JSON only.

### Build notes
- **Confidence decay is not optional:** `new = confidence * decay_factor ** weeks_elapsed`, run in `UpsertMemoryNode`.
- **Contradictions expected:** lower confidence on the contradicted fact, create a new one. Never overwrite.
- **Standalone importable module** — `MemoryLoaderNode`, `EpisodeWriteService`, `ConsolidationWorkflow`, no coupling to any one workflow. This is infrastructure.
- Local-model note: the short episode-write summary is a fine local-model candidate later; the consolidation prompt must stay on Claude — weak output here silently degrades everything downstream.

### Tests ship with it — and they matter most here
Consolidation output schema validity; the decay function (freeze time, assert decay); contradiction handling (assert old-fact confidence drops, new fact created, no overwrite); `MemoryLoaderNode` retrieval ordering. Bad memory output is the kind of silent failure that erodes trust in every system built on it — test it hard.

---

## Project H — Model Evaluation & Routing Harness
### Knowing exactly which nodes can run local without degrading output — and proving it.

**Pattern:** offline evaluation; empirical model routing. **Reuse downstream:** the routing decisions bake into every node's `model_provider`; the rigor transfers to evaluating any prompt. **Sellable as:** "I cut your AI spend substantially with measured quality retention."

*Sequencing note: best placed after Project D (you'll have summarizer, proposal, and RAG nodes — a good spread of structured and open-ended tasks to evaluate), and it pairs naturally with Project G (the same "measure quality rigorously" muscle that the consolidation prompt demands). Lettered H for now; **when** it actually gets built may shift as priorities change — treat the position as a recommendation, not a fixed slot.*

### The thesis it proves
Decompose a workflow into small enough nodes and local models can handle most of them, with paid frontier models reserved for what genuinely needs frontier reasoning. Your node-based architecture is already the precondition that makes this viable — each node is one narrow, bounded transformation, which is squarely in a good local model's range. This project turns that thesis from a hunch into measured, defensible fact.

### The expert distinction (what separates this from a toy)
The value is **not** "run everything local." It's the *routing judgment* — knowing, with data, which nodes are safe local and which silently degrade off-frontier. The naive version ("I made it run on Llama") is a toy. The rigorous version ("I built a system that empirically routes each node to the cheapest model meeting a quality bar, here's the data") is a consulting offering and a differentiator.

### Critical design principle: offline eval, not runtime router
This runs **occasionally and deliberately**, to *produce* routing decisions ("node X is safe on local-70B"). Those decisions then bake into the node's `model_provider` config at design time. You are **not** building per-request runtime model selection — that adds latency and complexity for marginal benefit when good static per-node decisions capture most of the value. Keep eval and runtime separate.

### What it does
For a given node, run a set of representative inputs (30–50 real examples) through several models — a frontier reference (Claude Opus), a mid local (e.g. Llama 70B), a small local (e.g. 7–8B) — score each output, and produce a per-node table: how much reference quality each model retains, at what cost. The routing decision then writes itself.

### Scoring strategy — by node type (this is where the expertise lives)
- **Deterministic / structural** (structured-output nodes like `OpportunityIdentifierNode`, the consolidation node): valid schema? required fields present? values in range? Cheap, objective; often catches where small models fail first (malformed output).
- **Reference-based** (extraction tasks): compare extracted facts against a hand-labeled set.
- **LLM-as-judge** (open-ended prose: summarizer, blog writer): a frontier model scores candidates against a rubric. **Handle judge bias explicitly** — score *blind* (judge doesn't know which model produced which output), randomize order, use specific criteria not vague "which is better." Judges skew toward longer outputs, their own family's style, and position. That you correct for this is itself a senior signal worth writing about.

### How it fits your system (it's elegant)
It rides on what you have. A node already declares its model via `AgentConfig`; swapping `ModelProvider` is nearly free. The harness is a runner that takes a node + inputs + a list of model configs, executes the node under each, collects outputs, passes them to a scorer, and persists results to a table. It is itself a workflow in your own framework — you're using your orchestration system to evaluate your orchestration system.

### Tests ship with it
The scoring functions (deterministic scorers against known-good/known-bad outputs); the blind/randomized judge harness (assert it strips model identity and randomizes order); results persistence.

### The future Rust attach point (kept in the back of the mind, not built now)
If, much later, you lean so heavily on local models that the *serving runtime* (model loading, batching, token streaming, memory management) becomes a measured bottleneck that off-the-shelf serving like Ollama can't clear, that runtime layer is genuine Rust territory. **You do not build this now** — off-the-shelf serving is the runtime, you talk to it over an API, and the moment to write Rust here announces itself with data. Noted here only so the door stays open.

---

## Parallel Track — Rust Infrastructure CLI
### The control plane for *your* infrastructure. Where Rust stays warm through daily use.

*Not a numbered project — a parallel track you develop alongside the harness work whenever you want a Rust session. No fixed slot.*

### Reframed (June 2026): what Claude Code now does for you, so you don't build it
On May 28, 2026 Anthropic shipped **Agent View** (`claude agents` — a terminal dashboard across background Claude Code sessions, run by a per-user supervisor process so work survives terminal/shell closure), **Dynamic Workflows** (Claude Code writes its own orchestration scripts and spins up many parallel subagents within a session), and the older **subagents** (`/agents` — reusable YAML configs in `.claude/agents/`). **This commoditizes the "trigger and watch Claude Code coding runs" job.** Do not rebuild it in Rust. Use the built-ins (`claude agents`, `claude --bg "<task>"`, Claude Code Web for sessions that survive machine sleep) for the *coding-agent* case.

What Anthropic did **not** build — and structurally will not, because it isn't their product — is a control plane for *your* infrastructure: your Python orchestration system, your Celery workflows, your Postgres tables, your **Project H eval runs**, and your **deployed client appliances running local models**. That is what this CLI is for. The line the old version drew was right; the emphasis was wrong.

### What it is, and how it differs from Claude Code
**Claude Code is the agent that does the work, and now also manages its own coding sessions** (Agent View / Dynamic Workflows / subagents). **This CLI is the operational interface to *your specific infrastructure* and your cost-optimization layer** — not a wrapper around Claude Code. They're stacked, not competing: let Claude Code orchestrate Claude Code; this CLI commands and observes *your* systems.

### What it does — re-aimed
- **(Demoted to thin convenience) Remote coding triggers.** The only seam the built-ins don't cover is *phone → your own Mac Mini, surviving sleep*. Agent View is local and sessions don't survive shutdown (you run `claude respawn --all` on wake); Claude Code Web survives but runs in Anthropic's cloud, not on your hardware. Keep a thin remote-trigger command **only if you still want phone-to-Mini-on-your-hardware after trying the built-ins.** Don't lead with it.
- **(Now the spine) Operate your workflows.** Trigger a content-pipeline run on a URL, generate a proposal for a prospect, **run the Project H eval harness on a node**, inspect the `LearningArtifact` table. First-class commands over ad-hoc `curl`/DB queries. Untouched by anything Anthropic ships.
- **(Now the spine) Observe your infrastructure and the cost layer.** Status of what's running on the Mini, recent runs, failures, logs — and, wired to Project H, **per-node model routing decisions and measured cost/quality**: which nodes are safe on local-9B/local-70B, what a given workflow run cost, what local-vs-paid saved. This is the surface that becomes a *client-facing appliance* (see below).
- **(Product seed) The single-binary client appliance.** The same binary a non-technical client runs on their own hardware to operate and observe their automation — and to see, in plain numbers, what it cost and what local models saved them. This is the delivery vehicle for the cost-optimization thesis, not a dev-only tool.

### Why Rust is an unambiguous fit here (unlike orchestration, and unlike re-wrapping Claude Code)
A CLI you invoke dozens of times a day wants instant startup and single-static-binary deployment (copy one file — no environment, no dependency hell). For the **client appliance**, the single binary is the entire value proposition: "copy one file, double-click, it runs, your data never leaves the building" is a thing you can say to a gym or a clinic that a Python-on-Kubernetes stack never can. The Rust CLI ecosystem (`clap`, optionally `ratatui` for a TUI) is among the most mature parts of the language. Clean language boundary: **Rust commands and observes, Python executes**, over HTTP/the API — no FFI, no rewriting working Python.

**Honest limit on the Rust bet:** Rust compounds in the places the model vendors won't go — long-running runtimes (the WhatsApp/SMB service), single-binary appliances for non-technical operators, and the local-model hot path. It is *not* an advantage in "a nicer way to launch Claude Code" — that layer is now built-in and being commoditized by Anthropic itself. Keep Rust where it compounds.

### Scope discipline
First version is one command that does something the built-ins don't: e.g. **run a Project H eval on one node and print the cost/quality result.** It earns its next command only when you reach for one that isn't there. The "control plane for my whole practice" framing — and the "client appliance" framing — are the destination, not the first commit.

---

---

# PART 4: THE THREE INTERNAL-TOOL / PRODUCT IDEAS

These ride on the projects above and map to the studio lifecycle. **Build the thinnest version only when a real need forces it.** They validate the problem; productizing is a separate, later decision (revisit only after a tool survives your own daily use for months).

| Idea | Built on | Studio role | Build trigger |
|---|---|---|---|
| **#3 Research / intelligence synthesis** | Project B + Project G | Prospecting & client ramp | Prospecting the first client |
| **#1 Account / client memory layer** | Project G + Project F | Delivery & retention | ~3 clients; you start forgetting things |
| **#5 Expert "second brain"** | Project G | Capturing your own judgment | Optional; may never need formalizing |

The trap to avoid: infinite internal-tool building with no revenue. The studio earns by shipping client work. Build the thinnest cut at the moment of real need, never a feature ahead.

---

---

# PART 5: REFERENCE TABLES

## Components Built and Where Reused

| Component | Built In | Reused In |
|---|---|---|
| `EmbeddingService` | Phase 0 | A, D, F, G |
| `TranscriptService` | Phase 0 | A |
| `SearchService` (Tavily) | Phase 0 | B, C |
| `ChunkingService` | Phase 0 | A, D |
| `ToolUseNode` | Phase 0 / B | B, C |
| `SelfCriticNode / ReviseNode` pattern | A | C, E |
| `LearningArtifact` model | A | F |
| `RetrieveChunksNode` | D | F (verbatim) |
| `ContentChunk` / `ChatSession` models | D | F |
| `ParallelNode` (merge fixed) | E | G and beyond |
| `MemoryLoaderNode` / `ConsolidationWorkflow` | G | any client/product work (verbatim) |
| `AgentEpisode` / `SemanticMemory` models | G | products #1, #5 |
| Eval harness + per-node routing decisions | H | every node's `model_provider`; client cost optimization |
| Rust harness CLI | parallel track | daily ops across all projects |

## Tech Stack

| Concern | Tool | Notes |
|---|---|---|
| Language | Python 3.12+ | Primary |
| Framework | Your orchestration system | Workflow, Node, TaskContext, AgentNode |
| AI (agents) | Claude via pydantic-ai | `ModelProvider.ANTHROPIC`, `claude-opus-4-7` |
| AI (tool loop) | `anthropic` SDK directly | Project B only |
| AI (cheap/narrow tasks) | `claude-haiku-4-5-20251001` or local Ollama | Critics, classification, routing, episode-write |
| Embeddings | Voyage AI `voyage-2` | 1024 dims |
| Search | Tavily | Built for agents |
| Database | PostgreSQL + pgvector | Extension already in the Docker image |
| Async | Celery + Redis | Configured |
| Env mgmt | `uv` | In use |
| Prompts | `.j2` via PromptManager | Always — never hardcode |
| Testing | pytest + fixtures | Core locked in Phase 0; per-project after |
| Harness | Mac Mini + Caddy + async Claude Code | Remote-triggered dev (GitHub/webhook/Telegram) |

## Portfolio / Interview Narrative (one line each)

| Project | Description |
|---|---|
| Infra + harness | "Production-ready event-driven AI pipeline infra with async queuing, plus a remote-triggered agentic dev harness on self-hosted hardware" |
| A: Content Pipeline | "Agentic pipeline turning any video into structured summaries and blog posts, with self-correcting output" |
| B: Research Agent | "Multi-step research agent with hand-built tool loop and self-correction across web sources" |
| C: Proposal Generator | "Domain agent that researches a company and produces scoped consulting proposals in PT and EN" |
| D: Document Q&A | "RAG system with session memory — answers from a company's own documents, tracks the conversation" |
| E: Specialized Pipeline | "Refactored multi-agent pipeline showing why specialized agents beat generalists" |
| F: Knowledge Base | "Semantic search over a growing corpus of learning artifacts — meaning, not keywords" |
| G: Memory System | "Reusable episodic→semantic memory with confidence decay and contradiction handling — agents that remember across sessions" |
| H: Eval & Routing Harness | "System that empirically routes each workflow node to the cheapest model meeting a measured quality bar — with bias-corrected evaluation" |
| Rust Harness CLI | "Single-binary terminal control plane for triggering and observing remote agent runs and workflows" |

## Red Flags to Watch For

- Hardcoding a system prompt in Python (use `.j2`).
- Not storing embeddings at write time (you'll regret it at Project F).
- Skipping the self-critic loop in Project A (it's the point).
- Using `AgentNode` in Project B (use raw SDK — earn the abstraction).
- Building the hardened Project B / any product idea before a real need exists.
- Shipping a workflow without its tests (the core was hardened in Phase 0 so this discipline could hold).
- Treating "one more project" as the thing standing between you and ready. The checkpoint is a *skill*, not a finish line.
- **Building Project H as a runtime router instead of an offline eval tool** (per-request model selection is overkill; static per-node decisions capture the value).
- **Reaching for Rust where Python is sufficient.** The CLI is the right Rust home (instant startup, single binary, daily use); the orchestration layer is not. Let the heavy Rust runtime moment arrive with data, not enthusiasm.

---

*Living reference. Update as projects complete and client work surfaces new patterns. The Socratic Tutor app and physics study live in separate, archived documents — this plan is solely about becoming an expert agentic/harness engineer and building a practice from it.*

*Last updated: May 2026*
