---
type: LocalContext
title: Project Context
description: Orientation, architecture overview, document map, and standing rules for the python-orchestration-system.
---

# CONTEXT — python-orchestration-system

*Orientation for this project. Stable — rarely changes. Read this before `status.md`.*

---

## What This Project Is

A production-grade Python agentic orchestration framework — event-driven, node-based workflow engine
with async task queue. The framework is the foundation; each Phase 1–3 project adds a working
workflow on top of it, building sellable competence and portfolio artifacts.

**Stack:** FastAPI · Celery · Redis · PostgreSQL + pgvector · Voyage AI embeddings · Jinja2 prompts

**Architecture:** `FastAPI endpoint → Celery task queue → Workflow.run() → Node chain → TaskContext`.
Each node is a typed unit: `AgentNode`, `ToolUseNode`, `RouterNode`, `ParallelNode`. `TaskContext`
is the shared mutable ledger passed between nodes (keyed dict; nodes read and write by key).
All system prompts live in `app/prompts/*.j2`, loaded by `PromptManager` — never hardcoded in Python.

For strategic context (practice goals, positioning, narrative):
see `agentic-portfolio/docs/career.md` and `agentic-portfolio/docs/brand.md`.

---

## Document Map

| File | Role | When to read |
|---|---|---|
| `context.md` (this file) | Orientation + architecture | First, every session |
| `status.md` | Current state — what's done, what's next | Every session after context |
| `master-plan.md` | Phase sequence, full project library (A–H), Diagnostic relationship, links to brain | When choosing what to work on |
| `decisions/index.md` | Settled choices — D1 through current | Before relitigating any settled choice |
| `plans/` | Technical implementation plans for specific features | When executing a specific feature |

**Repo-scoped files (not in planning/):**
- `CLAUDE.md` — agent working context: conventions, build/test commands, standing rules for this codebase
- `log.md` — append-only daily working log for this repo

---

## Project Sequence (names only)

**Phase 0 — Foundation:** Block A (presence + codebase ownership) · Block B (Mac Mini harness) · Block C (test infra + 4 bugs fixed) · Block D (shared services + scaffold)

**Phase 1 — Sellable Competence:** Project A (content pipeline — Done) · Project B (research agent) · Project C (proposal generator) · Project D (document Q&A + RAG) → competence checkpoint after D

**Phase 2 — Depth:** Projects E (specialization), F (semantic search), H (model eval harness) · Project G (agent memory — differentiating capstone)

**Parallel:** Rust appliance shell (`bastion`) — personal ops CLI that monitors this framework

Full phase/project detail in `master-plan.md`. Full technical spec per project in `plans/` and `decisions/`.

---

## Standing Rules

1. **Every workflow ships with tests.** Per-project test requirements are in `master-plan.md` Project Library.
2. **No hardcoded system prompts.** All prompts are `.j2` files in `app/prompts/` loaded via `PromptManager`. *(D34)*
3. **No deployment logic inside nodes.** Model choice and persistence are injected via config. *(D33)*
4. **`customer_care` is reference-only.** Do not extend it or add tests for it. New workflows go alongside it. *(CLAUDE.md)*
5. **Top-tier models first; measure before switching to local.** Project H owns that measurement. *(D35)*
6. **Python stays Python.** Rust has a defined home (bastion). Never rewrite orchestration core in Rust. *(CLAUDE.md)*

---

## Core Hardening (Phase 0 Block C — fixed bugs to preserve)

| Location | Bug fixed | Guard to keep |
|---|---|---|
| `database/repository.py` `GenericRepository.exists()` | SQLAlchemy 2.x incompatibility | uses `.first() is not None` pattern |
| `api/endpoint.py` | ghost-row commit ordering | `session.flush()` inside transaction before `send_task` |
| `database/session.py` | `create_engine` at import time | lazy `_get_engine()` — created on first use |
| Router nodes / `core/task.py` | silent `KeyError` on mis-ordered nodes | `TaskContext.get_node_output()` raises descriptive error |

---

## Reference

### Component Reuse Map

