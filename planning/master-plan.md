---
type: Plan
title: Python Orchestration System — Master Plan
description: Phase sequence, full project library (A–H), Diagnostic relationship, standing rules, and links to brain for business/career context.
---

# Python Orchestration System — Master Plan

*What this project is, what it builds, and in what order. Business and career context live in the
company brain — links at the bottom.*

---

## What This Repo Builds

A production-grade Python agentic orchestration framework: event-driven, node-based workflow engine
with async task queue (FastAPI → Celery → Workflow DAG → TaskContext). Each phase adds a working
workflow on top of the shared framework — every workflow ships with tests.

Stack: FastAPI · Celery · Redis · PostgreSQL + pgvector · Voyage AI embeddings · Jinja2 prompts

---

## Phase Sequence

| Phase | Block / Project | Status |
|---|---|---|
| Phase 0 | Block A — presence + codebase ownership | Done |
| Phase 0 | Block B — Mac Mini harness (public face) | Done |
| Phase 0 | Block B — Mac Mini harness (private face / Tailscale) | In progress |
| Phase 0 | Block C — test infra + 4 bug fixes | Done |
| Phase 0 | Block D — shared services + Project A scaffold | Done |
| Phase 1 | Project A — content pipeline | Done |
| Phase 1 | Project B — research agent | Not started |
| Phase 1 | Project C — proposal generator | Not started |
| Phase 1 | Project D — document Q&A + RAG | Not started |
| — | Competence checkpoint after Project D | Pending |
| Phase 2 | Project E — specialization refactor | Not started |
| Phase 2 | Project F — semantic search | Not started |
| Phase 2 | Project H — model eval & routing harness | Not started |
| Phase 3 | Project G — agent memory system (Honcho reference architecture) | Not started |
| Parallel | Rust appliance shell (bastion) | Ongoing |

---

## Relationship to The Diagnostic

Projects B (research agent) and C (proposal generator) are the orchestrated implementation of
The Diagnostic Stage 1's two halves. Project B must produce output conforming to the intake
schema; Project C must produce output conforming to the deliverable template. See
`planning/diagnostic-alignment/notes.md` for the output schema constraints before speccing either.

Project D (document Q&A + RAG) gates the competence checkpoint independently of B+C.

---

## Shared Services

- **Brain corpus indexer** (`scripts/index_brain.py`) — crawls the company brain repo,
  chunks by section, embeds via Voyage AI, stores in `brain_documents` table. Run manually
  to refresh: `python scripts/index_brain.py [--brain-path ../agentic-portfolio]`.

---

## Technical Standing Rules

- **Every workflow ships with tests.** No exceptions. Per-project test requirements are in the Project Library below.
- **All prompts are Jinja2 `.j2` files** in `app/prompts/`, loaded via `PromptManager`. Never hardcode a system prompt in Python. *(D34)*
- **No deployment logic inside nodes.** This framework is deployment-agnostic. Model choice and persistence are injected via config, never hardcoded in a node. *(D33)*
- **Top-tier models first.** Introduce local/open-weight model swaps via Project H after measuring. *(D35)*

---

## Project Library

*Sequenced by sellable competence. Every project ships with tests. Projects D, F, G, H are the most differentiating.*

---

### Project A — Content Pipeline (YouTube/Article → Personal Digest + optional Blog)

**Pattern:** source-routed linear pipeline + self-correction loop, forking to two outputs.
**Reuse downstream:** `LearningArtifact` model, `SelfCriticNode → ReviseNode` pattern, voice prompt, `FetchArticleNode`.
**Status: Done.**

**End result:**
POST `{url, make_blog?}` to `/events/content`. Celery runs:
1. `SourceRouterNode` (RouterNode) — YouTube vs article → routes to the right fetch node
2a. `FetchTranscriptNode` — fetch + clean transcript
2b. `FetchArticleNode` — fetch URL + extract readable text (trafilatura default; Firecrawl fallback for JS-heavy pages)
3. `SummarizerNode` — structured JSON summary + classification (AgentNode, structured output)
4. `StorageNode` — `LearningArtifact` row **with embedding at write time** + static HTML digest page + regenerate category index
5. *(only if `make_blog`)* `BlogWriterNode → SelfCriticNode → ReviseNode` → write blog draft to disk

