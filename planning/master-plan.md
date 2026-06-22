---
type: Plan
title: Python Orchestration System — Master Plan
description: What this project builds, the phase/project sequence, how B+C+D relate to The Diagnostic, and links to brain for business/career context.
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

- **D6 — Every workflow ships with tests.** No exceptions. See `Test_Plan.md` for scope.
- **D8 — All prompts are Jinja2 `.j2` files** in `app/prompts/`, loaded via `PromptManager`. Never hardcode a system prompt in Python.
- **D7 / D16 — No deployment logic inside nodes.** This framework is deployment-agnostic. Model choice and persistence are injected via config, never hardcoded in a node.
- **D9 — Top-tier models first.** Introduce local/open-weight model swaps via Project H after measuring.

---

## Strategy & Career Context

Business goals, contracting strategy, leads, and career posture live in the company brain:

- Career strategy: `agentic-portfolio/docs/career.md`
- Content plan: `agentic-portfolio/docs/content/ideas.md`
- Lead pipeline: `agentic-portfolio/docs/business/pipeline.md`
- The Diagnostic productized service: `agentic-portfolio/planning/the-diagnostic/plan.md`

---

*Last updated: June 2026. For the previous version's strategic arc and case studies, see `docs/career.md` in the brain.*
