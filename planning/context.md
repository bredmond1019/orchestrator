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
| `master-plan.md` | Phase sequence, Diagnostic relationship, links to brain | When choosing what to work on |
| `Test_Plan.md` | Testing scope and standards (Option A) | Before writing or reviewing tests |
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

1. **Every workflow ships with tests.** See `Test_Plan.md` for scope. *(D6)*
2. **No hardcoded system prompts.** All prompts are `.j2` files in `app/prompts/` loaded via `PromptManager`. *(D8)*
3. **No deployment logic inside nodes.** Model choice and persistence are injected via config. *(D7, D16)*
4. **`customer_care` is reference-only.** Do not extend it or add tests for it. New workflows go alongside it. *(CLAUDE.md)*
5. **Top-tier models first; measure before switching to local.** Project H owns that measurement. *(D9)*
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

*For state: open `status.md`. For the full project sequence and Diagnostic alignment: open `master-plan.md`. For why a choice was made: open `decisions/index.md`.*
*Last updated: June 2026.*