**Build notes:**
- `SummaryOutput` schema: title, category, tl_dr, read_time_estimate, core_concepts, key_insights, questions_raised, connections_to_my_work, further_exploration.
- `FetchArticleNode` is reused by any workflow that needs to ingest web-based knowledge.
- Self-critic loop stays linear (validator forbids cycles) — lives only on the blog branch.
- **Store embeddings at write time in `StorageNode` for every item**, digest-only included. This is what makes Projects F and G attach later.
- Voice prompt is a long-term asset; reused in Project C and external content.

**Tests ship with it:** `SourceRouterNode` routing (YouTube vs article, fallback/error), `FetchArticleNode` extraction (mock fetch; clean text out, graceful failure), `make_blog` branch (assert blog nodes run only when flagged), storage path (embedding written + HTML page + index regenerated), integration test both paths with agents mocked.

---

### Project B — Research Agent (thin first, then hardened)

**Pattern:** raw agentic tool loop + self-correction.
**Reuse downstream:** tool loop feeds Project C's `CompanyResearchNode`.

**Thin cut first — build this, stop here until a prospect needs more:**
A single `ToolUseNode` (raw `anthropic.Anthropic()` — write the `while stop_reason == "tool_use"` loop yourself). Input a company name; output a structured brief: what they do, where they likely bleed time, one automation hypothesis. **No Celery, no critic, no storage. ~50 lines.**

The `max_iterations` guard on `ToolUseNode` is not optional — it terminates the loop on runaway tool calls.

**Hardened version (only when a real prospect makes you want more):**
1. `PlannerNode` (AgentNode) — research plan
2. `ResearchNode` (ToolUseNode) — `web_search` + source tools
3. `CriticNode` (AgentNode) — gaps, unsupported claims
4. `ReviseNode` (AgentNode)
5. `StorageNode` — `LearningArtifact` + embedding

**Build notes:**
- This is the one project where you bypass `AgentNode`. Feel the raw tool loop. After this, you've earned the abstraction.
- Tavily over raw search APIs — built for agents.
- See `planning/diagnostic-alignment/notes.md` for output schema constraints (Project B output must conform to intake schema).

**Tests ship with it:** tool loop with mocked client (assert injects results, terminates on `end_turn` and on `max_iterations`), plus node tests for the hardened version.

---

### Project C — Client Proposal Generator

**Pattern:** research → structured output → review/revise with routing.

**End result:**
Input: company name, industry, brief description.
1. `CompanyResearchNode` (ToolUseNode from Project B — first real reuse)
2. `OpportunityIdentifierNode` (AgentNode) — 3 opportunities with scores
3. `OpportunityRouterNode` (RouterNode) — picks the highest-value one
4. `ProposalWriterNode` (AgentNode) — scoped proposal in PT and EN
5. `ProposalReviewNode` (AgentNode) — validates against explicit criteria
6. `ReviseNode` — addresses feedback if needed
7. `StorageNode`

**Build notes:**
- `Opportunity` schema: name, problem_statement, proposed_solution, estimated_value, build_complexity, fit_score. `OpportunitiesOutput`: opportunities, recommended, rationale.
- **Review criteria:** names client ≥3×? exactly one specific testable deliverable? realistic timeline (4–8 wks first project)? avoids vague language? investment matches complexity? Each PASS/FAIL with a line reference; router sends to `ReviseNode` on "revise", to `StorageNode` on "pass".
- One recommendation, not three.
- See `planning/diagnostic-alignment/notes.md` for output schema constraints (Project C output must conform to deliverable template).

**Tests ship with it:** node tests (mocked agents), router's pass/revise branching, structured-output schema validation.

---

### Project D — Document Q&A + Session Memory (RAG)

**Pattern:** full RAG + session memory.
**Reuse downstream:** `RetrieveChunksNode` (verbatim later), `ContentChunk` + `ChatSession` models.

**End result:**
- **Ingestion** (`/events/ingest_document`): `ParseDocumentNode → ChunkDocumentNode → EmbedChunksNode → StoreChunksNode`
- **Query** (`/events/query`): `EmbedQuestionNode → RetrieveChunksNode → AssembleContextNode → AnswerNode → UpdateSessionMemoryNode`

