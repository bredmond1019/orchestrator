---
type: Reference
title: orchestrator Knowledge
description: Distilled, durable knowledge for orchestrator — how it works, conventions, and an architecture digest.
doc_id: knowledge
layer: [factory]
project: orchestrator
status: active
keywords: [knowledge, conventions, architecture, semantic memory, durable]
related: [context, status, memory, planning-index]
---

# Knowledge — orchestrator

Distilled, **durable** project knowledge: how the system works, the conventions it follows, and an
architecture digest. This is *semantic memory* at repo scope — the things a new agent should read
to understand the project, kept current as the design settles.

Seed it from `context.md`, the decision record, and what you learn while building. Keep entries
durable (how things work), not episodic (what happened) — episodic notes go in `memory.md`, settled
choices go in `decisions/`. Each entry promoted from the cold archive tier carries provenance
(D35 format: claim · source · date · supersedes · freshness).

## How it works

_Architecture digest — the main components and how they fit together._

- **Core execution model: FastAPI → Celery → Workflow.run() → Node chain → TaskContext**
  The public surface is a single `POST /events/` endpoint. Celery receives the task and calls `Workflow.run()`, which walks a validated DAG of typed nodes. `TaskContext` is the shared mutable ledger keyed by node name — nodes read upstream results and write their own outputs via `update_node()`.
  source: planning/context.md · date: 2026-06-25 · supersedes: — · freshness: 2026-06-27

- **Node types: AgentNode, ToolUseNode, RouterNode, ParallelNode**
  `AgentNode` wraps a pydantic-ai model call. `ToolUseNode` uses the raw Anthropic SDK tool loop (Project B). `RouterNode` dispatches to branches (marked `is_router=True` in the DAG). `ParallelNode` fans out to multiple branches and merges results.
  source: docs/app-architecture-overview.md · date: 2026-06-25 · supersedes: — · freshness: 2026-06-27

- **TaskContext key contract: AgentNode stores `{"result": output}`, not `output` directly**
  `AgentNode.update_node(node_name=..., result=output)` produces `{"result": output}` in `task_context.nodes[name]`. Any downstream node reading `ctx.get_node_output("X")` gets the inner `output`, not the wrapper. Tests must mirror this exact structure when seeding an upstream node — passing a raw dict produces a silent false-pass.
  source: CLAUDE.md (Standing Rule 9) · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **Two-stage hybrid retrieval (RetrieveChunksNode)**
  Stage 1: pgvector cosine-distance ANN (top-20 candidates, NaN-safe sort). Stage 2: ILIKE keyword re-rank scoped only to Stage 1 candidate IDs. Scores fused additively; section-title chunks receive 2× boost. Corpus dispatch: `"content"` → `content_chunks`; `"brain"` → `brain_documents`. Pattern is proven from `rag-engine-rs` and reused verbatim in Project F.
  source: planning/archive/phase1-projectD/tasks.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **Brain semantic layer (brain-rag): BrainDocument model + index_brain.py indexer**
  `app/database/brain_document.py` holds the `BrainDocument` SQLAlchemy model with `Vector(1024)` embedding, six OKF frontmatter columns (doc_id, layer, project, status, keywords, related), generated `content_tsv` tsvector (GIN-indexed) for Postgres FTS, and an HNSW ANN index. `scripts/index_brain.py` is the standalone CLI that walks the brain corpus, strips YAML frontmatter, embeds via `mxbai-embed-large` (Ollama), and upserts. Supports `--rebuild`, `--dry-run`, `--limit N`.
  source: planning/archive/brain-rag/tasks.md · date: 2026-06-26 · supersedes: — · freshness: 2026-06-27

- **Incremental node-level execution state (D28)**
  `Workflow.run()` accepts an optional `on_progress` callback injected by the Celery worker. After each node completes, the worker persists the updated `events` row (status + `node_runs` JSON). Default is a no-op — nodes themselves never open a DB session. This keeps the brain deployment-agnostic (D18/D33) while giving crash visibility and the foundation for resume-from-last-good-node.
  source: planning/decisions/D28-node-level-execution-state.md · date: 2026-06-24 · supersedes: — · freshness: 2026-06-27

- **Orchestrator-owned versioned data contract (D30)**
  `docs/data-contract.md` describes everything an external consumer (Bastion CLI) reads: the `events` table, `task_context`/`node_runs` JSON shape, and the HTTP surface. Version-bumped on any shape change; `bastion/docs/data-contract.md` is re-pinned in lockstep. `AgentNode`/`ToolUseNode` base classes capture per-node input (prompt/messages) + JSON-serializable output, making the detail view possible without consumer-specific node code.
  source: planning/decisions/D30-data-contract-ownership.md · date: 2026-06-24 · supersedes: — · freshness: 2026-06-27