| Component | Built In | Reused In |
|---|---|---|
| `EmbeddingService` | Phase 0 | A, D, F, G |
| `TranscriptService` | Phase 0 | A |
| `ArticleExtractionService` / `FetchArticleNode` | Phase 0 / A | A, any workflow ingesting web content |
| `SearchService` (Tavily) | Phase 0 | B, C |
| `ChunkingService` | Phase 0 | A, D |
| `ToolUseNode` | Phase 0 / B | B, C |
| `SelfCriticNode / ReviseNode` pattern | A | C, E |
| `LearningArtifact` model | A | F |
| `RetrieveChunksNode` | D | F (verbatim) |
| `ContentChunk` / `ChatSession` models | D | F |
| `ParallelNode` (merge fixed) | E | G and beyond |
| `MemoryLoaderNode` / `IngestTimeExtractionNode` / `ConsolidationWorkflow` | G | any client/product work (verbatim) |
| `Peer` / `AgentEpisode` / `SemanticMemory` models (multi-peer) | G | client memory patterns |
| Eval harness + per-node routing config | H | every node's `model_provider` |
| Clean documented HTTP API | Phase 0 / D | every shell + agent client |
| Rust appliance shell | bastion (parallel track) | see `agentic-portfolio/docs/projects/bastion.md` |

### Tech Stack

| Concern | Tool | Notes |
|---|---|---|
| Language (brain) | Python 3.12+ | Primary; deployment-agnostic |
| Language (SMB shell) | Rust | Single binary in bastion; clap, optionally ratatui |
| Framework | This orchestration system | Workflow, Node, TaskContext, AgentNode |
| AI (agents) | Claude via pydantic-ai | `ModelProvider.ANTHROPIC` |
| AI (tool loop) | `anthropic` SDK directly | Project B only — learn the loop by hand |
| AI (cheap/narrow + local) | `claude-haiku-4-5-20251001` or local Ollama | Critics, classification, episode-write; routing decided by Project H |
| AI (frontier-only) | Claude | Project G consolidation — never local *(D35)* |
| Embeddings | Voyage AI `voyage-2` (default); local options evaluated in H | See model reference in `master-plan.md` |
| Search | Tavily | Built for agents |
| Database | PostgreSQL + pgvector | Local or managed — same queries |
| Async | Celery + Redis | Configured |
| Env mgmt | `uv` | In use |
| Prompts | `.j2` via PromptManager | Always — never hardcode *(D34)* |
| Testing | pytest + fixtures | Core locked in Phase 0; per-project after |
| Harness | Mac Mini + Caddy + async Claude Code | Remote-triggered dev |
| Networking — public | Caddy + Cloudflare DNS (port 80/443) | `learn-agentic-ai.com` and public blog |
| Networking — private | Tailscale (free Personal plan) | All private tooling — no open ports |
| Web extraction — default | trafilatura | Free, local, fast |
| Web extraction — fallback | Firecrawl (free tier 500 credits/month) | JS-heavy pages; full-site `/crawl` for bulk ingestion |
| Deployment injection | config only, never code | model routing + persistence *(D33)* |

### Rust Reference Implementations

Three completed portfolio Rust projects serve as implementation references. Python brain stays Python; Rust shell stays Rust.

| Project | What it demonstrates | Most relevant to |
|---|---|---|
| `rag-engine-rs` | Two-stage hybrid retrieval (semantic + keyword re-rank), bounded-concurrency embedding pipeline, Ollama local inference, pgvector via Diesel. 19 tests, CI clean. | **Project D** `RetrieveChunksNode` two-stage pattern; `EmbeddingService` concurrency model |
| `claude-sdk-rs` | Typed async Rust SDK: `Config` → CLI flag mapping, `QueryBuilder`, streaming via `futures::Stream`, session continuity (`--resume`), structured error codes. v2.0.0 on crates.io, 149 tests. | **Rust appliance shell** CLI interaction model |
| `workflow-engine-rs` | Compile-time-validated workflow graphs, multi-transport MCP client (HTTP/WS/stdio), real tiktoken token counting, Handlebars prompt templating. 717 tests, zero clippy warnings. | **Future MCP integration**; **Rust appliance shell** workspace structure |

### Red Flags

- Hardcoding a system prompt in Python (use `.j2`). *(D34)*
- Not storing embeddings at write time (you'll regret it at Project F).
- Skipping the self-critic loop in Project A (it's the point).
- Using `AgentNode` in Project B (use raw SDK — earn the abstraction).
- Building the hardened Project B before a real prospect makes you want more.
- Shipping a workflow without its tests.
- Treating "one more project" as the thing standing between you and ready.
- Building Project H as a runtime router instead of an offline eval tool. *(D33 / D8 orchestrator)*
- Reaching for Rust where Python is sufficient. *(CLAUDE.md)*
- Writing `if running_locally:` inside a brain node. *(D33)*
- Letting the privacy pitch drift into absolutism ("nothing ever leaves") — consolidation stays on Claude. *(D35)*

---

*For state: open `status.md`. For the full project sequence and project specs: open `master-plan.md`. For why a choice was made: open `decisions/index.md`.*
*Last updated: June 2026.*