**Build notes:**
- Models: `ContentChunk(doc_id, position, section_title, content, embedding)`, `ChatSession(doc_id, turns JSONB, topics_covered, timestamps)`.
- **Build `RetrieveChunksNode` carefully** — it's reused verbatim downstream.
- **Implement two-stage hybrid retrieval in `RetrieveChunksNode`:** semantic vector search narrows candidates; keyword re-rank fuses signals. Beats pure cosine on business document queries (exact terminology, SKUs, policy language). **Reference:** `rag-engine-rs/src/services/search/two_stage_retrieval.rs` — a working Rust implementation of this exact pattern using pgvector + keyword re-rank. Python port uses Voyage embeddings, but the retrieval logic is identical and proven on real help-center documents.
- Chunk size: 500 tokens / 50 overlap starting point; tune on a real business doc.
- RAG retrieves from the document; session memory tracks the conversation. Both assembled together in `AssembleContextNode`.
- Note which nodes are local-friendly vs. frontier-dependent as input to Project H.

**Tests ship with it:** retrieval correctness (mock embeddings, assert ordering), RAG-vs-session-memory assembly, ingestion chunking boundaries.

**Competence checkpoint after Project D:** can walk into an unfamiliar SMB and name 3 automatable workflows in 30 min, explain how to build each, scope a bounded engagement. If yes → ready for a paid diagnostic. If no → name exactly what's missing.

---

### Project E — Specialization Refactor

**Pattern:** specialized nodes + parallelism. Kept separate from Project A on purpose — you build the naive pipeline first, feel its limits, then refactor and watch quality change.

**The refactor:**
- **Before:** `Fetch → Summarizer → BlogWriter → SelfCritic → Revise → Storage`
- **After:** `Fetch → [ConceptExtractorNode ‖ StructureAnalystNode] → BlogDraftNode → VoiceMatchNode → SelfCritic → Revise → Storage`

**Build notes:**
- **Fix the `ParallelNode` merge gap here** (each parallel node writes a uniquely keyed slot; merge after). This is the first genuine need for parallelism.
- Run the same video through old and new pipelines; compare. The quality delta is the lesson.
- Write the comparison — strong portfolio content.

**Tests ship with it:** parallel merge (assert both slots present and correctly combined), new specialized nodes.

---

### Project F — Semantic Search Over Your Corpus

**Pattern:** semantic retrieval at corpus scale. Mostly Project D components. Payoff for storing embeddings at write time since Project A.

**End result:**
`GET /knowledge/search?q=...` returns top-3 relevant `LearningArtifact`s with excerpts and source URLs; optional synthesis (a single `AgentNode` consolidating top-k into one answer).

**Build notes:**
- Prove semantic (not keyword) retrieval: search "agents communicating" and confirm results tagged "multi-agent orchestration."
- Practical use: before each study session, query what you've learned about a topic.

**Tests ship with it:** ranking/ordering with mocked embeddings; synthesis node with mocked agent.

---

### Project G — Agent Memory System (Episodic → Semantic)

**Pattern:** episodic→semantic consolidation, confidence decay, contradiction handling, multi-peer entity modeling.
**Reuse downstream:** `MemoryLoaderNode` (verbatim), the whole module.

**Before you build: read Honcho's source code.** Honcho (Plastic Labs, open-source) is the best available reference implementation of reasoning-first agent memory. Their FastAPI server, Postgres schema, and Celery worker setup are directly instructive — same stack. What to adopt:
- **Two-stage pipeline.** Ingest-time: fast model captures latent facts per message immediately. Dream-time (Celery, nightly): deeper reasoning across prior episodes and representations. Your Celery infrastructure already supports this split.
- **Multi-peer entity model.** Any entity that persists and changes over time: a user, a company, a client, a product, an SOP. For organizational knowledge this is the right abstraction.
- **Natural-language query interface.** Load relevant representations via a NL question, not just cosine similarity.