- **Role in Bastion (D36): Engine + Python-half-of-Brain**
  This repo is two of Bastion's five layers: the **Engine** (LLM/agent workflow runtime) and the **Python half of the Brain** (brain-rag semantic retrieval, indexing, memory/entity store). Project F ≡ Brain Block B (semantic layer). Project G ≡ Brain Block S (memory capability). Bastion CLI (Rust) is a read-only consumer over HTTP/Postgres — it never shares code with this repo and never holds any workflow logic.
  source: planning/decisions/D36-bastion-engine-brain-role.md · date: 2026-06-25 · supersedes: — · freshness: 2026-06-27

- **Component reuse map (Phase 0 → Phase 2)**
  `EmbeddingService` built Phase 0, reused in A/D/F/G. `SearchService` (Tavily) built Phase 0, reused in B/C. `ChunkingService` built Phase 0. `RetrieveChunksNode` built in Project D, reused verbatim in F. `ContentChunk`/`ChatSession` models from D reused in F. `ParallelNode` (fixed merge) from E used in G+. `MemoryLoaderNode`/`ConsolidationWorkflow` from G reusable in client work.
  source: planning/context.md · date: 2026-06-25 · supersedes: — · freshness: 2026-06-27

- **Embedding model: mxbai-embed-large via Ollama (D37), not Voyage**
  The Brain vector store uses a local 1024-dim model (`mxbai-embed-large` served by Ollama on the Mac Mini). Dimension matches `voyage-2` — no schema migration needed. `EmbeddingService(model, dims)` provider seam makes this transparent to nodes. `--rebuild` is now free and repeatable. Re-evaluate hosted embedder only when a paying client engagement demands it.
  source: planning/decisions/D37-local-embeddings-mxbai.md · date: 2026-06-26 · supersedes: Voyage AI as default embedder · freshness: 2026-06-27

- **Diagnostic alignment: Projects B + C output schemas are revenue-gated**
  Project B must produce `DiagnosticIntakeOutput` (with `WorkflowCandidate` list). Project C produces a deliverable matching the Diagnostic template (Situation + Ranked Candidates + Top 3 Profiles + First Engagement). Composite scoring formula embedded in the j2 prompt: `composite = (frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)`. This is a client-revenue constraint, not a portfolio constraint.
  source: planning/archive/diagnostic-alignment/notes.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

## Conventions

_Naming, patterns, and standing choices specific to this project._

