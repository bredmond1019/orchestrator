---
type: Plan
title: Agentic Engineering Projects & Learning Plan
description: Documentation for this phase or specification.
---

# Agentic Engineering Projects & Learning Plan
## Brandon's Path to Expert Agentic & Harness Engineer — and the Company Brain

*Updated: June 2026 · Status: Active*
*Major revision: Company Brain destination + one-brain-two-shells architecture (see DECISIONS D14–D19)*
*Incorporates: existing Python orchestration framework, codebase analysis, test plan (Option A)*

---

## How to Use This Document

This is your single technical reference. It covers:
- The **Python Agentic Orchestration System** you already built (your infrastructure foundation — and the **brain** of the Company Brain)
- A **Phase 0 codebase orientation** to do before any project
- **7 projects (A–G)** building progressively harder agentic patterns, sequenced by *sellable competence*, plus **Project H** (model evaluation) and the **Rust appliance shell** parallel track
- The **Company Brain architecture** — how Projects D + G + H + the Rust shell assemble into one product with two deployment faces

### The organizing principle

Projects are ordered by one question: **"Does this teach me something I'll sell — or that makes me demonstrably expert?"** Not by any single product's dependency graph. *(See DECISIONS D3.)* But there is now a named destination the projects converge toward — the **Company Brain** (DECISIONS D14) — and several projects are explicitly its components. This is not a return to the old "assemble one app" sequencing; it's recognizing that the expertise-first project set *already adds up to* a defensible product, and naming it so decisions prune faster.

### What the Company Brain is (and which projects build it)

A **Company Brain** ingests a company's scattered knowledge, structures it, keeps it current, and emits an executable skills file agents can act on. In this plan's parts:
- **Project D** (RAG over business documents) = the **retrieval half** — and a pattern you've shipped in production (Helpscout).
- **Project G** (episodic→semantic memory, decay, contradiction handling) = the **"keeps it current" engine** — the half that makes it living rather than static.
- **Project F** (semantic search over a corpus) = the cross-document retrieval surface.
- **Project H** (model eval & routing) = what makes the privacy promise ("runs on your hardware") *honest and measured*.
- **The skills-file emitter** = the Claude Code skills primitive your harness already runs, pointed at the structured knowledge.

### You are not starting from zero