**End result — a memory module attachable to any workflow:**
1. **Ingest-time extraction** (after each interaction turn): fast extraction — what happened, what was learned, what was contradicted. Updates the relevant peer's representation immediately. Local-model candidate.
2. **Dream-time consolidation job** (Celery, session-end + nightly): deeper reasoning across recent episodes and prior representations. Extracts durable facts, resolves contradictions, updates confidence. **This step stays on Claude — never local.**
3. **Memory loader** (session start): loads top-k relevant representations via natural-language query.

**Models (multi-peer):**
```
Peer(peer_id, peer_type, workspace_id, representation, updated_at)
AgentEpisode(peer_id, session_id, summary, outcome, tags, embedding, occurred_at)
SemanticMemory(peer_id, fact, confidence, evidence_episode_ids, decay_factor, source_peer_id, timestamps, embedding)
```

**Build notes:**
- **Confidence decay is not optional:** `new = confidence * decay_factor ** weeks_elapsed`, run in `UpsertMemoryNode`.
- **Contradictions expected:** lower confidence on the contradicted fact, create a new one. Never overwrite.
- **Ingest-time extraction is a local-model candidate** — evaluate in Project H.
- **Dream-time consolidation must stay on Claude.** Weak models produce confident-but-wrong durable facts that silently corrupt everything downstream. *(D35 named frontier-only exception)*
- Build as a standalone importable module — `MemoryLoaderNode`, `EpisodeWriteService`, `IngestTimeExtractionNode`, `ConsolidationWorkflow`, no coupling to any one workflow.
- **Target 5–10% context injection per query** (Honcho benchmark: 90.4% accuracy at median 5% context). If representations push 50%+ of context, consolidation quality is the problem.

**Tests ship with it — test harder than anything else in the plan:** consolidation output schema validity (per peer, multi-peer case); decay function (`freezegun` to advance weeks, assert `confidence * 0.95**weeks`); contradiction handling (old-fact confidence drops, new fact created, no overwrite); multi-peer isolation (peer A's facts don't bleed into peer B); ingest-time extraction (fast path produces valid summary and episode write); `MemoryLoaderNode` retrieval ordering (both cosine and NL query modes). Bad memory output is the trust-eroding silent failure.

---

### Project H — Model Evaluation & Routing Harness

**Pattern:** offline evaluation; empirical model routing.
**Output:** per-node routing config file the brain loads at startup — different config for local-heavy vs. cloud deployments.

**Critical design principle: offline eval, not runtime router.** This runs occasionally and deliberately to *produce* routing decisions ("node X is safe on local-70B"). Those decisions bake into the node's `model_provider` config at design time. Not per-request runtime model selection. *(D33 / D8 orchestrator)*

**What it does:**
For a given node, run 30–50 representative inputs through several models — frontier reference (Claude Opus), mid local (70B-class), small local (7–9B) — score each output, produce a per-node table: quality retention vs. cost.

**Scoring strategy by node type:**
- **Deterministic / structural** (structured-output nodes, consolidation): valid schema? required fields? values in range?
- **Reference-based** (extraction tasks): compare extracted facts against a hand-labeled set.
- **LLM-as-judge** (open-ended prose): frontier model scores candidates against a rubric. **Score blind, randomize order, use specific criteria.** Correcting for judge bias is itself a senior signal.

**Also evaluate:** local embedding options (retrieval quality with local vs Voyage embeddings on a real business-doc corpus).

**Tests ship with it:** scoring functions (deterministic scorers against known-good/known-bad outputs); blind/randomized judge harness (assert strips model identity and randomizes order); results persistence.

---

### Rust Appliance Shell

Moved to `bastion` — see `agentic-portfolio/docs/projects/bastion.md` and `bastion/planning/master-plan.md`. The Rust shell commands and observes the Python brain over HTTP; the two never share code. Rust stays Rust; Python stays Python. *(D33, D35)*

---

## Strategy & Career Context

Business goals, contracting strategy, leads, and career posture live in the company brain:

- Career strategy: `agentic-portfolio/docs/career.md`
- Content plan: `agentic-portfolio/docs/content/ideas.md`
- Lead pipeline: `agentic-portfolio/docs/business/pipeline.md`
- The Diagnostic productized service: `agentic-portfolio/planning/the-diagnostic/plan.md`

---

*Last updated: June 2026. For the previous version's strategic arc, see `docs/career.md` in the brain.*
