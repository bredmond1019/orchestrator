---
type: Plan
title: Python Orchestration System — Master Plan
description: Phase sequence, full project library (A–H), this repo's role as Bastion's Engine + Python-half-of-Brain, the program-block crosswalk, the Diagnostic relationship, and standing rules.
doc_id: master-plan
layer: [engine, brain]
project: orchestrator
status: active
keywords: [master plan, phase sequence, project library, Bastion Engine, program blocks]
related: [context, status, D36-bastion-engine-brain-role]
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

## Role in Bastion (the primary program)

This repo is **two of Bastion's five layers**: the **Engine** (where the LLM/agent workflows run) and
the **Python half of the Brain** (`brain-rag` — semantic retrieval, indexing, the memory/entity
store). Bastion is the brain's now-primary program — the five-layer practice OS (Brain · Engine ·
Factory · Console · Surfaces) — sequenced **demand-first**. The cross-repo program plan, its block
order, and the seams between repos are authoritative in the **brain**, not here:

- Program roadmap + demand-first wave table — `agentic-portfolio/planning/bastion-product/master-plan.md`
- Naming + layer-ownership rule — `agentic-portfolio/planning/bastion-product/ownership.md`
- System architecture — `agentic-portfolio/planning/bastion-product/architecture.md`
- Governing decisions — brain **D24** (Python/Rust seam), **D25** (read-only state, triggered
  mutations), **D26** (Bastion-the-system naming, demand-first, F≡B unification, MCP server/client
  split, code-aware Brain, memory as a Brain capability). Adopted locally as **D36**.

**The seam (brain D24).** Python owns where the LLM/embedding ecosystem lives — agent loops,
embeddings, RAG, prompt iteration. **Every client deliverable ships as a Python workflow here.** Rust
(the Console, `bastion`) owns deployment, validation, protocol, and structure, and *harvests* tested
crates from `workflow-engine-rs` / `claude-sdk-rs`. The two never share code; Rust never holds the
billable work. This is the long-standing "Python stays Python" rule (D6/D33), now stated as a layer
boundary.

**What that means for this plan.** The project library (A–H) below is unchanged in identity — it is
still how this repo's work is numbered and referenced across `status.md`, `decisions/`, and
`CLAUDE.md`. Two reframings and a set of new Brain-side blocks land on top of it (brain D26 / local
D36):

- **Project F ≡ the Brain semantic layer** (brain-program **Block B**) — semantic search over the
  corpus *is* the Brain's semantic retrieval; the two are one thing now, not a late Phase-2 extra.
- **Project G ≡ the Brain's memory/entity capability** (brain-program **Block S**) — clients,
  companies, products, and SOPs become first-class **entities**; the memory store is Brain data.
- **Project H ≡ the Eval + success-metrics engine** (brain-program **Block U**) — model eval & routing
  is elevated from a floating wave-table row to a *named capability track* (Self-Improvement); it is the
  engine that *licenses* autonomy promotion (Block X) and feeds the Console metrics surface (Block V).