- **All LLM prompts are Jinja2 templates via PromptManager (D34)**
  Every system prompt lives in `app/prompts/<name>.j2`, never inline in Python. `PromptManager` loads and renders them. Node code imports the manager only — no f-string prompts. This allows prompt tuning without touching logic and enables independent version control of prompt changes.
  source: planning/decisions/D34-jinja2-prompts.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **Every workflow must be registered in both registries (Standing Rule 6)**
  Add the enum member to `app/workflows/workflow_registry.py` AND the event schema entry to `app/api/schema_registry.py`. Missing the second step causes the API dispatcher to 422 every request for that workflow. `tests/api/test_endpoint.py::TestSchemaRegistryCompleteness` enforces this automatically.
  source: CLAUDE.md (Standing Rule 6) · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **No deployment logic inside nodes (D33/D18)**
  Model choice and persistence are injected — never hardcoded. The first `if running_locally:` inside a node means two products have started being built. Model routing via per-node `model_provider` config; persistence always via `GenericRepository`. The worker (harness layer) is the only thing that knows persistence exists.
  source: planning/decisions/D33-deployment-agnostic-nodes.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **Python stays Python; Rust is the Console (D6/D36)**
  Orchestration is I/O-bound — model/DB/network latency dominates; microseconds saved by Rust are meaningless behind a 2-second model call. Rust (`bastion`) is a separate Bastion layer that reads this repo over HTTP/Postgres and never shares code with it. Do not suggest Rust rewrites of any orchestration code.
  source: planning/decisions/D6-python-for-orchestration.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **Project G (agent memory) = episodic → semantic pipeline; Honcho is the reference (D25)**
  Read Honcho source before writing Project G code. Adopt its two-stage pipeline and multi-peer entity model. Build a custom G for production (not Honcho) for domain specificity and privacy-first deployment. Clients, companies, products, and SOPs are first-class entities keyed by `workspace_id`.
  source: planning/decisions/D25-honcho-reference.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **Top-tier models first; eval-driven local routing via Project H (D35)**
  All first implementations use the best available hosted model. Local/open-weight alternatives enter via Project H's offline eval harness, which produces per-node routing decisions baked in at design time — not a per-request runtime router. The eval is the expert artifact (the routing judgment), not the dynamic switch.
  source: planning/decisions/D35-top-tier-models.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **Lazy imports inside main() for CLI scripts (D32)**
  `scripts/` files must defer heavy imports (ORM sessions, EmbeddingService, API-key consumers) to inside `main()`. Module-level body: stdlib + argparse only. This keeps `--dry-run` and `--help` usable without a live DB or API key, and keeps import-only usages (CI, tooling) safe.
  source: planning/decisions/D32-lazy-import-cli-scripts.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **SQLite test fixture excludes ARRAY and Vector models (D31)**
  Any SQLAlchemy model with `ARRAY` or `Vector` columns is excluded from `Base.metadata.create_all()` in the SQLite conftest fixture. Pass only SQLite-compatible models via `tables=`. Mark the excluded models in a comment. Those models are tested against live PostgreSQL only.
  source: planning/decisions/D31-sqlite-array-exclusion.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **`customer_care` workflow is reference-only and frozen**
  Do not extend it, add tests for it, or treat it as a pattern to modify. New workflows go alongside it. All four core hardening bugs (repository.exists() 2.x compat, ghost-row commit ordering, lazy engine init, descriptive KeyError on mis-ordered nodes) are fixed and covered by tests — do not reintroduce them.
  source: CLAUDE.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **OKF frontmatter required on every new .md in docs/ or planning/**
  Required fields: `type`, `title`, `description`. Strongly encouraged: `doc_id`, `layer`, `project`, `status`, `keywords`, `related`. Adding a file to a directory requires updating that directory's `index.md`; propagate scope changes up the tree.
  source: CLAUDE.md (Standing Rule 10) · date: 2026-06-25 · supersedes: — · freshness: 2026-06-27

## Gotchas

_Non-obvious constraints, sharp edges, and hard-won lessons._

- **Keyword search silently fails on question-form queries without punctuation stripping**
  `RetrieveChunksNode._keyword_search()` must strip non-word characters from query terms before ILIKE matching (`re.sub(r"\W+", "", t)`). Without this, queries ending in "?" (e.g. "What is X?") never get keyword boost — the bare "?" term matches nothing. Discovered in Project D post-merge audit.
  source: log.md (2026-06-22 phase1-projectD post-merge hardening) · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **FTS generated column requires IMMUTABLE function: use array_to_tsvector(), not array_to_string()**
  Postgres rejects STABLE functions in generated columns. `array_to_tsvector()` is IMMUTABLE and safe; `array_to_string()` is STABLE and will fail at migration time. Trade-off: keywords match as exact tokens without stemming — correct for controlled OKF vocabulary.
  source: log.md (2026-06-26 brain-rag-improvements Blocks C+D) · date: 2026-06-26 · supersedes: — · freshness: 2026-06-27

- **chunk_by_section prepends headers to all chunks — test is_header_only_chunk on body only**
  `chunk_by_section` prepends the section header to every chunk it produces, so checking `len(chunk.content)` on the combined text flags every chunk as "too short" (since the header alone exceeds thresholds). The `_is_header_only_chunk()` helper must measure the **header-stripped body** to correctly identify title-only chunks.
  source: log.md (2026-06-26 brain-rag-improvements Block E) · date: 2026-06-26 · supersedes: — · freshness: 2026-06-27

- **Voyage AI free tier blocks live --rebuild: 3 RPM / 10K TPM with no backoff**
  The first live `index_brain.py --rebuild` was blocked by Voyage's free tier rate limits — the indexer has no built-in backoff. This forced the switch to local mxbai-embed-large (D37). If Voyage is ever re-introduced, add exponential backoff around `embed_batch` calls and a `--limit N` flag to test incrementally.
  source: planning/decisions/D37-local-embeddings-mxbai.md · date: 2026-06-26 · supersedes: — · freshness: 2026-06-27

- **Alembic dual-head conflict when two migrations branch from the same parent**
  BrainDocument and events table migrations both branched from `learning_artifacts`, creating a dual Alembic head. Required a manual merge migration (`alembic merge heads`). Always verify `alembic heads` shows a single head after every migration; add the new migration's `revision` to `.gitignore` whitelist if needed.
  source: log.md (2026-06-22 brain-rag Layer 1) · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

---

*Durable knowledge. For episodic notes see `memory.md`; for the chronological narrative see the
root `log.md`.*