Before the project library: you have already shipped, solo and in production, an **Internal Support Dashboard** (100+ daily cross-functional users, 24–48hr support wait-time reduction, still in daily use — *a primitive company brain*: cross-functional knowledge made queryable and adopted) and a **Helpscout Support Automation** (RAG + vector + semantic search in production — *the Company Brain's retrieval half, already shipped*). You contributed heavily to a production healthcare AI tool (**AI Scribe**) through and past launch. Several projects below are clean, defensible, owned-end-to-end rebuilds of patterns you've already proven. Project D especially. *(See DECISIONS D9.)*

### The rules

1. **Ship each project.** It has to work end-to-end and be demonstrable.
2. **Every project ships with its own tests.** The core engine is locked down in Phase 0 (Test Plan, Option A — DECISIONS D5). From Project A onward, a new workflow means new tests — no exceptions.
3. **Build the thinnest thing that teaches the pattern.** Then expand only when a real need forces it.
4. **Learning content is AI/agentic/harness engineering** — fed through Project A and absorbed as you build.
5. **(New, June 2026) The brain never knows where it's running.** Deployment decisions (which model, where data lives) are *injected via config*, never hardcoded in a node. The first `if running_locally:` in a brain node means you've started building two products. *(See DECISIONS D18.)*

---

---

# PART 1: YOUR EXISTING INFRASTRUCTURE
## The Python Agentic Orchestration System — *the Brain of the Company Brain*

*Before touching any project, understand what you already have. This section is your codebase reference. It reflects the actual code as reviewed, not an idealized version.*

---

## What You Already Built

**Production-ready event-driven AI pipeline infrastructure.** Not a demo, not a starter kit. The core abstractions (Workflow, Node, TaskContext, AgentNode) are clean, composable, and apply to every project here. The Customer Care workflow shipped with it is a **reference implementation only** — you read it to learn the patterns, you do not extend it, and (per Option A) you do not test it.

**Mental model:** this system is the scaffold. Every project is a new workflow attached to it. **And the whole thing, behind a clean API, *is* the deployment-agnostic brain that both the SMB Rust shell and a future enterprise shell wrap (DECISIONS D16).**

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

**The two deployment-injection points (DECISIONS D18) live in this diagram already:**
- **Model provider** is per-node config on `AgentNode` (AgentConfig → pydantic-ai). This is where Project H's routing decisions bake in, and where SMB-vs-enterprise differ.
- **Persistence** is `GenericRepository` over Postgres+pgvector. SMB runs it locally; enterprise runs it managed/multi-tenant. The brain issues identical queries.

Neither requires new machinery — the boundary is enforced by *not* adding `if running_locally:` branches inside nodes.

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
- **Local models are a one-line change** (`ModelProvider.OLLAMA`) thanks to pydantic-ai. **This one-line-ness is the technical foundation of the privacy pitch (DECISIONS D19):** the same node runs against Claude or a local model purely by config, which is exactly why Project H's per-node routing decisions can bake in cleanly and why the SMB shell can run "local-by-default."

| Use | When |
|---|---|
| `AgentNode` (pydantic-ai) | Structured output, production pipelines, agent-call-as-infrastructure |
| Raw `anthropic.Anthropic()` via `ToolUseNode` | Project B only — where learning the tool loop is the goal |

Rule: write the raw `while stop_reason == "tool_use"` loop exactly **once** (Project B). After that, use `AgentNode` forever.

### `core/nodes/parallel.py` — ParallelNode [USE, fix-on-first-use]
Runs nodes concurrently via `ThreadPoolExecutor`.

**Known gap (from code review):** parallel results aren't merged back into the main context — the calling node currently discards the returned list, and parallel nodes mutate the shared `task_context` directly. **Fix when you first genuinely use parallelism (Project E):** have each parallel node write to a uniquely keyed slot and merge after.

### `core/nodes/router.py` — BaseRouter / RouterNode [NO CHANGES NEEDED]
Declarative conditional routing. List of `RouterNode` instances; first match wins; `fallback` on no-match.

### `core/schema.py` — WorkflowSchema / NodeConfig [NO CHANGES NEEDED]
Declarative graph definition. Forces graph-thinking before agent code. `createworkflow` scaffolds it.

### `core/validate.py` — WorkflowValidator [NO CHANGES NEEDED]
DFS cycle detection + BFS reachability, on every `Workflow.__init__()`.

### `services/prompt_loader.py` — PromptManager [CRITICAL HABIT]
Jinja2 + YAML frontmatter `.j2` files. **Never hardcode a system prompt in Python. Always a `.j2` file.** Prompts are assets; iterate the file, not the code.

### `api/` — FastAPI endpoints [TREAT AS A PRODUCT SURFACE, June 2026]
Previously "just the way events get in." Under the Company Brain architecture (DECISIONS D16, Layer 3), **this API is the product's machine-readable interface** — the thing the Rust shell, a future enterprise dashboard, and a client's own coding agent all drive. When you add endpoints, give them clean, documented, stable request/response schemas. The Software-for-Agents thesis (agents as first-class clients) is realized *here*, for free, if the API is designed as a contract rather than an internal detail.

### `worker/` — Celery + Redis [USE FOR ALL LONG-RUNNING PIPELINES]
Accept-and-delegate: FastAPI accepts, persists, queues; worker runs the workflow. Each new workflow adds a `@celery_app.task`.

### `database/` — SQLAlchemy + PostgreSQL [EXTEND WITH NEW MODELS]
`DatabaseUtils`, `db_session`, `GenericRepository` all reusable. **Missing, build as projects need them:** pgvector (one migration), then `ContentChunk` (Project D), `LearningArtifact` (Project A), `AgentEpisode` + `SemanticMemory` (Project G).

### Customer Care workflow — REFERENCE ONLY [DO NOT EXTEND, DO NOT TEST]
A worked example of how the abstractions compose. Read it when confused about wiring a pattern. Build new workflows alongside it, never on top of it.

---

## Infrastructure Gaps to Close First (Phase 0, Foundation Block D)

Build once, reuse everywhere:

1. **pgvector migration** — `CREATE EXTENSION IF NOT EXISTS vector;` then vector columns via Alembic.
2. **EmbeddingService (Voyage AI)** — `voyage-2`, 1024 dims. **A legitimate standing option, not a temporary compromise:** the first full run-through uses top-tier models everywhere (Voyage included) to confirm everything works, then local swaps get introduced and measured in Project H. **Privacy note:** Voyage is hosted — embeddings leave the building — so the strict on-prem SMB story needs a local embedding option, which now has named candidates (Qwen3-Embedding-8B/4B, BGE-M3, Arctic Embed 2.0 — see the Local & Open-Weight Model Reference). Designed as a config swap so Voyage and locals coexist per deployment (DECISIONS D18, D19).
3. **TranscriptService** — wraps youtube-transcript-api, handles long-video chunking.
3b. **ArticleExtractionService** — fetch a URL and extract clean readable text (trafilatura/readability). Powers Project A's `FetchArticleNode`; **reused by the Company Brain to ingest web-based client knowledge** (help docs, public pages, wikis). Build it once, here.
4. **SearchService (Tavily)** — clean structured results for the tool loop.
5. **ChunkingService** — overlapping token-sized chunks for transcripts/PDFs.
6. **ToolUseNode (raw Anthropic)** — for Project B; manages the tool loop manually with a `max_iterations` guard.

**New dependencies:** `voyageai`, `youtube-transcript-api`, `tavily-python`, `pymupdf`, `trafilatura` (article text extraction), and pin `anthropic` explicitly.

---

---

# PART 2: PHASE 0 — CODEBASE ORIENTATION
## Do This Before Any Project. Non-Negotiable.

**Goal:** own the framework mentally, not just use it.

### Step 1 — Read the core engine line by line
`core/workflow.py`, `core/task.py`, `core/nodes/agent.py`, then `parallel.py`, `router.py`, `schema.py`, `validate.py`, `prompt_loader.py`. **As you go, confirm the two deployment-injection points (DECISIONS D18):** that `model_provider` is config on `AgentConfig`, and that persistence is fully behind `GenericRepository`. This is the reconnaissance that proves the one-brain-two-shells architecture is feasible without refactoring.

### Step 2 — Draw the architecture from memory
Close all files. Draw the three tiers with every component and connection on your whiteboard.

### Step 3 — Run the Customer Care workflow end-to-end
`docker compose up -d`, POST an event, watch the Celery worker, inspect the `task_context` JSON in Postgres. Trace every call.

### Step 4 — Answer these five without looking
1. A workflow has 5 nodes. Node 3 needs data Node 1 produced. How does it access it?
2. Two nodes run in parallel then merge. Which node type, and what's the thread-safety consideration?
3. Branch: if content is "spam" go to A, else B. How?
4. Iterate a system prompt without restarting the server — how does PromptManager enable this?
5. A request hits your API. Walk every step until the result is stored in the DB.

If you can answer all five and draw the diagram, Phase 0 orientation is done.

---

---

# PART 3: THE PROJECT LIBRARY (A–G)

*Sequenced by sellable competence. Every project ships with tests. Projects D, F, G, H are explicitly Company Brain components.*

---

## Project A — Content Pipeline (YouTube/Article → Personal Digest + optional Blog)
### Fastest full rep. Your personal knowledge feed AND your content-marketing engine.

**Pattern:** source-routed linear pipeline + self-correction loop, forking to two outputs. **Reuse downstream:** `LearningArtifact` model, the `SelfCriticNode → ReviseNode` pattern, your voice prompt, and — new — `FetchArticleNode` (the Company Brain reuses it to ingest web-based client knowledge).

### Why first
Fastest way to exercise the whole `Workflow → Node → TaskContext → AgentNode → PromptManager → RouterNode` chain end-to-end, and it produces something you'll use *every morning*: a personal knowledge feed. You constantly find YouTube videos and articles (AI engineering, but also physics/relativity, music) you don't have time to consume and then lose. This pipeline ingests them, summarizes and categorizes them, stores them so nothing gets lost, and serves them to a private page you read with coffee on the tablet, on your phone during the day, or on the Kindle at night. The self-critic loop is still the real engineering lesson; the wiring is fast.

### The reframe: a one-person Company Brain (the dogfood version) — and a Honcho evaluation environment

This personal feed is the Company Brain at a scale of one — *you*. Same shape: ingest scattered sources, structure them, store by topic, eventually track what you already know. The "keep track of what I know" instinct is **Project G's job** (semantic memory over your own learning); the categorized, searchable store is **Project F's corpus**. So this is not scope creep away from the plan — it's the personal-scale dogfood of the exact product you're building, and living inside a small one daily will make you understand the real one better. Build the ingestion-and-store layer now; the smart layers (search, "what I already know") attach later *because you stored embeddings at write time*.

**The Honcho validation experiment (DECISIONS D25):** when you get to the memory layer of the personal feed (the "what I already know" smart layer, which is the Phase 3 upgrade after G ships), **use Honcho rather than your own G**. Install Honcho on the Mini (same Postgres + pgvector + Redis stack, Docker Compose, points at Claude Haiku), wire it to the personal feed's `LearningArtifact` store, and live inside it daily. This isn't a production commitment — it's deliberate competitive intelligence. You want to feel: where is Honcho strong (personal preference modeling, communication style, cross-session recall)? Where is it awkward (organizational knowledge, domain-specific extraction, company process modeling)? Where does the domain mismatch (built for personal preferences, your product needs organizational knowledge) show up in practice? The answers will directly inform your Project G design. *Awareness of how the best available competitor works, felt from the inside rather than read in docs, is worth more than any amount of architecture research.* (DECISIONS D25.)

### Two inputs, two outputs

**Inputs (both via POST to `/events/content`):**
- a **YouTube URL** → transcript flow (existing)
- an **article URL** → fetch + readable-text extraction (new)
- the event payload carries an optional **`make_blog` flag** (default false)

**Outputs:**
- **Always: a personal digest** — categorized, stored, served as static HTML on the Mini. This is the default path; every link produces one.
- **On `make_blog=true`: also a public blog draft** in your voice (the original Project A output), through the self-critic→revise loop, for `learn-agentic-ai.com`.

*Decision (DECISIONS D21): digest-always, blog-on-flag.* The default path is the simple one; the blog branch is opt-in, so the feed works from the first link and the pipeline never has to *decide* whether something is blog-worthy.

### End result
POST `{url, make_blog?}` to `/events/content`. Celery runs:
1. `SourceRouterNode` (RouterNode) — YouTube vs article → routes to the right fetch node
2a. `FetchTranscriptNode` — fetch + clean transcript (existing)
2b. `FetchArticleNode` — fetch URL + extract readable text (**new**; trafilatura/readability does the heavy lifting)
3. `SummarizerNode` — structured JSON summary + classification (AgentNode, structured output)
4. `StorageNode` — **(a)** `LearningArtifact` row **with embedding at write time**, **(b)** a static HTML digest page in the right category folder, then regenerate the category index
5. *(only if `make_blog`)* `BlogWriterNode → SelfCriticNode → ReviseNode` → write blog draft to disk

### The reading surface (MVP — deliberately dumb)
- `StorageNode` writes **static HTML** — one page per item + simple per-category index pages. Static HTML is the universal format: renders on the Pixel tablet/phone browsers and is the one thing the Kindle's experimental browser tolerates. No app, no login flow, no JS framework.
- **Caddy serves the folder privately on the Mini** (you're already standing Caddy up in Foundation Block B — this is a near-zero marginal step that reinforces the harness work). Private over the home network or behind simple auth.
- **What this MVP deliberately does NOT have:** no tagging UI, no search box, no "what I already know" intelligence, no cross-device sync engine, no recommendation. Those are Projects F (search over the same embeddings) and G (memory over the same artifacts), attached later for free *because the embeddings are stored now*. Building any of them Day 1 is the infinite-tooling trap wearing your favorite hobby as a costume — refuse it.

### Build notes
- Scaffold with `createworkflow`.
- `SummaryOutput` schema: title, **category** (classify into a small starting set — `ai_engineering`, `physics_relativity`, `music`, `other` — let it grow as you feed it things; don't hardcode a rigid taxonomy), **tl_dr** (one line for skimming), **read_time_estimate** (so morning-coffee-you can pick something short), core_concepts, key_insights, questions_raised, connections_to_my_work, further_exploration.
- **`FetchArticleNode` is the one genuinely new node — and it's quietly valuable beyond this project.** Clean article-text extraction is exactly what the Company Brain needs to ingest a client's web-based knowledge (help docs, public pages, wikis). Build it well; the real product reuses it. Implementation: **trafilatura as the default** (free, local, fast); **Firecrawl as a fallback** when trafilatura returns empty or junk (JS-rendered pages, dynamic content). Handle failures gracefully — store the failure with a `fetch_status` field, don't crash the pipeline. See DECISIONS D24 for the trafilatura-first / Firecrawl-fallback rationale and the `max_calls` guard rule for agent contexts.
- **Summarizer prompt focus areas:** agentic engineering patterns & orchestration, harness engineering & agentic coding, AI system architecture, company-knowledge/RAG/memory systems (bias the corpus toward the Company Brain) — *and* your personal-interest categories (physics/relativity, music), which the same summarizer handles without special-casing.
- **Voice prompt is a long-term asset.** Used only on the blog branch, reused in Project C and all external content.
- **Self-critic loop stays linear** (validator forbids cycles) and lives only on the blog branch.
- **Store embeddings at write time** in `StorageNode` — for *every* item, digest-only included. This is what makes Projects F and G able to attach later. Deferring it hurts twice now (personal search *and* the corpus).

### Capture (how links get in) — MVP, don't over-build
Day 1, the input is just a POST to the existing endpoint: a browser bookmarklet, a phone share-shortcut, or the `send_event` script. **Do not build a capture app.** One-tap capture from the phone is a natural just-in-time upgrade (a phone shortcut, or later the Rust CLI), built when the friction of the MVP capture is actually felt — not before.

### Later upgrades (flagged, NOT built now)
- **Weekly EPUB digest emailed to your Kindle** (Kindle reads `.epub`/`.mobi` + "send to Kindle"). Nice, but morning-coffee-on-the-tablet is the Day-1 case and static HTML nails it. Someday item.
- Search and "what I already know" → Projects F and G, over the same embeddings.
- One-tap phone capture → just-in-time, when MVP capture friction is felt.

### Tests ship with it
Tests for each node (mocked agents): the `SourceRouterNode` routing (YouTube vs article → correct fetch node, plus fallback/clear-error), `FetchArticleNode` extraction (mock the fetch; assert clean text out, graceful failure handling), the `make_blog` branch (assert blog nodes run only when flagged), the storage path (assert embedding written at write time *and* HTML page + index regenerated), and one integration test of the full chain with agents mocked — both digest-only and digest+blog.

---

## Project B — Research Agent (thin first, then hardened)
### The tool loop, written by hand. Once. Your prospecting tool — and your Company-Brain-scoping tool.

**Pattern:** raw agentic tool loop + self-correction. **Reuse downstream:** the tool loop feeds Project C's `CompanyResearchNode`; this is also the seed of the #3 intelligence-synthesis product.

### Why this is the most sellable competence
"Research a company, find the automation opportunity" *is* the consulting motion — and the front edge of scoping a Company Brain. Building it makes you able to walk into an unfamiliar business and see the work, including *where knowledge is trapped in one person's head.*

### Thin cut first (build this, stop here until a prospect needs more)
A single `ToolUseNode` (raw `anthropic.Anthropic()` — write the `while stop_reason == "tool_use"` loop yourself; the `max_iterations` guard is not optional) plus Tavily. Input a company name; output a structured brief: what they do, where they likely bleed time, one automation hypothesis. **No Celery, no critic, no storage. ~50 lines.**

### Hardened version (only when a real prospect makes you want more)
1. `PlannerNode` (AgentNode) — research plan
2. `ResearchNode` (ToolUseNode) — `web_search` + source tools
3. `CriticNode` (AgentNode) — gaps, unsupported claims
4. `ReviseNode` (AgentNode)
5. `StorageNode` — `LearningArtifact` + embedding

### Build notes
- **This is the one project where you bypass `AgentNode`.** Feel the loop. After this, you've earned the abstraction.
- Tavily over raw search APIs — built for agents.

### Tests ship with it
The tool loop with a mocked client (assert it injects results and terminates on `end_turn` and on `max_iterations`), plus node tests for the hardened version.

---

## Project C — Client Proposal Generator
### Your first real business tool. The competence-checkpoint skill, trained.

**Pattern:** research → structured output → review/revise with routing. **Business value: high.**

### Why it matters
The `OpportunityIdentifierNode` prompt *is* the skill of seeing automation in a business you don't know — the "three workflows in 30 minutes" checkpoint. The structured-output-against-a-schema work here is the *same skill* you exercised in production on AI Scribe.

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
- `Opportunity` schema: name, problem_statement, proposed_solution, estimated_value, build_complexity, fit_score. `OpportunitiesOutput`: opportunities, recommended, rationale.
- **Review criteria:** names client ≥3×? exactly one specific testable deliverable? realistic timeline (4–8 wks first project)? avoids vague language? investment matches complexity? Each PASS/FAIL with a line reference; router sends to `ReviseNode` on "revise", to `StorageNode` on "pass".
- **One recommendation, not three.**
- **New (June 2026):** where a prospect is at the 30–80 inflection, one of the three opportunities the identifier surfaces should be a *thin-slice Company Brain* ("your onboarding knowledge / your SOPs, made queryable, on your hardware"). Train the prompt to recognize knowledge-fragmentation pain, not just task automation.
- Run it on the two warm leads as practice.

### Tests ship with it
Node tests (mocked agents), the router's pass/revise branching, structured-output schema validation.

---

## Project D — Document Q&A + Session Memory (RAG)
### The most common SMB request. **The Company Brain's retrieval half.**

**Pattern:** full RAG + session memory. **Reuse downstream:** `RetrieveChunksNode` (verbatim later), `ContentChunk` + `ChatSession` models. **This is half the Company Brain (DECISIONS D14).**

### Why it matters
RAG over a client's own documents — SOPs, product catalogs, internal wikis, policy docs — is the single most common SMB automation ask *and* the retrieval foundation of the Company Brain. Build it now, framed for *business documents*, not textbooks.

**You have already shipped this in production.** Your Helpscout Support Automation used RAG, vector search, and semantic search, architected by you, solo. So Project D is **reinforcement and a clean portfolio refresh of a proven competence, not first contact.**

### End result
**Ingestion** (`/events/ingest_document`): `ParseDocumentNode → ChunkDocumentNode → EmbedChunksNode → StoreChunksNode`.
**Query** (`/events/query`): `EmbedQuestionNode → RetrieveChunksNode → AssembleContextNode → AnswerNode → UpdateSessionMemoryNode`.

### Build notes
- Models: `ContentChunk(doc_id, position, section_title, content, embedding)`, `ChatSession(doc_id, turns JSONB, topics_covered, timestamps)`.
- **Build `RetrieveChunksNode` carefully** — cosine-distance top-k; reused verbatim downstream.
- Chunk size: 500 tokens / 50 overlap starting point; tune on a real business doc.
- **The distinction to internalize:** RAG retrieves from the document; session memory tracks the conversation. Both are context, assembled together in `AssembleContextNode`. This is the conceptual groundwork for Project G — and the line between "static knowledge" (RAG) and "living knowledge" (G's memory) that defines the full Company Brain.
- **New (June 2026) — note model routing as you build:** embedding and retrieval are pure-local-friendly; the `AnswerNode` is where answer quality lives and may want a stronger model. Don't optimize yet — just observe which steps are which, as input to Project H. This is where the "local-by-default, frontier-for-the-few" map starts (DECISIONS D19).

### Tests ship with it
Retrieval correctness (mock embeddings, assert ordering), the RAG-vs-session-memory assembly, ingestion chunking boundaries.

### Competence checkpoint
After Project D, test yourself against the checkpoint (three automatable workflows in 30 min, with local-vs-paid for one). If yes → ready for a paid diagnostic. If no → name exactly what's missing, and be suspicious if the answer is "one more project."

---

## Project E — Specialization Refactor
### Architectural judgment. The before/after is the whole point.

**Pattern:** specialized nodes + parallelism. **Kept separate from Project A on purpose.**

### Why it's separate
If you wrote Project A in its final specialized form, you'd skip the lesson. You build the naive single-pass pipeline, feel its limits, then refactor and watch quality change. That experience is what lets you *explain to a client or interviewer* why specialization matters.

### The refactor
**Before:** `Fetch → Summarizer → BlogWriter → SelfCritic → Revise → Storage`
**After:** `Fetch → [ConceptExtractorNode ‖ StructureAnalystNode] → BlogDraftNode → VoiceMatchNode → SelfCritic → Revise → Storage`

### Build notes
- **Fix the `ParallelNode` merge gap here** (each parallel node writes a uniquely keyed slot; merge after). First genuine need for parallelism.
- Run the same video through old and new pipelines; compare. The quality delta is the lesson.
- Write the comparison — strong LinkedIn material.

### Tests ship with it
The parallel merge (assert both slots present and correctly combined), plus the new specialized nodes.

---

## Project F — Semantic Search Over Your Corpus
### Reuse + the tool you'll actually use to learn. **Company Brain's cross-document retrieval surface.**

**Pattern:** semantic retrieval at corpus scale. **Mostly Project D components.** Seed of the client-memory product — now understood as part of the Company Brain.

### End result
`GET /knowledge/search?q=...` returns top-3 relevant `LearningArtifact`s with excerpts and source URLs; optional synthesis (a single `AgentNode` consolidating top-k into one answer).

### Build notes
- The payoff for storing embeddings at write time since Project A.
- Prove semantic (not keyword) retrieval: search "agents communicating" and confirm you get results tagged "multi-agent orchestration."
- **Practical use:** before each study session, query "what have I learned about context engineering / harnesses / orchestration / company-knowledge systems?"

### Tests ship with it
Ranking/ordering with mocked embeddings; the synthesis node with a mocked agent.

---

## Project G — Agent Memory System (Episodic → Semantic)
### The hardest. The most differentiating. **The Company Brain's "keeps it current" engine.**

**Pattern:** episodic→semantic consolidation, confidence decay, contradiction handling, multi-peer entity modeling. **Reuse downstream:** `MemoryLoaderNode` (verbatim), the whole module. **This is the half of the Company Brain that turns static RAG into a living map of how a company works (DECISIONS D14, D4).**

### Before you build: study Honcho (DECISIONS D25)

**Read Honcho's source code before writing a single line of Project G.** Honcho (Plastic Labs, open-source, github.com/plastic-labs/honcho) is the best available open reference implementation of reasoning-first agent memory. It's the same problem you're solving, built by people who've thought hard about it, with published benchmarks validating their architecture choices.

**What Honcho gets right that you should directly adopt:**
- **Two-stage reasoning pipeline.** Ingest-time: a fast model captures latent information from each new message immediately (preferences, claims, contradictions) and updates the entity's representation. Dream-time: a separate background process periodically revisits prior messages and prior reasoning, drawing new inferences. This is better than your original single-stage Celery consolidation job — the ingest-time pass keeps representations current immediately; the dream-time pass finds things that require reasoning across multiple sessions. Adopt both stages. Your Celery infrastructure already supports this split cleanly.
- **Multi-peer entity model.** Honcho's primitive is a *peer* — any entity that persists and changes over time: a user, an AI agent, a company, a client, a product, an SOP. For the Company Brain, this is the right abstraction. You're not modeling one thing; you're modeling the company, its clients, its products, its processes, and the relationships between them. Your original `AgentEpisode`/`SemanticMemory` schema was single-entity — evolve it toward multi-peer (see schema below).
- **Natural-language query interface.** Honcho's query model is "ask a research agent a question in natural language, get a synthesized answer" — not "embed a query string, retrieve top-k chunks." For memory that reasons, this is strictly better. Your `MemoryLoaderNode` should evolve toward this: load relevant representations with a natural-language question, not just cosine similarity.

**What your version does differently — and why that's your advantage:**
- **Domain specificity.** Honcho was built for user-modeling in conversational AI (preferences, beliefs, communication styles). The Company Brain models *organizational knowledge* — processes, client relationships, product facts, evolving SOPs, things-only-this-person-knows. The domain is different enough that owning the consolidation prompt is an asset. Yours is tuned, inspectable, versioned in `.j2`, and improvable via Part 5's prompt-evolution loop. Honcho's ingest-time model is a fine-tuned black box.
- **Privacy-first deployment.** Honcho's managed service sends data to their API. Your version runs on the client's hardware. The reasoning model question (can a local model do ingest-time extraction?) is exactly what Project H measures.
- **You understand every design decision.** When a client asks why a fact is wrong, you can trace it. With Honcho's fine-tuned model, you can't.

**The competitive intelligence framing (also DECISIONS D25):** you're validating Honcho on your personal knowledge feed first — not because you'll use it in production, but because living inside it daily for weeks will teach you where it's strong, where it's awkward, and where the domain mismatch (personal preferences vs. organizational knowledge) shows up in practice. That's competitive intelligence you feel, not just read. When you build your own G, you'll know exactly what you're improving on.

### Why this is the capstone now
Durable memory that gets smarter across sessions, decays confidence over time, handles contradictions, and models multiple entities is frontier-adjacent and the thing most teams get wrong. For a Company Brain, it's the difference between "search over docs" and "knows how this company actually operates, including the parts no document states." Honcho's benchmarks prove the approach works (90.4% on LongMem S, beating even the oracle-context baseline) — your job is to build the version of this that runs privately, on organizational knowledge, on the client's own hardware.

### End result
A memory module attachable to any workflow, with a two-stage pipeline:
1. **Write episode / ingest-time pass** (after each interaction turn): fast extraction — what happened, what was learned, what was contradicted. Updates the relevant peer's representation immediately. Fast, cheap, local-model candidate.
2. **Dream-time consolidation job** (Celery, session-end + nightly): deeper background reasoning across recent episodes and prior representations. Extracts durable facts, resolves contradictions, updates confidence, draws cross-session inferences. This is the Claude-only step.
3. **Memory loader** (session start): loads top-k relevant representations via natural-language query — not just cosine similarity.

### Models — evolved to multi-peer (informed by Honcho)
```
Peer(
    peer_id,            # company | client_X | product_Y | sop_Z | agent_name
    peer_type,          # [company, client, product, process, agent, user]
    workspace_id,       # Company Brain workspace
    representation,     # current synthesized summary of what's known
    updated_at
)

AgentEpisode(
    peer_id,            # which peer this episode is about
    session_id,
    summary,            # ~40 tokens, fast ingest-time extraction
    outcome,            # [learned|contradicted|confirmed|bookmarked|unclear]
    tags,
    embedding,
    occurred_at
)

SemanticMemory(
    peer_id,            # which peer this fact belongs to
    fact,               # specific, falsifiable
    confidence,         # 0–1
    evidence_episode_ids,
    decay_factor,       # default 0.95/week
    source_peer_id,     # which peer observed this (supports "what does A know about B")
    timestamps,
    embedding
)
```

**The multi-peer unlock for the Company Brain:** you can now model not just "what does the company know" but "what does the support agent know about client X" or "what has changed in SOP Y over the last quarter." That's the peer model in practice, and it's what makes the Company Brain genuinely organizational rather than just a fancy document store.

### The consolidation prompt — the real work, and the privacy asterisk
Extract 3–5 durable, **specific and falsifiable** facts per peer. Assign confidence by evidence strength. **If a fact contradicts an existing one, lower the old fact's confidence rather than overwriting — learning is non-monotonic.** Return valid JSON only, keyed by `peer_id`.

**This is THE step that stays on Claude (DECISIONS D19).** Honcho's benchmarks confirm this directly: their ingest-time pass uses a small fine-tuned model (gemini-2.5-flash-lite), but the deep consolidation — the reasoning that surfaces non-obvious inferences — uses claude-haiku-4-5. A weak model here produces plausible-but-wrong durable facts that silently corrupt everything downstream. Project H will confirm with data, but the design assumption is locked: consolidation is frontier-only. Being able to point at exactly this step and explain exactly why is itself a senior signal.

**Honcho's token efficiency data, now a design input for Project H:** Honcho achieves 90.4% accuracy while using a *median 5%* of available context per query. That's the difference between a $0.50 query and a $0.05 query at scale. The target for your G is the same: keep representations dense enough that the loader injects 5–10% of context, not 80%. This is a measurable quality criterion for Project H to evaluate.

### Build notes
- **Read Honcho's source before starting.** Their FastAPI server, Postgres schema, and Celery worker setup are directly instructive — same stack as yours. Note: their ingest-time and dream-time pipeline implementation is the most valuable thing to study.
- **Confidence decay is not optional:** `new = confidence * decay_factor ** weeks_elapsed`, run in `UpsertMemoryNode`.
- **Contradictions expected:** lower confidence on the contradicted fact, create a new one. Never overwrite.
- **Standalone importable module** — `MemoryLoaderNode`, `EpisodeWriteService`, `IngestTimeExtractionNode`, `ConsolidationWorkflow`, no coupling to any one workflow.
- **Ingest-time extraction is a local-model candidate** — it's a bounded, fast task (extract latent facts from one message). Evaluate in Project H: if a 7–9B model clears the quality bar, the ingest-time pass costs pennies and stays local.
- **Dream-time consolidation must stay on Claude.** The reasoning across multiple episodes and prior representations to surface non-obvious inferences is exactly where weak models produce confident-but-wrong output.
- **Query interface:** implement natural-language query (`MemoryLoaderNode` takes a question string, returns a synthesized answer assembled from relevant representations) alongside the cosine-similarity retrieval. The NL interface is what Project F's semantic search points at, and it's what clients actually want to use.

### Tests ship with it — and they matter most here
Consolidation output schema validity (per peer, multi-peer case); the decay function (`freezegun` to advance weeks, assert `confidence * 0.95**weeks`); contradiction handling (assert old-fact confidence drops, new fact created, no overwrite); multi-peer isolation (assert peer A's facts don't bleed into peer B's representations); ingest-time extraction (fast path produces a valid summary and episode write); `MemoryLoaderNode` retrieval ordering (both cosine and NL query modes). Bad memory output is the trust-eroding silent failure — test it harder than anything else in the plan.

---

## Project H — Model Evaluation & Routing Harness
### Knowing exactly which nodes can run local without degrading output — and proving it. **What makes the privacy promise honest.**

**Pattern:** offline evaluation; empirical model routing. **Reuse downstream:** the routing decisions bake into every node's `model_provider`; this *is* the SMB-vs-enterprise model config (DECISIONS D18). **Sellable as:** "I cut your AI spend substantially with measured quality retention — and here's exactly what runs on your hardware versus what leaves it."

*Sequencing: best placed after Project D (you'll have summarizer, proposal, and RAG nodes to evaluate), and it pairs naturally with Project G. Lettered H; the build order is recommended, not fixed.*

### The thesis it proves (now load-bearing — DECISIONS D19)
Decompose a workflow into small enough nodes and local models handle most of them, with frontier models reserved for what genuinely needs frontier reasoning. Your node-based architecture is already the precondition. This project turns that thesis from a hunch into measured, defensible fact — **and the privacy wedge of the whole Company Brain depends on it being true and demonstrated, not asserted.**

### The expert distinction
The value is **not** "run everything local." It's the *routing judgment* — knowing, with data, which nodes are safe local and which silently degrade off-frontier (above all, Project G's consolidation step). The rigorous version ("I built a system that empirically routes each node to the cheapest model meeting a quality bar, here's the data") is a consulting offering, a differentiator, and the technical backbone of the privacy promise.

### Critical design principle: offline eval, not runtime router (DECISIONS D8)
This runs **occasionally and deliberately**, to *produce* routing decisions ("node X is safe on local-70B"). Those decisions bake into the node's `model_provider` config at design time. You are **not** building per-request runtime model selection.

### What it does
For a given node, run a set of representative inputs (30–50 real examples) through several models — a frontier reference (Claude Opus), a mid local (e.g. Llama/Qwen 70B-class), a small local (7–9B) — score each output, and produce a per-node table: how much reference quality each model retains, at what cost. **The output is the model-routing config file the brain loads at startup — different file for SMB (local-heavy) vs enterprise.**

### Scoring strategy — by node type
- **Deterministic / structural** (structured-output nodes, the consolidation node): valid schema? required fields present? values in range? Cheap, objective; catches where small models fail first.
- **Reference-based** (extraction tasks): compare extracted facts against a hand-labeled set.
- **LLM-as-judge** (open-ended prose): a frontier model scores candidates against a rubric. **Handle judge bias explicitly** — score *blind*, randomize order, use specific criteria. Correcting for judge bias is itself a senior signal worth writing about.

### How it fits your system
It rides on what you have. A node declares its model via `AgentConfig`; swapping `ModelProvider` is nearly free. The harness is a runner that takes a node + inputs + a list of model configs, executes the node under each, scores, and persists results. It is itself a workflow in your own framework — you're using your orchestration system to evaluate your orchestration system.

### Also evaluate: the local embedding option
Per the Block-D note, the strict on-prem story needs embeddings that don't leave the building. Include a local embedding model in the eval (retrieval quality with local vs Voyage embeddings on a real business-doc corpus). If local retrieval holds up, the privacy promise has no embedding asterisk.

### Tests ship with it
The scoring functions (deterministic scorers against known-good/known-bad outputs); the blind/randomized judge harness (assert it strips model identity and randomizes order); results persistence.

### The future Rust attach point (back of mind, not built now — DECISIONS D7)
If, much later, you lean so heavily on local models that the *serving runtime* (loading, batching, streaming, memory) becomes a *measured* bottleneck off-the-shelf serving (Ollama) can't clear, that runtime layer is genuine Rust territory. **You do not build this now** — the moment announces itself with data.

---

## Parallel Track — Rust Appliance Shell *(formerly "Rust Infrastructure CLI")*
### The SMB delivery vehicle for the Company Brain. Where Rust stays warm — and earns a product role.

*Upgraded scope, June 2026 (DECISIONS D17): this is no longer just a personal ops CLI. It is the **SMB shell** of the Company Brain — the single binary that is the privacy promise made physical. Still a parallel track with no fixed slot; develop it whenever you want a Rust session.*

### What changed, and what didn't
Anthropic's May 28, 2026 Claude Code releases (**Agent View** `claude agents`, **Dynamic Workflows**, subagents) **commoditized the "trigger and watch Claude Code coding runs" job.** Do not rebuild it in Rust — use the built-ins for the *coding-agent* case. That ruling stands. What's new is that the *other* thing this track was always partly about — a control plane for *your* infrastructure — is now recognized as the **SMB product shell**, not just a dev convenience.

### What it is, and how it differs from Claude Code
**Claude Code does the coding work and manages its own coding sessions.** **This binary is the operational interface to the Company Brain's *Python brain* — and, packaged for a client, the appliance a non-technical operator runs.** They're stacked, not competing: let Claude Code orchestrate Claude Code; this binary commands and observes *the brain*.

### What it does — re-aimed at the product
- **(Spine) Supervise and operate the local brain.** Start/stop the Python brain + local Postgres, run first-time setup, trigger an ingestion or a query, inspect what's stored. First-class commands over ad-hoc `curl`/DB queries. This is the operator's whole interface in the SMB deployment.
- **(Spine) Observe infrastructure and the cost/privacy layer.** Status of what's running, recent runs, failures, logs — and, wired to Project H, **per-node model routing and measured cost/quality**: which nodes ran local vs. hit Claude this week, what it cost, what local saved, what left the building and what didn't. **This is the surface that makes the privacy promise legible to a non-technical client.**
- **(Product) The single-binary client appliance.** The same binary a client runs on their own hardware to operate and observe their Company Brain — and to see, in plain numbers, what it cost and what stayed private. This is the delivery vehicle for the whole SMB thesis.
- **(Demoted to thin convenience) Remote coding triggers.** The only seam the Claude Code built-ins don't cover is *phone → your own Mac Mini, surviving sleep.* Keep a thin remote-trigger command only if you still want it after trying the built-ins. Don't lead with it.

### Why Rust is an unambiguous fit here (DECISIONS D6, D17)
A binary an operator invokes daily wants instant startup and single-static-binary deployment. For the **client appliance**, the single binary *is* the value proposition: "copy one file, double-click, it runs, your data never leaves the building" is something you can say to a clinic or a growing startup that a Python-on-Docker stack never can. The Rust CLI ecosystem (`clap`, optionally `ratatui`) is mature. Clean language boundary: **Rust commands and observes, Python executes**, over HTTP — no FFI, no rewriting working Python.

**Honest limit on the Rust bet:** Rust compounds in single-binary appliances for non-technical operators, long-running runtimes, and the local-model hot path. It is *not* an advantage in "a nicer way to launch Claude Code" — that's built-in now. Keep Rust where it compounds.

### Scope discipline
First version is one command that does something real end-to-end: **start the local brain, ingest one document, run one query against a local model, print the answer and what it cost.** That single command is the entire SMB thesis in miniature. It earns its next command only when you reach for one that isn't there. The "control plane for my whole practice" and "client appliance" framings are the destination, not the first commit.

---

---

# PART 4: THE COMPANY BRAIN — ASSEMBLY & THE THREE PRODUCT IDEAS

*The three internal-tool ideas from earlier revisions are now understood as facets of, or adjacencies to, the Company Brain. Build the thinnest version of anything here only when a real need forces it.*

## How the projects assemble into the product

| Company Brain part | Built from | Status after Phase 3 |
|---|---|---|
| Retrieval (static knowledge) | Project D | shipped as a project |
| Web-source ingestion (entire sites) | `CrawlSiteNode` (Firecrawl `/crawl`) | thin build on first client with web-hosted docs |
| Cross-document search | Project F | shipped as a project |
| Living memory (keeps it current) | Project G | shipped as a project |
| Honest model routing / cost & privacy | Project H | shipped as a project |
| Skills-file emitter (agents act on it) | harness skills primitive + Brain v1 | thin build, on real need |
| SMB delivery (single binary, on-prem) | Rust appliance shell | thin build, on first client pull |
| Enterprise delivery (cloud, multi-tenant) | Enterprise shell around same brain | only on enterprise pull (DECISIONS D16) |

**The assembly is not a new project** — it's wiring components you built for their own sake behind the clean API, then putting a shell on it. That's the payoff of expertise-first sequencing: the product falls out of the learning.

## The three earlier product ideas, re-situated

| Idea | Built on | Relationship to Company Brain | Build trigger |
|---|---|---|---|
| **#3 Research / intelligence synthesis** | Project B + G | Prospecting & client-ramp tool; front edge of scoping a brain | Prospecting the first client |
| **#1 Account / client memory layer** | Project G + F | *Is* the Company Brain's memory, applied per-client | ~3 clients; you start forgetting things |
| **#5 Expert "second brain"** | Project G | The Company Brain pointed at *your own* judgment | Optional; may never formalize |

The trap to avoid: infinite internal-tool building with no revenue. The studio earns by shipping client work. Build the thinnest cut at the moment of real need, never a feature ahead.

---

---

# PART 5: THE SELF-IMPROVING SYSTEM (Phase 3+ Capstone)
## How the framework evolves, corrects itself, and lets agents extend it — safely

*This is a frontier capstone, not a near-term build. It assembles from the plan (clean API + node library + validator/test-gate + Project H), exactly like the Company Brain. Governed entirely by DECISIONS D20. Read the trigger discipline at the end before touching any of it — this is the infinite-internal-tooling trap in its most seductive form.*

### The one principle that governs all of it (DECISIONS D20)

> **The system may freely do what is measured and gated. New capability enters only by human-reviewed PR. The gates themselves are never self-approved.**

The thing being graded never rewrites its grader. Everything below is an application of that single line.

### The three tiers, separated (they get blurred; don't blur them)

**Tier 1 — Self-correction (you already build this).** A system that fixes its own *outputs*. The `SelfCriticNode → ReviseNode` pattern (Project A) is the bounded version. The deeper version closes the loop with *real outcome signals* instead of a critic's opinion: did the retrieved chunk answer the question, did the proposal convert, did a consolidated fact later get contradicted. Project G's contradiction handling (lower confidence on a contradicted fact) is already a primitive of this — the system noticing it was wrong. Safe by construction; the output is transient and re-derivable.

**Tier 2 — Self-evolution (the highest-value tier — tuning what exists, gated by measurement).** Not new code — *improving existing components*, each change scored before promotion:
- **Prompt evolution.** Prompts are `.j2` assets decoupled from code (the PromptManager habit). A meta-workflow generates a candidate prompt variant; **Project H scores it against the incumbent** on held-out examples; the winner is promoted. Every piece already exists (prompts-as-assets, eval harness, scoring rubric). **This is the highest-leverage, lowest-risk self-improvement available to you** — no path to silent catastrophic failure because every change is measured before it ships. It produces a real "the system improved itself, here's the measured delta" story (strong content, genuine differentiator).
- **Routing evolution.** Project H re-runs periodically against accumulated *real production* examples; when a cheaper model now clears a node's quality bar (models improved, or the prompt got better), the routing config updates. The system gets cheaper over time at constant quality — automatically, but **still offline and gated, never per-request** (preserves D8). It's the *config* that evolves, not the runtime.
- **Memory evolution.** Project G's episodic→semantic consolidation with decay and contradiction handling *is* self-evolution — the system getting smarter across sessions while staying honest. You're already building the most sophisticated piece of this tier.

**Tier 3 — Self-construction (the headline ask — safe *only* because of your architecture).** A system that builds its own workflows and grows its own capability. Split into two speeds:

- **Composition (fast, free, agent-driven).** Your framework has the precondition almost nothing else does: a workflow is **data** (`WorkflowSchema` — a declarative node graph), not imperative code, and the `WorkflowValidator` runs DFS-cycle + BFS-reachability checks on *every* `Workflow.__init__`, *before* anything executes. So an agent can **compose a new workflow by emitting a schema over existing trusted nodes**, the validator rejects malformed graphs before they run, and candidates run against test inputs in a sandbox before registration. The agent writes *graph definitions over vetted components* — never execution code. This is the safe, buildable, differentiating version most "self-building agent" attempts skip (they let agents write code and skip the validator-and-test gate, then explode in production).
- **Capability expansion (slow, human-gated, by PR).** New *nodes* — new `process()` code touching your infrastructure — enter only through a pull request. The Notion example, end to end: an agent researches the Notion MCP server, writes a `NotionNode` conforming to the `Node` ABC, writes its `.j2` prompt and its tests (non-negotiable), and opens a PR. CI runs the tests; the validator checks example workflows; **a human reviews the code** (credential handling, conventions, a clean `process`) and merges or doesn't. **Review happens once per capability, not once per use** — once merged, every agent composes `NotionNode` freely. That asymmetry is the whole design: capability grows slowly and deliberately; composition over what exists is fast and free.

### Why this *is* Software for Agents (not just an internal tool)

The RFS thesis: agents need machine-readable interfaces and discoverable docs to be first-class operators of software. This framework, exposed that way, is exactly that — *for building automation itself*. An agent doesn't just *use* your tools; it *extends the toolset*, through a disciplined contribution process. You'd be shipping the rails on which agents safely grow a company's automation capability. It dovetails with the Company Brain: the brain knows how a company works; this layer lets agents *act* on that knowledge by composing and proposing the workflows that do the work. (Same instinct as the skills-file emitter — turn knowledge into agent-actionable capability — one layer up.)

### What you'd actually build (note how little is new)

The **agent-facing API/CLI** is the Layer-3 surface you already committed to as a product contract (Phase 0/D), now with a demanding first consumer — an agent that needs to:
1. **Discover what nodes exist** — a **capability registry** endpoint: the trusted nodes, their input/output schemas, what each does. *This is the one genuinely new primitive, and it's small* — your nodes are already declarative classes; you're exposing a machine-readable catalog of them.
2. **Compose a workflow** — submit a `WorkflowSchema`, get it validated, run it against test inputs in a sandbox.
3. **Propose a new node** — scaffold via `createworkflow` (already exists), then open a PR.

The **Rust appliance CLI** is the natural home for the human side: `brain nodes list`, `brain workflow validate`, `brain pr review` — a real reason for the CLI to exist beyond ops.

### The boundary, stated as build rules (DECISIONS D20)

- Agents **may**: self-correct outputs; propose prompt variants (H decides); compose workflows over trusted nodes (validator + test-gate decide); open PRs for new nodes.
- Agents **may not**: author-and-deploy new node code without review; self-approve PRs; modify the validator, the test-runner, the capability registry's notion of "trusted," the eval rubric, or the Project G consolidation prompt autonomously.
- Those last items are **human-owned gates.** An agent may open a PR *against* the validator; it may never merge one. The grader stays out of the graded system's reach.

### Trigger discipline — READ THIS BEFORE BUILDING ANY OF IT

This is a **platform**, and platforms are where solo builders vanish for a year building something beautiful no client asked for. You have a documented infinite-internal-tooling weakness; this is its most seductive costume.

- **The Notion node is a one-afternoon hand-build today.** No platform required. Build it by hand.
- **Build the second and third nodes by hand too.** Feel the scaffold→test→PR dance as a manual chore.
- **The trigger to build the agent-contribution layer is real, repeated friction** — you notice you're doing the same rote dance often and wish an agent would do the boring parts. *That* is the signal. Not "it'd be cool." Not "it'd demo well."
- **The thinnest first cut** is "agent scaffolds the node and opens the PR; human does everything else" — and even that waits until hand-building is a felt chore.
- **Prompt evolution (Tier 2) is the better first self-improvement build** than any of Tier 3 — it's almost entirely H infrastructure, has no catastrophic failure path, and produces the measured-self-improvement story. Do it first if you do any of this.

Sequencing: all of Part 6 is **Phase 3+**. It depends on the clean API (Phase 0/D), a node library large enough to compose over (Projects A–G), a trustworthy validator and test-gate (Phase 0/C), and the eval harness (Project H). Like the Company Brain, it *assembles* from the plan — it is never a detour from it.

---

---

# PART 6: REFERENCE TABLES

## Components Built and Where Reused

| Component | Built In | Reused In |
|---|---|---|
| `EmbeddingService` | Phase 0 | A, D, F, G |
| `TranscriptService` | Phase 0 | A |
| `ArticleExtractionService` / `FetchArticleNode` | Phase 0 / A | A, **Company Brain (web-source ingestion)** |
| `CrawlSiteNode` (Firecrawl) | Company Brain build | Company Brain client doc ingestion, Research Agent (future) |
| `SearchService` (Tavily) | Phase 0 | B, C |
| `ChunkingService` | Phase 0 | A, D |
| `ToolUseNode` | Phase 0 / B | B, C |
| `SelfCriticNode / ReviseNode` pattern | A | C, E |
| `LearningArtifact` model | A | F |
| `RetrieveChunksNode` | D | F (verbatim), Company Brain |
| `ContentChunk` / `ChatSession` models | D | F, Company Brain |
| `ParallelNode` (merge fixed) | E | G and beyond |
| `MemoryLoaderNode` / `IngestTimeExtractionNode` / `ConsolidationWorkflow` | G | any client/product work (verbatim), Company Brain |
| `Peer` / `AgentEpisode` / `SemanticMemory` models (multi-peer) | G | Company Brain memory (company/client/product/process peers), products #1/#5 |
| Eval harness + per-node routing config | H | every node's `model_provider`; SMB-vs-enterprise model config; cost optimization |
| Clean documented HTTP API | Phase 0 / D | every shell + agent client (Layer 3) |
| Rust appliance shell | parallel track | SMB Company Brain delivery; daily ops |

## Tech Stack

| Concern | Tool | Notes |
|---|---|---|
| Language (brain) | Python 3.12+ | Primary; deployment-agnostic |
| Language (SMB shell) | Rust | Single binary; clap, optionally ratatui |
| Framework | Your orchestration system | Workflow, Node, TaskContext, AgentNode |
| AI (agents) | Claude via pydantic-ai | `ModelProvider.ANTHROPIC`, `claude-opus-4-7` |
| AI (tool loop) | `anthropic` SDK directly | Project B only |
| AI (cheap/narrow + local) | `claude-haiku-4-5-20251001` or local Ollama (Qwen/Llama 70B-class, 7–9B small) | Critics, classification, routing, episode-write; routing decided by Project H |
| AI (frontier-only) | Claude | Project G consolidation step — never local (DECISIONS D19) |
| Embeddings | Voyage AI `voyage-2` (1024 dims) default; local options (Qwen3-Embedding / BGE-M3 / Arctic Embed 2.0) evaluated in H | see Local & Open-Weight Model Reference below |
| Search | Tavily | Built for agents |
| Database | PostgreSQL + pgvector | Local (SMB) or managed (enterprise) — same queries |
| Async | Celery + Redis | Configured |
| Env mgmt | `uv` | In use |
| Prompts | `.j2` via PromptManager | Always — never hardcode |
| Testing | pytest + fixtures | Core locked in Phase 0; per-project after |
| Harness | Mac Mini + Caddy + async Claude Code | Remote-triggered dev |
| Networking — public | Caddy + Cloudflare DNS (port 80/443) | `learn-agentic-ai.com` and public blog — accessible to anyone |
| Networking — private | **Tailscale** (free Personal plan, unlimited devices) | Personal feed, orchestration API, all private tooling — your devices only; no open ports (DECISIONS D23) |
| Web extraction — default | trafilatura | Free, local, fast for clean articles; used in `ArticleExtractionService` |
| Web extraction — fallback + crawl | **Firecrawl** (free tier 500 credits/month) | JS-heavy pages, paywall-adjacent sites (fallback); full-site `/crawl` for Company Brain client doc ingestion (`CrawlSiteNode`); MCP-native agent tool support (DECISIONS D24) |
| Deployment injection | config only, never code | model routing + persistence (DECISIONS D18) |

## Local & Open-Weight Model Reference

> ⚠️ **This table goes stale fast — treat it as a snapshot, not a source of truth.** Last verified **June 2026**. The open-weight landscape reshuffles every few weeks; new models ship and leaderboards reorder constantly. **The durable answer is Project H: run candidates through your own eval harness on your own business-doc corpus (recall@10, nDCG@10 for retrieval; the per-node scorers for LLMs) and let *your data* make the call.** This table is a starting shortlist for *what to feed into H*, not a verdict. Re-verify model names, sizes, and licenses before committing — names like "Qwen 3.6" will be "Qwen 3.8" by the time you read this.

**Two hard rules that don't go stale:**
1. **Project G consolidation stays on Claude — never local**, regardless of how good a local model looks. A weak model here produces plausible-but-wrong durable facts that silently corrupt everything downstream (DECISIONS D19). This is the named frontier-only exception.
2. **For the commercial appliance, prefer Apache 2.0 / MIT weights.** Llama's license restricts use above 700M MAU (irrelevant at your scale but a needless flag); some Chinese open-weight models carry custom licenses with jurisdiction-specific commercial restrictions. Permissive defaults mean the appliance never inherits a license headache. Apache/MIT among the below: Qwen family, Mistral, GLM-5.1, Qwen3-Embedding.

**Honcho benchmark data as a Project H design target (DECISIONS D25):** Honcho's published evals (mid-2026, LongMem S) show 90.4% accuracy using a **median 5% of available context per question** (mean 11%). Their pipeline: `gemini-2.5-flash-lite` for ingest-time extraction (fast, cheap, local-model candidate in your version) + `claude-haiku-4-5` for the chat/query endpoint. This is empirical evidence for two Project H targets: (a) ingest-time extraction is a bounded, fast task — test whether a local 7–9B model clears the bar before committing to a hosted call; (b) the memory query layer should target 5–10% context injection, not "dump everything in" — if your G's representations are pushing 50%+ of context, the consolidation quality is the problem, not the retrieval. These are measurable criteria for H's eval rubric, not guesses.

### LLMs — by node role

| Node role (examples) | Quality bar | June 2026 open-weight candidates | Realistic hardware | Notes |
|---|---|---|---|---|
| **Consolidation** (Project G dream-time `consolidation.j2`) | Frontier-only | **none — Claude only** | — | The asterisk on the privacy pitch. Never local. Honcho confirms: their deep consolidation uses claude-haiku-4-5; their ingest-time pass uses a small model (separate concerns). |
| **Ingest-time extraction** (Project G fast path — extract latent facts per message) | Low–mid; bounded task | Mistral Small 4, Phi-4-mini, smaller Qwen variants, gemini-2.5-flash-lite equivalent | 8–16GB VRAM | **Project H priority eval.** Honcho uses a fine-tuned small model here; test whether a local 7–9B clears the bar. If yes, ingest-time stays entirely local. |
| **Heavy reasoning / answer-gen** (D `AnswerNode`, NL memory query, open-ended synthesis) | Near-frontier | Qwen 3.6 Plus, DeepSeek V4, Kimi K2.6, GLM-5.1 | Beefy box / multi-GPU; not a 16GB laptop | Frontier-competitive on benchmarks; validate on *your* tasks. GLM-5.1 = MIT, good commercial fit. |
| **Mid-tier workhorse** (summarizer, blog draft, proposal writer) | Mid-cloud-API parity | 70B-class (Qwen, Llama 3.3 70B-class) at Q4 | 64–128GB unified memory *or* 32–48GB VRAM (single Mac Studio / one strong GPU) | This is the tier where local becomes "genuinely useful," competitive with mid-tier cloud APIs for most tasks. The SMB appliance's main workhorse. |
| **Cheap / narrow** (critics, classification, routing, episode-write summary) | Low — bounded transformations | Mistral Small 4, Gemma 4 31B, Phi-4-mini, smaller Qwen variants | 8–24GB VRAM / modest unified memory | The easy local wins H confirms first. Many of these are safe-local with near-zero quality loss because the task is narrow. |
| **Tool loop** (Project B) | n/a — learning exercise | raw `anthropic` SDK (Claude) | — | Not a routing target; B exists to feel the loop by hand. |

### Embedding models — local alternatives to Voyage

**Current default:** Voyage AI `voyage-2` (hosted, 1024 dims) — used for the first full run-through so everything works before optimizing (DECISIONS: keep Voyage as a legitimate standing option, not a compromise). The locals below are the down-the-road swaps evaluated in H. All slot into `EmbeddingService` as a config swap (Ollama-style), same as the LLMs.

| Model | Best at | Size / hardware | License | Notes for the Company Brain |
|---|---|---|---|---|
| **Qwen3-Embedding-8B** | Top-quality multilingual retrieval (incl. PT/EN cross-lingual) | ~16GB VRAM at F16; **~5GB at Q4_K_M** (RTX 4060 Ti / M1 Pro 16GB) | Apache 2.0 | **Recommended default local embedder.** #1 MTEB-multilingual (70.58, Jun 2025), 32K context, instruction-aware (a retrieval-prefix buys 1–5% recall). Quantized fit on modest hardware essentially closes the embedding asterisk on the privacy pitch. |
| **Qwen3-Embedding-4B** | Same family, lighter footprint | ~half the 8B resources | Apache 2.0 | ~67 MTEB. The pick when the client's hardware is mid-tier, not high-end. |
| **Qwen3-Embedding-0.6B** | Tiny-footprint deployments | Very small | Apache 2.0 | For the weakest hardware tier; quality drops accordingly — verify on real docs. |
| **BGE-M3** | Hybrid (dense + sparse/lexical) retrieval | up to 8192 tokens; mid VRAM | MIT-style permissive | **The pick when a corpus is acronym/SKU/policy-code-heavy** — sparse signal catches exact matches dense embeddings miss (common in SMB SOPs/catalogs). Most battle-tested in production. Per-language quality varies (unbalanced training data) — validate PT. |
| **Arctic Embed 2.0** | Lightweight multilingual | 568M params; small | Apache 2.0 | Multilingual with a smaller footprint than BGE-M3; Matryoshka reduction to 256 dims. Worth evaluating for small-hardware clients. |

**Retrieval-eval discipline (matters more than MTEB rank):** a model can ace topical similarity yet fail at surfacing the *one* passage with the right entities/constraints — which is exactly what RAG needs. Score on **recall@10** and **nDCG@10** against your own business-doc corpus, not the leaderboard. Note also: for RAG, retrieval quality often matters more than LLM size — a good local embedder + clean chunking + a smaller local LLM can beat a giant LLM with poor retrieval. This is *why* the privacy wedge holds (DECISIONS D19).

### Where this feeds the plan
- **Project H** is where these candidates get measured and the winners bake into per-node `model_provider` config (and the embedding choice into `EmbeddingService`).
- The resulting config is what differs between the **SMB shell** (local-heavy) and **enterprise shell** (cloud/private-endpoint) — same brain, different config (DECISIONS D16, D18).
- The **Rust appliance** surfaces, in plain numbers, which nodes ran local vs. hit Claude and what it cost — the legible version of "what stayed in the building" (DECISIONS D17).

## Portfolio / Interview Narrative (one line each)

| Project | Description |
|---|---|
| Infra + harness | "Production-ready event-driven AI pipeline infra with async queuing, plus a remote-triggered agentic dev harness on self-hosted hardware" |
| A: Content Pipeline | "Source-routed agentic pipeline that turns YouTube videos or articles into categorized, structured knowledge — a private self-hosted reading feed, with optional self-correcting blog drafts" |
| B: Research Agent | "Multi-step research agent with hand-built tool loop and self-correction across web sources" |
| C: Proposal Generator | "Domain agent that researches a company and produces scoped consulting proposals in PT and EN" |
| D: Document Q&A | "RAG system with session memory — answers from a company's own documents, tracks the conversation" |
| E: Specialized Pipeline | "Refactored multi-agent pipeline showing why specialized agents beat generalists" |
| F: Knowledge Base | "Semantic search over a growing corpus — meaning, not keywords" |
| G: Memory System | "Reasoning-first episodic→semantic memory with two-stage pipeline (ingest-time extraction + dream-time consolidation), multi-peer entity modeling, confidence decay, and contradiction handling — informed by Honcho's architecture, domain-tuned for organizational knowledge" |
| H: Eval & Routing Harness | "System that empirically routes each workflow node to the cheapest model meeting a measured quality bar — with bias-corrected evaluation" |
| Rust appliance shell | "Single-binary, on-prem control plane that runs a private AI knowledge system on a company's own hardware — nothing leaves the building" |
| **Company Brain** | **"A privacy-first company knowledge system: ingests a company's scattered knowledge, keeps it current with durable agent memory, emits executable skills for agents — running entirely on the company's own hardware, with measured local-vs-frontier routing"** |

## Red Flags to Watch For

- Hardcoding a system prompt in Python (use `.j2`).
- Not storing embeddings at write time (you'll regret it at Project F).
- Skipping the self-critic loop in Project A (it's the point).
- Using `AgentNode` in Project B (use raw SDK — earn the abstraction).
- Building the hardened Project B / any product idea / either shell before a real need exists.
- Shipping a workflow without its tests.
- Treating "one more project" as the thing standing between you and ready.
- **Building Project H as a runtime router instead of an offline eval tool** (DECISIONS D8).
- **Reaching for Rust where Python is sufficient** (DECISIONS D6). The appliance shell is the right Rust home; the brain is not.
- **(New) Writing `if running_locally:` inside a brain node** — the moment one product silently becomes two (DECISIONS D18). Deployment lives in config and the shell, never the brain.
- **(New) Letting the privacy pitch drift into absolutism** ("nothing ever leaves") — the consolidation step and (until proven otherwise) embeddings leave. Honest "local-by-default, frontier-for-the-named-few" is the defensible claim (DECISIONS D19).
- **(New) Building the Company Brain "product" ahead of the projects that compose it** — the brain is *assembled* from D/F/G/H, not invented separately. No revenue-free product-build sprints.

---

*Living reference. Update as projects complete and client work surfaces new patterns. The Socratic Tutor app and physics study live in separate, archived documents — this plan is about becoming an expert agentic/harness engineer and building the Company Brain from it.*

*Last updated: June 2026 — Company Brain framing + one-brain-two-shells architecture.*