- **New Brain-side blocks** (O, J, C, P, L, R), the **Python half of cost-control** (I), and the three
  north-star tracks this repo now owns — **U** (eval/metrics, above), **W** (external-intelligence loop +
  external-knowledge memory), and **Z** (`sdlc-flow`/`sdlc-run` graduated into orchestrator-native
  nodes & workflows — the Coding & Delivery harness becoming Engine-native) — are specified in the
  [Bastion Program Blocks](#bastion-program-blocks-engine--brain) section, in the brain's block-contract
  format.

### Program-block crosswalk

How the brain's program blocks map to this repo's work and the **demand-first wave** they sit in
(authoritative order lives in the brain wave table — this is the legibility bridge, not a second
source of truth). Project H is now elevated to **Block U**; Project E is **pulled forward to Wave 2**
as the hard prerequisite for **Block Z** (the wave fan-out needs the `ParallelNode` merge fix). The
three north-star tracks this repo owns — **U** (eval/metrics), **W** (external-intelligence), **Z**
(sdlc-as-nodes) — are detailed in the block-contract section below.

| Brain block | Wave | Orchestrator work (this repo) | Status |
|---|---|---|---|
| **T** | 0 | Enriched OKF frontmatter — `index_brain.py` parse/strip/enrich, `BrainDocument` columns + migration, retrieval keyword-boost + filters (**gates B**) | Not started |
| **B** | 0 | Semantic Brain over the company-brain corpus — populate the store, confirm `"brain"`-corpus Q&A (**absorbs Project F**) | Not started (retrieval shipped in Project D; population pending; now gated by T) |
| **O** | 0 | Widen the index corpus to all sub-repo `planning/` + `CLAUDE.md` | Not started |
| **J** | 0 | Brain freshness loop — auto-reindex on commit (with the brain repo) | Not started |
| **C** | 1 | Multi-workspace Brain — per-repo / per-client corpora (**Python half**; bastion does the graph-reader half) | Not started |
| **P** | 1 | Semantic code search — source as a corpus | Not started |
| **I** | 2 | Cost control **Python half** — abort endpoint + server-side budget gate (bastion drives the CLI half) | Not started |
| **S** | 3 | Entity / memory layer — clients as first-class entities (**Project G reframed**) | Not started |
| **L** | 3 | Answer-time grounding — citation verify + abstain (**Project D hardening**) | Not started |
| **R** | 4 | Brain-as-MCP-server — Python **server** half of the MCP split | Not started |
| **Z** | 2 | **`sdlc-flow`/`sdlc-run` → orchestrator-native nodes & workflows** (HL2 graduation into the Engine) | Not started |
| **U** | 4 | Eval + success-metrics engine (**absorbs Project H** — model eval & routing) | Not started |
| **W** | 5 ✲ | External-intelligence loop + external-knowledge memory | Not started |
| **MV.3B.S** | 5 | Graph-aware RAG — ingest Cortex/mev graph edges; two-stage structural+semantic retrieval (mev-numbered, **orchestrator-owned**) | Not started |
| — (Project **E**) | 2 | ParallelNode merge fix (Project E core) — **pulled forward as Block Z's prerequisite** | Not started |

---

## North-Star Alignment (umbrella view)

> **Added 2026-06-27 (north-star Thread 2c).** The cross-repo program master-plan was reorganized around
> the north star into
> **7 capability tracks** (see `agentic-portfolio/planning/bastion-product/master-plan.md`). This section
> maps **this repo's phases/projects onto those tracks** so the two plans read as one — **nothing here is
> removed or renumbered**; the A–H project numbering is load-bearing (referenced across `status.md`,
> `decisions/`, `CLAUDE.md`) and stays exactly as is. This is the *capability lens* over it, plus the
> three new program tracks the orchestrator now owns. (Worked reference: `bastion/planning/master-plan.md`
> Thread 2b.)

**orchestrator phase / project → program capability track:**

| This repo's work | Program capability track | What the orchestrator owns in it |
|---|---|---|
| `brain-rag` + Projects D/F → Blocks B, O, C, P, L, R, S | **Track 1 — Brain: Context & Memory** | the Python half of the Brain — semantic retrieval, corpus widening, multi-workspace, code search, MCP server, entity/memory store |
| Project D answer-path → Block L; freshness → Block J | **Track 3 — Verification & Brain Integrity** | answer-time grounding (citation verify + abstain); the cron freshness loop |
| cost-control Python half → Block I | **Track 2 — Console: Observe, Cost & Control** | the *enforcement* point — abort endpoint + server-side budget gate the Console triggers (D25) |
| **Project H → Block U** ; **new Block W** | **Track 4 — Self-Improvement & Self-Healing** | the eval + success-metrics engine (elevated Project H) and the external-intelligence loop + external-knowledge memory |
| orchestrator half of Block X | **Track 5 — Governance & Autonomy** | dispatch-time enforcement of the trust ladder (the Engine runs the mutation, D25) |
| **new Block Z** (HL2 graduation) ; HL3/HL4 substrate | **Track 6 — The Harness Library** | `sdlc-flow`/`sdlc-run` graduated into Engine-native nodes/workflows (HL2); the `research_agent` (HL3) + `document_*` (HL4) substrate |
| Block G (loop-proof) | **Track 7 — The Loop-Proof** | the Engine runs the agentic workflows the narrated proof exercises |

**In-flight vs queued (this repo's program-track slice — authoritative status in `status.md`):**
- **🟢 Done (substrate):** Project D (RAG retrieval) · `brain-rag` Layer 1–2 · the frontmatter
  indexer/retrieval infra (Block T orchestrator half) · the Claude Code SDK + session providers (the
  seam Block Z builds on).
- **🟡 In flight:** Block B (semantic Brain — next up; the local-embedding `--rebuild`) · the private
  Tailscale face (Wave 0 infra).
- **⚪ Queued:** O · J · C (Python half) · P · I (Python half) · L · R · S · **U** (eval engine) ·
  **W** (external-intel) · **Z** (sdlc-as-nodes) · Project E (ParallelNode merge — pulled to Wave 2 for Z).

**The north-star tracks the orchestrator owns** (the LLM/embedding-ecosystem side of the D24 seam): the
whole Python half of the **Brain** (Track 1), the **answer-side** verification (Track 3), the cost-control
**enforcement** point (Track 2), and — **new from the umbrella reorg** — the **eval + success-metrics
engine** (Block U, elevating Project H), the **external-intelligence loop** (Block W), and the
**graduation of the Coding & Delivery harness into Engine-native nodes & workflows** (Block Z). The
Console-side blocks (the graph layer, exact cost, the kill-switch CLI, the MCP client, the trust
registry surface) stay in `bastion`; the brain umbrella owns the cross-repo order.

---

## Phase Sequence

*Status mirrors `status.md` (the source of truth). The demand-first wave order above re-sequences
**when** the post-checkpoint work happens; the phase numbering below is preserved for continuity of
reference.*

| Phase | Block / Project | Status |
|---|---|---|
| Phase 0 | Block A — presence + codebase ownership | In progress (agent-executable parts done; personal tasks deferred) |
| Phase 0 | Block B — Mac Mini harness (public face) | Done |
| Phase 0 | Block B — Mac Mini harness (private face / Tailscale) | In progress (Wave 0 #1) |
| Phase 0 | Block C — test infra + 4 bug fixes | Done |
| Phase 0 | Block D — shared services + Project A scaffold | Done |
| Phase 1 | Project A — content pipeline | Done |
| Phase 1 | Project B — research agent (thin cut) | Done |
| Phase 1 | Project C — proposal generator | Done |
| Phase 1 | Project D — document Q&A + RAG | Done |
| — | Competence checkpoint after Project D | **Passed (2026-06-23)** |
| Supporting | brain-rag Layer 1 (BrainDocument + index_brain.py) | Done |
| Supporting | expose-api-and-telegram-bot (API key auth, CORS, Telegram bot) | Done |
| Phase 2 | Project E — specialization refactor (ParallelNode merge) | Not started (**brain Wave 2** — pulled forward as Block Z's prerequisite) |
| Phase 2 | Project F — semantic search → **the Brain semantic layer (Block B)** | Not started (brain Wave 0) |
| Phase 2 | Project H — model eval & routing → **the Eval + success-metrics engine (Block U)** | Not started (brain Wave 4) |
| Phase 3 | Project G — agent memory → **the Brain memory/entity capability (Block S)** | Not started (brain Wave 3) |
| Bastion | Brain-side blocks O, J, C, P, L, R + cost-control I (Python half) | Not started (see crosswalk) |
| Bastion | **Block Z** — sdlc-as-nodes (HL2 graduation) + **Block U** (eval engine) + **Block W** (external-intel) | Not started (see crosswalk; Z = Wave 2, U = Wave 4, W = Wave 5 ✲) |
| Parallel | Console — `bastion` (Rust) | Ongoing |

---

## Relationship to The Diagnostic

Projects B (research agent) and C (proposal generator) are the orchestrated implementation of
The Diagnostic Stage 1's two halves. Project B must produce output conforming to the intake
schema; Project C must produce output conforming to the deliverable template. See
`planning/diagnostic-alignment/notes.md` for the output schema constraints before speccing either.

Project D (document Q&A + RAG) gated the competence checkpoint independently of B+C — **passed
2026-06-23**.

---

## Shared Services

- **Brain corpus indexer** (`scripts/index_brain.py`) — crawls the company brain repo,
  chunks by section, embeds via Voyage AI, stores in `brain_documents` table. Run manually
  to refresh: `python scripts/index_brain.py [--brain-path ../agentic-portfolio]`.
  This is the **Python half of the Brain layer** (`brain-rag`): Layer 1 (model + indexer) shipped;
  Layer 2 (corpus-dispatch retrieval) shipped with Project D; Layer 3 (MCP exposure) is **Block R**.
  Brain-program **Block B** populates its vector store; **Block O** widens its corpus to every
  sub-repo's docs; **Block J** makes the manual refresh automatic (reindex on commit).

---

## Technical Standing Rules

- **Every workflow ships with tests.** No exceptions. Per-project test requirements are in the Project Library below.
- **All prompts are Jinja2 `.j2` files** in `app/prompts/`, loaded via `PromptManager`. Never hardcode a system prompt in Python. *(D34)*
- **No deployment logic inside nodes.** This framework is deployment-agnostic. Model choice and persistence are injected via config, never hardcoded in a node. *(D33)*
- **Top-tier models first.** Introduce local/open-weight model swaps via Project H after measuring. *(D35)*
- **Python stays Python; Rust is the Console.** This repo is the Engine + Python-half-of-Brain. Rust
  (bastion) is a *separate* layer that harvests crates and reads this repo over HTTP/Postgres — never a
  rewrite of any part of this core. *(D6 / D33 / D36; brain D24)*
- **The Console is read-only for state; this repo performs the mutations.** Kill switches and
  self-healing PRs are *triggered* by bastion but *executed* here (the abort endpoint, the budget
  gate) or by the Factory. Agents propose via PR; humans approve the gates. *(D20 / D36; brain D25)*

---

## Project Library

*Sequenced by sellable competence. Every project ships with tests. Projects D, F, G, H are the most differentiating.*

---

### OR.1.A — Content Pipeline (YouTube/Article → Personal Digest + optional Blog)

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

### OR.1.B — Research Agent (thin first, then hardened)

**Pattern:** raw agentic tool loop + self-correction.
**Reuse downstream:** tool loop feeds Project C's `CompanyResearchNode`.
**Status: Done (thin cut). Hardened version deferred until a real prospect demands it.**

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

### OR.1.C — Client Proposal Generator

**Pattern:** research → structured output → review/revise with routing.
**Status: Done.**

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

### OR.1.D — Document Q&A + Session Memory (RAG)

**Pattern:** full RAG + session memory.
**Reuse downstream:** `RetrieveChunksNode` (verbatim later), `ContentChunk` + `ChatSession` models.
**Status: Done. Competence checkpoint passed 2026-06-23.**

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
- **Layer 2 of the Brain (brain-rag):** `RetrieveChunksNode` carries a `corpus` dispatch param so the
  same retrieval serves the document Q&A *and* the `"brain"` corpus. Answer-time grounding (citation
  verify + abstain) is hardened later as **Block L**.

**Tests ship with it:** retrieval correctness (mock embeddings, assert ordering), RAG-vs-session-memory assembly, ingestion chunking boundaries.

**Competence checkpoint after Project D — PASSED (2026-06-23):** can walk into an unfamiliar SMB and name 3 automatable workflows in 30 min, explain how to build each, scope a bounded engagement.

---

### OR.1.E — Specialization Refactor

**Pattern:** specialized nodes + parallelism. Kept separate from Project A on purpose — you build the naive pipeline first, feel its limits, then refactor and watch quality change.
**Bastion wave:** **Wave 2 — pulled forward as [OR.Z](#or-z--sdlc-flowsdlc-run--orchestrator-native-nodes--workflows-hl2-graduation)'s hard prerequisite** (the SDLC wave fan-out needs the `ParallelNode` merge fix). Was Wave 4 ✲; Block Z is the genuine parallelism need that pulls it in.

**The refactor:**
- **Before:** `Fetch → Summarizer → BlogWriter → SelfCritic → Revise → Storage`
- **After:** `Fetch → [ConceptExtractorNode ‖ StructureAnalystNode] → BlogDraftNode → VoiceMatchNode → SelfCritic → Revise → Storage`

**Build notes:**
- **Fix the `ParallelNode` merge gap here** (each parallel node writes a uniquely keyed slot; merge after). This is the first genuine need for parallelism.
- Run the same video through old and new pipelines; compare. The quality delta is the lesson.
- Write the comparison — strong portfolio content.

**Tests ship with it:** parallel merge (assert both slots present and correctly combined), new specialized nodes.

---

### OR.1.F — Semantic Search Over Your Corpus → the Brain semantic layer

> **Reframed (brain D26 / local D36): Project F ≡ brain-program Block B (the Brain semantic layer).**
> "Semantic search over the corpus" and "the Brain answers semantically" are the same capability; F
> is no longer a standalone Phase-2 extra but the **Wave 0** semantic-retrieval half of the Brain. The
> endpoint below still describes its public surface; the cross-repo framing, dependencies, and
> acceptance live in [OR.B](#or-b--semantic-brain-over-the-company-brain-corpus-absorbs-project-f).

**Pattern:** semantic retrieval at corpus scale. Mostly Project D components. Payoff for storing embeddings at write time since Project A.

**End result:**
`GET /knowledge/search?q=...` returns top-3 relevant `LearningArtifact`s with excerpts and source URLs; optional synthesis (a single `AgentNode` consolidating top-k into one answer).

**Build notes:**
- Prove semantic (not keyword) retrieval: search "agents communicating" and confirm results tagged "multi-agent orchestration."
- Practical use: before each study session, query what you've learned about a topic.
- The same retrieval, pointed at the `"brain"` corpus, *is* the Brain semantic layer (Block B).

**Tests ship with it:** ranking/ordering with mocked embeddings; synthesis node with mocked agent.

---

### OR.1.G — Agent Memory System (Episodic → Semantic) → the Brain memory/entity capability

> **Reframed (brain D26 / local D36): Project G ≡ brain-program Block S (the Brain's memory
> capability).** The store is **Brain data**; the workflows (ingest-time extraction, dream-time
> consolidation) are **Engine**; the Console reads it. The reframing makes **clients, companies,
> products, and SOPs first-class entities** so the Brain answers *"what's the status with client X,
> what rate did I quote."* All build detail below stands; the cross-repo entity framing, dependencies,
> and acceptance live in [OR.S](#or-s--entity--memory-layer-project-g-reframed).

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
- **`workspace_id` is the multi-workspace seam (Block C):** entities are scoped per workspace (per-repo, per-client), so the memory layer and the corpus layer share the same addressing.

**Tests ship with it — test harder than anything else in the plan:** consolidation output schema validity (per peer, multi-peer case); decay function (`freezegun` to advance weeks, assert `confidence * 0.95**weeks`); contradiction handling (old-fact confidence drops, new fact created, no overwrite); multi-peer isolation (peer A's facts don't bleed into peer B); ingest-time extraction (fast path produces valid summary and episode write); `MemoryLoaderNode` retrieval ordering (both cosine and NL query modes). Bad memory output is the trust-eroding silent failure.

---

### OR.1.H — Model Evaluation & Routing Harness

> **Reframed (north-star Thread 2c): Project H ≡ brain-program Block U (the Eval + success-metrics
> engine).** Model eval & routing is elevated from a floating wave-table row to the **named
> Self-Improvement track** — the engine that licenses autonomy promotion (Block X) and feeds the Console
> metrics surface (Block V). All build detail below stands as the seed; the cross-repo framing,
> dependencies, and acceptance live in [OR.U](#or-u--eval--success-metrics-engine-elevates-project-h).

**Pattern:** offline evaluation; empirical model routing.
**Output:** per-node routing config file the brain loads at startup — different config for local-heavy vs. cloud deployments.
**Bastion wave:** Wave 4 (volume/economics-driven — build when run volume makes cost optimization pay).

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

## Bastion Program Blocks (Engine + Brain)

The Brain-side and cost-control work this repo owns in the Bastion program, written in the brain's
**block-contract** format (`/generate-master-plan` skeleton: What · Why · Repo · Interfaces · Depends
on · Out of scope · Acceptance criteria). These are executed *here* — open Claude Code in this repo and
run `/generate-master-plan` → `/generate-tasks` → `/sdlc-flow` (or `/sdlc-block`). The cross-repo
order is the brain's demand-first wave table; the per-block detail is canonical there and mirrored
here so this repo is self-sufficient to execute against. "Brain-program Block X" = the same X in
`bastion-product/master-plan.md` (distinct from this repo's Phase 0 Blocks A–D).

---

### OR.T — Enriched OKF frontmatter (orchestrator half: indexer + model + retrieval)

- **What:** Make `scripts/index_brain.py` parse frontmatter (reuse `python-frontmatter`), **strip** the
  YAML from the embedded body, and bake a compact metadata context-prefix (`project`/`layer`/`type`/
  `keywords`) into each chunk's embed-text while storing clean `content`. Add six nullable columns to
  `BrainDocument` (`doc_id`, `layer`, `project`, `status`, `keywords`, `related`) + an Alembic migration.
  Extend `retrieve_chunks_node` so the `"brain"` corpus keyword re-rank also matches `keywords` and an
  optional `filters` arg scopes by `layer`/`project`/`status` (the `"content"` corpus is unchanged).
- **Why:** Wave 0 — **gates Block B**. The first embedding `--rebuild` must run over enriched,
  frontmatter-stripped docs, or the vectors are polluted (raw YAML) and under-enriched, and the Voyage
  cost is paid twice. The schema is the shared contract the Console's graph layer also reads.
- **Repo:** orchestrator (this half) + the brain repo (the schema decision D27,
  `docs/okf-frontmatter.md`, and the full doc backfill).
- **Interfaces / contracts:** Consumes the frontmatter schema (brain D27); consumes the existing
  `BrainDocument` model + corpus-dispatch contract. Produces the populated columns + enriched vectors the
  retrieval path and the bastion graph layer read. No data-contract version bump (read path).
- **Depends on:** The schema being settled (brain D27). Ship the model + migration + indexer atomically so
  no write references a missing column.
- **Out of scope:** The backfill of brain docs (brain repo). Running the embedding pass (that *is* Block
  B). Code-corpus metadata (Block P). mev validation (future consumer).
- **Acceptance criteria:** a fixture doc with frontmatter indexes with no raw YAML in `content`; text sent
  to `embed_batch` starts with the prefix while stored `content` does not; the six columns populate on
  insert and docs *without* the fields still index (defaults); `alembic upgrade head` applies; a `keywords`
  hit earns the re-rank boost and `filters` scopes results; the `"content"` corpus path is unchanged; gate
  holds (`uv run python -m pytest`, `ruff`, `pylint app/` 10.00/10).

---

### OR.B — Semantic Brain over the company-brain corpus (absorbs Project F)

- **What:** Run `index_brain.py` to populate the pgvector store over the OKF brain corpus, and confirm
  end-to-end semantic Q&A over the `"brain"` corpus through the existing two-stage hybrid retrieval
  (Project D's `RetrieveChunksNode` with corpus dispatch). This is the work the old Project F named,
  unified with the Brain's semantic layer (D26 F≡B).
- **Why:** Wave 0 — the Brain must answer semantically end-to-end before structural+semantic can be
  combined (bastion's graph layer) and before portability (Block C) generalizes the readers. The RAG
  machinery already exists (Project D); this is population + verification, not new retrieval code.
- **Repo:** orchestrator (`brain-rag` + Project D retrieval).
- **Interfaces / contracts:** Consumes the `BrainDocument` model + the `"brain"` corpus-dispatch
  contract already defined here. Produces a populated vector store the Console (`bastion`) and agents
  query. No data-contract version bump (read path only).
- **Depends on:** Block T (enriched frontmatter must land first so the one-time `--rebuild` embeds
  enriched, frontmatter-stripped docs). Project D already shipped the retrieval; runs in parallel with
  bastion's `knowledge_graph` block (graph reads files; this reads/writes Postgres).
- **Out of scope:** MCP exposure of the Brain (Block R). Brain portability / multi-workspace (Block C).
  Any change to the retrieval algorithm. Answer-time grounding (Block L). Graph-edge ingestion /
  structural retrieval (Block MV.3B.S).
- **Acceptance criteria:** `index_brain.py` populates the store over the live brain corpus; a known
  brain question returns a correctly cited answer over the `"brain"` corpus; the orchestrator gate
  holds (`uv run python -m pytest` all pass, `ruff` clean, `pylint app/` 10.00/10); a brain-corpus
  retrieval smoke test passes.

---

### MV.3B.S — Graph-aware RAG (edge ingestion; mev-numbered, orchestrator-owned)

- **What:** Ingest Cortex/mev's emitted graph (`mev emit-graph` — nodes/edges/leaves JSON, shipped in
  mev MV.3B.R) into the Brain store, and extend the `"brain"` retrieval path to **two-stage
  retrieval**: a structural stage expands the candidate set through the `related:`/link neighborhood
  of the top semantic hits, then the existing semantic + keyword re-rank orders the union. Persist the
  edges Postgres-side (a `brain_edges` table or equivalent keyed by `doc_id`, loaded from the emit-graph
  payload — the `BrainDocument.related` column from Block T holds the raw list; this block makes it
  traversable and pays it rent at query time).
- **Why:** Wave 5 — the second half of Dual-Graph Memory. The brain corpus's link structure (OKF
  `related:` edges, now validated clean by mev) is invisible to pure semantic retrieval; neighborhood
  expansion surfaces the decision/plan/status docs that *surround* a hit. Keeps the brain-program
  promise that mev's edge model is the contract.
- **Repo:** orchestrator (retrieval + ingestion), consuming mev's graph-emit format (read-only
  contract; mev owns the emitter).
- **Interfaces / contracts:** Consumes `mev emit-graph` JSON (mev's edge model is the contract) and
  the Block T `BrainDocument` columns. Produces the edge store + the two-stage retriever the Console
  and agents query. No data-contract version bump (read path only).
- **Depends on:** Block B (a populated, queryable semantic store to expand from). mev MV.3B.R (done —
  the emitter exists).
- **Out of scope:** Relatedness *suggestion* (brain-program HQ.R2). Changes to mev's emit format.
  Structural-only queries with no semantic stage (the Console's `bastion brain` graph reader covers
  those file-side).
- **Acceptance criteria:** edges load from a live `mev emit-graph` run; a query whose answer lives in
  a `related:`-neighbor of the top semantic hit retrieves that neighbor; measurable retrieval-quality
  improvement (or parity + explainability) vs semantic-only on the Block B eval set; the orchestrator
  gate holds (`uv run python -m pytest`, `ruff`, `pylint app/` 10.00/10).

---

### OR.O — Widen the index corpus to all sub-repo planning docs

- **What:** Extend `index_brain.py`'s corpus list to include every sub-repo's `planning/` (status,
  decisions, devlog) **+** `CLAUDE.md`, each as its own workspace/corpus. Answers *"where am I in repo
  X, what did I decide, how does this project work"* across all repos.
- **Why:** Wave 0 — highest value-to-cost ratio in the program: it is already OKF markdown, so this is
  a corpus-config change, not new retrieval code. A daily-driver feature on day one.
- **Repo:** orchestrator (the indexer).
- **Interfaces / contracts:** Consumes the existing `BrainDocument` + corpus-dispatch contract;
  produces **per-repo corpora**. Light dependency on the multi-workspace addressing introduced in
  Block C (corpora must be addressable by workspace).
- **Depends on:** Block B (a populated, queryable store to widen). Block C for clean per-workspace
  addressing (can ship a flat multi-corpus first and tighten under C).
- **Out of scope:** Indexing source code (Block P). Per-client corpora (Block C / S). Auto-refresh
  (Block J).
- **Acceptance criteria:** a known status/decision question over a sub-repo returns a correctly cited
  answer **scoped to that repo's corpus**; the indexer crawls each configured sub-repo's `planning/` +
  `CLAUDE.md`; the orchestrator gate holds; a multi-corpus retrieval test covers cross-repo scoping.

---

### OR.J — Brain freshness loop (cron reindex + `bastion brain reindex`)

- **What:** Wire two triggers for `index_brain.py` — a **daily cron job** and a `bastion brain reindex`
  convenience command — so the Brain stays current without manual CLI invocation. The incremental skip
  logic already ships in Layer 1 (`indexed_at` vs. file `mtime`): a default run only re-embeds modified
  files; `--rebuild` forces a full re-index. **No post-commit hooks** — sub-repo commits are frequent
  SDLC commits, not meaningful doc changes; scoped to the brain corpus only.
- **Why:** Wave 0 — today the indexer is a manual CLI, so the Brain silently goes stale between runs;
  "self-updating" is currently false. The incremental path is already built; this block is purely
  wiring triggers. Cheapest high-payoff fix in the extension.
- **Repo:** Cross-repo — orchestrator (cron config + any runner script) + bastion (the
  `bastion brain reindex` subcommand that shells out to `index_brain.py`).
- **Interfaces / contracts:** Consumes the existing `BrainDocument` + corpus-dispatch contract and the
  indexer's already-shipped incremental-skip path (`indexed_at` vs. mtime). No data-contract bump.
- **Depends on:** Block B (a populated store to keep fresh).
- **Out of scope:** Post-commit hooks on sub-repos (too noisy — SDLC sessions commit constantly).
  Real-time streaming index. Multi-knowledge-dir scheduling (Block C handles portability).
- **Acceptance criteria:** a cron job runs `index_brain.py` on a daily schedule; `bastion brain reindex`
  shells out to `index_brain.py` and surfaces the output; a run over an already-indexed, unchanged corpus
  skips all files (incremental path confirmed); `--rebuild` forces a full re-index; both repos' gates
  hold.

---

### OR.C — Multi-workspace Brain (per-repo / per-client corpora) — Python half

- **What:** Generalize the Python Brain readers — the RAG indexer and retriever — to point at an
  **arbitrary knowledge directory / workspace** (a config/CLI-provided root + workspace id), not only
  the brain repo's path. Same OKF + RAG behavior over any conforming directory; `workspace_id` becomes
  the addressing key shared with the memory layer (Block S).
- **Why:** Wave 1 — proves the Brain is a *capability* over a knowledge dir, not a hardcode of one
  repo; required groundwork for per-repo (Block O) and per-client (Block S) corpora and for the
  loop-proof's "point Bastion at your knowledge."
- **Repo:** orchestrator (indexer/retriever root + workspace config). The **bastion
  graph-reader half** of the same shared "knowledge directory" convention is built in bastion.
- **Interfaces / contracts:** Produces a shared **"knowledge directory / workspace" convention** (root
  path + workspace id + OKF expectations) consumed identically by the Python RAG and the bastion graph
  reader — the load-bearing cross-repo seam of this block.
- **Depends on:** Block B (semantic retrieval populated). Coordinates with bastion's graph reader (it
  consumes the same convention).
- **Out of scope:** Multi-tenant switching UX. De-opinionating the OKF format itself. Packaging /
  install. The Rust graph-reader root config (bastion's half).
- **Acceptance criteria:** the Python readers index and answer over a **second, non-brain** OKF
  directory passed by config/flag; default still resolves to the brain repo; the workspace convention
  is documented as the shared contract; the orchestrator gate holds; a portability test fixture (small
  OKF dir) is covered.

---

### OR.P — Semantic code search (source as a corpus)

- **What:** Chunk + embed source files per repo (chunk by function/class via tree-sitter) as new
  **per-repo code corpora**. Answers *"how does X work, where's the code that does Y."*
- **Why:** Wave 1 — "ask my own system how my own code works" is a genuine daily feature and a strong
  dogfood story. Reuses the Project D retrieval machinery over a new corpus type.
- **Repo:** orchestrator (embeddings + retrieval = Engine/Brain Python half).
- **Interfaces / contracts:** Produces **code-chunk corpora** addressable by repo/workspace (Block C
  addressing). The deterministic structural twin — exact symbol/def/refs, code-as-graph — is bastion's
  Block Q, **out of scope** here.
- **Depends on:** Block C (multi-workspace addressing); benefits from Block O.
- **Out of scope:** Exact symbol/def/refs and code-as-graph (bastion Block Q — deterministic,
  Console-side). Cross-repo refactoring.
- **Acceptance criteria:** a "how does X work" query returns the relevant functions with file/line
  citations; chunking respects function/class boundaries; the orchestrator gate holds; a code-corpus
  retrieval test covers function-boundary chunking + citation.

---

### OR.I — Cost control (abort endpoint + server-side budget gate) — Python half

- **What:** Add the **enforcement points** the Console's kill switch and budget controls trigger: a new
  **authenticated abort endpoint** that cancels a run and stamps its terminal state, and a
  **server-side budget gate** that refuses (or flags) a dispatch that would exceed a configured
  ceiling. bastion drives the CLI half (`bastion kill`, `--watch`, thresholds); the Engine performs the
  cancel and the gate.
- **Why:** Wave 2 — retroactive cost estimation is not control. Per brain D25 the Console is read-only
  for state and *triggers* mutations; the actual cancel + terminal stamp **must** live here, the layer
  that owns the run lifecycle.
- **Repo:** Cross-repo — orchestrator (abort endpoint + budget gate, the enforcement
  point) + bastion (the CLI surface that calls them).
- **Interfaces / contracts:** **Produces two new D20 data-contract additions** — an authenticated abort
  endpoint and a budget-gate field/response — bumped per the CLAUDE.md D20 protocol and re-pinned in
  bastion's `data-contract.md`. Consumes the existing per-node cost/usage capture (D30).
- **Downstream consumers (no new endpoint required of them):** beyond `bastion kill`, the **BastionUI**
  program (brain **D28**) is a downstream consumer — `bastion serve` proxies *this* abort endpoint so
  the phone can kill a run (BastionUI server Phase 11 Block G; brain BastionUI program Block N). The
  BastionUI program defines **no new orchestrator endpoint** — it depends on this Block I. There is no
  scheduling change here: Block I stays Wave 2; BastionUI's Engine-control phase is post-v1 and waits on
  it. (Block I's prerequisite, **D28 incremental persistence, is already shipped** — see
  `app/worker/tasks.py` `on_progress`.)
- **Depends on:** The incremental execution-state persistence (D28) so a run is abortable mid-flight;
  bastion's structured-event spine strengthens alerting but is not hard-required here.
- **Out of scope:** Per-client billing. Silent auto-killing (operator- or threshold-triggered with
  confirmation). Any direct Celery/Redis manipulation by bastion (it calls the endpoint; it never
  touches the queue).
- **Acceptance criteria:** `POST` to the abort endpoint cancels a running workflow and the run reaches
  terminal state in `node_runs`; a dispatch over the budget ceiling is refused/flagged per config; the
  data-contract bump is recorded in both `data-contract.md` files; the orchestrator gate holds; tests
  cover the abort path and the budget-gate decision.

---

### OR.L — Answer-time grounding (citation verify + abstain)

- **What:** Harden the RAG answer path (Project D): **verify** that a cited section actually contains
  the claim it's cited for, add a **confidence/abstain threshold** (return "I don't have that" when
  retrieval score is below a bar rather than relying only on the prompt rule), and prefer **two-source
  corroboration** for high-stakes answers.
- **Why:** Wave 3 — completes "prevent hallucinations" on the *answer* side (the corpus side is
  bastion's deterministic integrity scan). Today grounding is a single soft prompt instruction with no
  verification and no numeric abstain — not good enough once client work runs on the Brain.
- **Repo:** orchestrator (Project D retrieval/answer nodes).
- **Interfaces / contracts:** Consumes the existing retrieval pipeline + `cited_sections` field.
  Produces a **verified-citation + confidence signal** on the answer envelope.
- **Depends on:** Block B (semantic retrieval populated). Independent of bastion.
- **Out of scope:** A full eval/routing harness (Project H). Re-architecting retrieval (reuse the
  two-stage hybrid path). LLM-judged semantic contradiction (that's the bastion deterministic
  integrity scan's fuzzy follow-on).
- **Acceptance criteria:** an answer whose cited section does not contain the claim is flagged/withheld
  in a test; below-threshold retrieval returns an explicit abstain; the orchestrator gate holds
  (pytest / ruff / pylint 10.00/10); tests cover the verification and abstain paths.

---

### OR.R — Brain-as-MCP-server (Python server half of the MCP split)

- **What:** Expose the Brain (semantic + structural + memory read path) as an **MCP server** in the
  Engine, so agents and tools reach it over the protocol. The **server is Python** (here); the
  **client is Rust** (bastion's harvested `workflow-engine-mcp`) — built together as distinct seam
  halves (D26 MCP split).
- **Why:** Wave 4 — brain-rag **Layer 3 = MCP**. This is the server peer the Console's MCP client
  connects to; it makes the Brain reachable by any MCP-speaking agent, not just this orchestrator's own
  nodes.
- **Repo:** orchestrator (the Engine / Brain Python half).
- **Interfaces / contracts:** Produces an **MCP server surface** over the Brain read path; consumed by
  bastion's vendored MCP client. Defines the tool schema (query kinds, corpus/workspace params) as the
  client↔server contract.
- **Depends on:** Block B (semantic) + the structural graph being queryable (bastion's graph block);
  Block C (workspace addressing) for scoped queries.
- **Out of scope:** The MCP client (bastion). Auth beyond what the transport provides. Write/mutation
  tools (read path only; mutations stay endpoint-triggered per Block I / D25).
- **Acceptance criteria:** bastion's vendored client connects to this server and invokes a Brain query
  tool end-to-end; the tool schema is documented as the client↔server contract; the orchestrator gate
  holds; a server-side tool-invocation test passes.

---

### OR.S — Entity / memory layer (Project G reframed)

- **What:** Build Project G as the Brain's **memory capability** with **clients, companies, products,
  and SOPs as first-class entities**: the store (`Peer`/`AgentEpisode`/`SemanticMemory`) is Brain data;
  the workflows (ingest-time extraction, dream-time consolidation on Claude, loader) are Engine; the
  Console reads it. Index business/operational docs so the Brain answers *"what did I last discuss with
  client X, what's their status, what rate did I quote."*
- **Why:** Wave 3 — the "keep track of client work" capability, Bastion's operational memory.
  Demand-first: the first real client creates the need for the **entity** half immediately; full
  consolidation can follow.
- **Repo:** orchestrator (store + workflows) + the brain repo (operational docs
  indexed).
- **Interfaces / contracts:** Consumes the Honcho reference architecture (orchestrator D25). Produces
  the **entity/memory store** the Console and Engine read, keyed by `workspace_id` (the Block C
  addressing). The full Project G build spec (models, decay, contradiction handling, test bar) is the
  Project Library entry above.
- **Depends on:** Block B (retrieval) + Block C (the multi-workspace / entity addressing model).
- **Out of scope:** Model-routing of the ingest/consolidation steps (Project H). Consolidation must
  stay on Claude (D35) — never local.
- **Acceptance criteria:** a client entity accumulates episodes/facts across interactions; confidence
  decay + contradiction handling proven by test; a "what's the status with client X" query returns a
  cited answer; the orchestrator gate holds — **Project G's heavier test bar applies** (test harder
  than anything else in the plan).

---

### OR.Z — `sdlc-flow`/`sdlc-run` → orchestrator-native nodes & workflows (HL2 graduation)

> **★ Brandon's priority ask (north-star Thread 2c).** Graduate the **Coding & Delivery harness (HL2)**
> from a base-template JS harness into **Engine-native Node/Workflow primitives** — so coding work runs
> with *more control*: typed state, durable retries/checkpoints, live observability (bastion monitor),
> and exact cost. Sequenced **early but after the cross-repo unblock work** (Brandon: "move this up
> sooner than later so we can start doing coding work with more control, but only after we unblock some
> work for other repos") — Wave 2, gated only on the Wave-0 Brain unblock (T/B) + the cost-control seam
> (Block I) other repos need, with **Project E (ParallelNode merge) as its hard local prerequisite.**
> When executed, this block is large enough to warrant its own sub-master-plan (open Claude Code here and
> run `/generate-master-plan` for it) — start with one stage/workflow, prove parity with the JS engine,
> then expand. **Do not rewrite the JS engines in one shot.**

**The graduation, concretely.** Today `sdlc-flow`/`sdlc-run` are JS workflow engines in
`base-template/.claude/workflows/` that orchestrate `/sdlc-task` pipelines across dependency-ordered
waves — each task in its own git worktree, with bounded retries, triage, escalation, and additive
merges. The orchestrator already has every primitive needed to host this natively:
- the **Node / Workflow / TaskContext** DAG engine (the deterministic orchestration layer);
- **`ParallelNode`** (once Project E's merge gap is fixed) for the per-wave task fan-out;
- the **`CLAUDE_CODE_SDK` + `CLAUDE_CODE_SESSION` providers (already shipped)** — these *drive Claude
  Code* to do the actual coding, exactly as a node's `model_provider`. **The Engine never writes code
  itself**; the SDLC nodes drive Claude Code agents through these providers — the load-bearing seam that
  makes this fit D24/D25;
- **`RouterNode`** for triage / escalation branching;
- **incremental execution persistence** (D28 `on_progress`) → a coding run shows up in `events` /
  `node_runs` like any workflow, so **bastion monitors it live** (a direct boost to the loop-proof, Block G).

The work: model the SDLC stages (scout → implement → test → review → merge) as orchestrator **Nodes**,
and block-level orchestration (wave fan-out, per-task worktree isolation, retry/escalation) as a
**Workflow** composing `ParallelNode` + `RouterNode`. base-template keeps the *spec/command authoring
surface* (the `/sdlc-*` commands, the spec format, `harness.json`); only the *execution runtime*
graduates into the Engine.

- **What:** Build Engine-native SDLC **nodes** (scout/implement/test/review/merge, each driving Claude
  Code via the existing providers) and a block-orchestration **workflow** (wave fan-out via `ParallelNode`,
  per-task worktree isolation, bounded retry + escalation via `RouterNode`, additive merge) that
  reproduce the `sdlc-flow`/`sdlc-run` behavior as orchestrator primitives. Incremental: one
  stage/workflow first, prove parity, then expand.
- **Why:** north-star §"Separate open-ended reasoning from deterministic workflows" + §"Every repeated
  success should become a reusable asset" — the deterministic SDLC orchestration becomes typed,
  checkpointed Engine state while the per-task coding stays open-ended agent work driven via the
  providers. Graduating HL2 into the Engine gives the operator real control over coding work (durable
  retries, live monitor, exact cost) and makes the loop-proof (Block G) a *native* Engine run, not a JS
  side-process. Fits D24's "one authoring engine (Python)".
- **Repo:** orchestrator (the Engine — SDLC nodes + the orchestration workflow). Consumes
  base-template's spec/command surface; observed by bastion.
- **Interfaces / contracts:** Consumes the Node/Workflow/TaskContext primitives + `CLAUDE_CODE_SDK`/
  `CLAUDE_CODE_SESSION` providers + `ParallelNode` (Project E). Consumes **base-template's `/sdlc-*` spec
  format + `harness.json`** as the *input contract* (likely warrants a new shared **SDLC-spec/harness
  contract** doc between base-template and orchestrator — author it with this block). Produces
  Engine-native SDLC nodes + workflow; the coding run is exposed over the existing **D20/D30 data
  contract** (`events`/`node_runs`) so bastion observes it with no new endpoint.
- **Depends on:** **Project E (ParallelNode merge) — hard prerequisite** (the wave fan-out needs it).
  Soft sequencing: after Wave-0 Brain unblock (T/B) + cost-control seam (Block I). The Claude Code
  providers are already shipped.
- **Out of scope:** **Auto-merge** — the human review gate stays (D25; agents propose via PR, humans
  approve). Replacing base-template's spec/command *authoring* surface (only the execution runtime
  graduates). A one-shot rewrite of the JS engines (incremental parity instead). Self-healing trigger
  (that's program Block N, which *drives* this harness).
- **Ratchet:** the reusable Engine-native HL2 harness — SDLC stage nodes + the wave-fan-out/worktree/
  additive-merge workflow as first-class Engine primitives any future coding work composes; plus the
  shared SDLC-spec contract.
- **Eval slice:** the **coding** eval domain in Block U — pass-rate of spec→shipped runs, retry rate,
  intervention rate, regression rate; this is the harness whose evals Block U most needs.
- **Ladder rung:** advances HL2 from rung 5 (a specialized harness, in JS) to rung 7 (a durable,
  observable, checkpointed automation made Engine-native) — the explicit "graduate a reliability-critical
  workflow into the platform" move.
- **Acceptance criteria:** a spec runs through the Engine-native SDLC workflow (scout→implement→test→
  review) driving Claude Code via the providers and producing a draft PR with the review gate intact;
  wave fan-out across ≥2 independent tasks runs via `ParallelNode` with correct per-task worktree
  isolation + additive merge; the run is visible in `events`/`node_runs` (bastion can monitor it); the
  orchestrator gate holds (`uv run python -m pytest`, `ruff`, `pylint app/` 10.00/10); tests cover the
  stage nodes + the fan-out/merge path.

---

### OR.U — Eval + success-metrics engine (elevates Project H)

> **Project H ≡ Block U.** The model-eval & routing harness (Project H) is elevated from a floating
> wave-table row to the **named Self-Improvement track** the north-star demands. The Project Library
> entry below stands as the build detail (scoring strategies, blind/randomized judge, routing config);
> this block widens it into the program's eval + success-metrics engine.

- **What:** Stand up an **evaluation + success-metrics engine**: an eval harness covering the north-star
  eval domains (coding, review, test-writing, browser, docs, research, project-management, long-horizon,
  failure-injection, policy/safety, uncertainty, scope-control, adversarial-input), tracking
  pass-rate · pass-rate-under-repeat · by-domain · by-model · by-profile · time-to-success ·
  cost-to-success · intervention frequency · silent-failure frequency · regression history. **Absorbs
  Project H** (model eval & routing). Reads the per-repo `status.md` **Metrics** sections (D30) as the
  lagging operational signal.
- **Why:** north-star Layer I — *"this is the core of self-improvement; without this the system is
  theater."* Today eval is an unscoped floating row; the north-star elevates it to a track. Its outcomes
  are what *license* autonomy promotion (Block X — trust earned from measured results), and they feed the
  Console metrics surface (Block V) and model routing.
- **Repo:** orchestrator (the eval harness + metrics aggregation = Engine).
- **Interfaces / contracts:** Consumes the D30 `status.md` Metrics convention + workflow run records
  (the D20/D30 `node_runs` cost/usage). Produces eval pass/regression signals consumed by Block X (trust
  promotion), Block V (the Console metrics rollup), and model routing. No data-contract bump (read path)
  unless a new eval-result field is exposed cross-repo.
- **Depends on:** Block B (a working Brain/agent path to eval over) + the D30 Metrics convention (HQ
  Restructure Thread 1). Project H's design is the seed. Demand-first: pull forward when run
  volume/economics justify routing decisions, or before any autonomy promotion (Block X). **Block Z's
  coding eval is its first high-value slice.**
- **Out of scope:** Model-routing *enforcement* (stays Project H's routing half until volume demands it).
  Per-harness evals beyond the slices each harness owns (Track 6). Adopting external ideas without a
  local eval (that's Block W's discipline, run *through* this engine).
- **Ratchet:** the eval harness + the scorer library + the per-node routing config + the regression-
  history store — reusable across every harness and the one-change self-improvement loop.
- **Eval slice:** this block *is* the eval engine — it defines the slices; its own success is "a slice
  runs and scores by domain/model and regression persists across runs."
- **Ladder rung:** makes rung 6 (add eval coverage) first-class — the engine the whole ladder's rung 6
  runs on, and the gate that licenses rungs 8–9 (monitoring, trust-based autonomy).
- **Acceptance criteria:** an eval slice runs offline and scores pass-rate by domain/model; regression
  history persists across runs; a representative slice gates a self-improvement change (the one-change
  loop) with keep-if-better/revert-if-worse demonstrated; the orchestrator gate holds.

---

### OR.W — External-intelligence loop + external-knowledge memory

- **What:** A **recurring news→improvement pipeline** (north-star §"External Intelligence Loop"):
  scheduled monitoring of open-source agent/AI architecture repos, releases/changelogs, model-provider
  updates, protocols (MCP / agent-to-agent), benchmarks, papers, and dependency security advisories.
  Produces a dated, ranked **digest** + improvement candidates (new eval / skill / workflow / adapter /
  policy / dashboard / contract). Writes a dedicated **external-knowledge memory** layer with fields
  `source · url · date · category · claim · relevance · confidence · suggested-experiment · status ·
  outcome`. **Adopt nothing into core without a local eval / shadow run** (runs through Block U).
- **Why:** north-star §"External Intelligence Loop" + §"News-to-Improvement Pipeline" — the system
  learns from the outside world, not only from its own failures. The curated reference list in
  `north-star.md` (LangGraph, Letta, Temporal, Graphiti, Langfuse, Mastra, …) is the seed feed. Answers
  *"what changed in the agent ecosystem this week; which ideas improved us; which did we reject and
  why; which of our assumptions are getting stale."*
- **Repo:** orchestrator (the recurring workflow = Engine; a `research_agent`
  specialization) + the brain repo (the external-knowledge memory docs, indexed as a Brain corpus).
- **Interfaces / contracts:** Consumes WebSearch/fetch + MCP + the north-star reference list. Produces
  external-knowledge memory entries (queryable in the Brain via Track 1) + improvement candidates feeding
  the D30 `improve` queue and Block U's eval-candidate intake.
- **Depends on:** Block B (a Brain to store into) + recurring-loop infra (cron, like Block J).
  Demand-first: low urgency until the core loop is stable (north-star: "expand breadth only after the
  loop is stable"); high leverage for not going stale. Wave 5 ✲.
- **Out of scope:** Auto-adopting any external claim (must pass a Block U eval / shadow run). Building
  new MCP *servers* (Block R). Ingesting thin-wrapper / chat-shell projects (north-star de-prioritization
  rules apply).
- **Ratchet:** the external-knowledge memory layer + the recurring digest workflow (a `research_agent`
  specialization that also seeds the HL3 Browser Research harness).
- **Eval slice:** candidates it surfaces are validated through Block U; its own success metric = share of
  surfaced candidates that became adopted improvements vs. rejected-with-reason.
- **Ladder rung:** a recurring automation (rung 7) + monitoring (rung 8) pointed at the *external* world,
  feeding rung 6 (new evals) and rungs 3–4 (new skills/workflows).
- **Acceptance criteria:** a scheduled run produces a dated, ranked digest + ≥1 bounded experiment
  candidate; external-knowledge entries carry the full field set and are retrievable in the Brain; at
  least one candidate is shown routed into the `improve` queue or Block U; the orchestrator gate holds.

---

## Console — `bastion` (the Rust layer; separate repo)

The **Console** of Bastion — a single Rust binary (`bastion`) — commands and observes this Python
Engine over HTTP and reads its Postgres state directly; the two **never share code**. It is *not* a
rewrite of any part of this repo and holds no billable work (brain D24/D25, local D36). Where Rust
uniquely wins, it **harvests** tested crates from the portfolio repos (`workflow-engine-rs`,
`claude-sdk-rs`) — token counting, MCP client, the `knowledge_graph` structural layer, a local-model
node — never standing up a second engine.

This repo's only obligations to the Console are **data-contract** ones: keep the `events` /
`task_context` / `node_runs` shapes pinned (D20/D30), and add the abort endpoint + budget gate
(Block I) the Console triggers. See `agentic-portfolio/docs/projects/bastion.md` and
`bastion/planning/` for the Console's own plan.

---

## Strategy & Career Context

Business goals, contracting strategy, leads, and career posture live in the company brain:

- Career strategy: `agentic-portfolio/docs/career.md`
- Content plan: `agentic-portfolio/docs/content/ideas.md`
- Lead pipeline: `agentic-portfolio/docs/business/pipeline.md`
- The Diagnostic productized service: `agentic-portfolio/docs/diagnostic/plan.md`
- The Bastion program (this repo is its Engine + Python-half-of-Brain):
  `agentic-portfolio/planning/bastion-product/master-plan.md`

---

*Last updated: 2026-06-27 — north-star Thread 2c (orchestrator reorg): added the North-Star Alignment
(umbrella view) section mapping phases/projects → the 7 capability tracks; reframed Project H → Block U
(eval + success-metrics engine); added the three north-star tracks this repo now owns — Block U,
Block W (external-intelligence loop), and Block Z (`sdlc-flow`/`sdlc-run` → orchestrator-native nodes &
workflows, the HL2 graduation); pulled Project E forward to Wave 2 as Block Z's prerequisite. Block
contracts use the north-star-enriched `/generate-master-plan` skeleton (Ratchet · Eval slice · Ladder
rung). Earlier — 2026-06-25 — aligned to the Bastion program (brain D24/D25/D26; local D36): Role-in-
Bastion section + program-block crosswalk, reframed Projects F→Block B and G→Block S, added Brain-side
blocks O/J/C/P/L/R + cost-control I. For the previous version's strategic arc, see `docs/career.md`.*
