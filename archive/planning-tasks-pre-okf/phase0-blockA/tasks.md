---
type: Specification
title: Phase 0, Block A
description: Establish digital presence with case studies foregrounded and achieve genuine ownership of the or...
---

# Task Spec — Phase 0, Block A

## Goal
Establish digital presence with case studies foregrounded and achieve genuine ownership of the orchestration framework's core engine.

## Context Pointers
- **Master Plan:** Phase 0 → Foundation Block A (Technical + Visibility sections)
- **Projects Plan:** Part 2 — Phase 0 Codebase Orientation (Steps 1–4, the five questions)
- **Key repo files:** `app/core/workflow.py`, `app/core/task.py`, `app/core/nodes/agent.py`, `app/core/nodes/parallel.py`, `app/core/nodes/router.py`, `app/core/schema.py`, `app/core/validate.py`, `app/services/prompt_loader.py`, `app/workflows/customer_care_workflow.py`
- **CLAUDE.md:** Standing rules (no hardcoded prompts, `customer_care` is reference-only, deployment decisions injected via config)
- **DECISIONS:** D18 (two injection points), D23 (two-face Mini architecture), D9 (case studies as pre-existing evidence)

---

## Step-by-Step Tasks

### 1. Read the core engine — `workflow.py` and `task.py`
- Open `app/core/workflow.py` and read every line. Understand the `while current_node_class:` DAG-walk loop in `run()`, the schema validation on `__init__`, and how routing is handled.
- Open `app/core/task.py`. Understand `TaskContext` as shared pipeline state, how `update_node(name, **kwargs)` works, and the `nodes` dict as a downstream-readable ledger.
- Note: confirm `Workflow.run()` does not hardcode any model or persistence detail — both should come from node config and `GenericRepository` respectively. (This is the D18 reconnaissance.)

### 2. Read `AgentNode` and support nodes
- Read `app/core/nodes/agent.py` line by line. Understand `AgentConfig`, `ModelProvider` enum, how pydantic-ai's `Agent` is wrapped, `OutputType` structured output, and `DepsType` context injection.
- Read `app/core/nodes/parallel.py`. Note the `ThreadPoolExecutor` pattern and the known gap: parallel nodes mutate shared `task_context` directly; results list is discarded. This is the gap fixed in Project E.
- Read `app/core/nodes/router.py`. Understand `BaseRouter` + `RouterNode` declarative pattern; first-match wins, `fallback` on no-match.
- Read `app/core/schema.py`. Understand `WorkflowSchema(start, nodes)` and `NodeConfig(node, connections, is_router)`.
- Read `app/core/validate.py`. Understand DFS cycle detection + BFS reachability, and that this runs on every `Workflow.__init__()`.
- Read `app/services/prompt_loader.py`. Understand Jinja2 + YAML frontmatter `.j2` loading, `get_prompt(name, **vars)`.

### 3. Read the Customer Care reference implementation
- Read `app/workflows/customer_care_workflow.py` — the `WorkflowSchema` wiring, how `ParallelNode` is used for the three parallel analysis nodes, and the router setup.
- Skim `app/workflows/customer_care_workflow_nodes/*.py` — enough to understand how `AgentNode` is subclassed, how prompts are loaded via `PromptManager`, and how `task_context.update_node(...)` is called.
- Read `app/schemas/customer_care_schema.py` — the Pydantic event schema pattern.
- **Do not extend or modify any of these files.**

### 4. Run the Customer Care workflow end-to-end
- Ensure Docker is running: `cd docker && ./start.sh`
- Apply migrations: `cd app && uv run alembic upgrade head`
- Start the API and worker (two separate terminals): `cd app && uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload` and `cd app && uv run celery -A worker.config.celery_app worker --loglevel=info`
- POST a sample event: `python requests/send_event.py` (or `curl` with one of the payloads in `requests/events/`)
- Watch the Celery worker output. Trace every step: FastAPI → DB persist → `send_task` → worker → `WorkflowRegistry` lookup → `Workflow.run()` → each node → `task_context` updates.
- Inspect the stored `task_context` JSON in Postgres to confirm the full ledger.

### 5. Confirm the two injection points (D18 reconnaissance)
- In `AgentNode`, verify that `model_provider` and `model_name` come from `AgentConfig` — not hardcoded per-node.
- In the workflow and nodes, verify that all persistence goes through `GenericRepository` — no direct session/DB calls inside node `process()` methods.
- Write down the result: "injection points confirmed" or note any violation found. This is the architectural prerequisite for the one-brain-two-shells design.

### 6. Answer the five orientation questions (close all files first)
Without looking at code, answer these in writing (a scratch document, a notebook, anywhere):
1. A workflow has 5 nodes. Node 3 needs data Node 1 produced. How does it access it?
2. Two nodes run in parallel then merge. Which class, and what is the thread-safety consideration?
3. Branch on content type: if "spam" go to node A, else node B. How is this implemented?
4. Iterate a system prompt without restarting the server — how does `PromptManager` enable this?
5. A request hits the API. Walk every step until the result is stored in the DB.

Draw the three-tier architecture diagram on your whiteboard without looking: Infrastructure tier, Core Engine tier, Support Services tier — with every named component and the data/control flow arrows.

If you can answer all five and draw the diagram, Phase 0 orientation is complete.

### 7. LinkedIn overhaul
- Update headline: `AI / Agentic Systems Engineer | Multi-agent pipelines, orchestration & agentic harnesses | São Paulo`
- Rewrite About section: the through-line arc (teacher and builder → shipped Internal Support Dashboard → Helpscout RAG automation → AI Scribe → agentic/harness engineering). Bilingual framing. Open to São Paulo roles and consulting.
- Foreground the three case studies with real numbers: Internal Support Dashboard (100+ daily users, 24–48hr wait-time reduction, still in daily use), Helpscout Automation (RAG + vector + semantic in production), AI Scribe (production healthcare AI, 4+ months ownership post-launch).
- Master's in Pure Mathematics, prominently.
- Review the public-narrative rule (Master Plan, "The Public Narrative Principle") — make yourself and your work the subject of every sentence. No company names in prose.

### 8. GitHub cleanup
- Archive stale / slop repos that are not portfolio-grade.
- Pin the Python orchestration engine repo and the Rust engine (pending walk-through review — only after confirming you can defend every design decision; do not pin it if not reviewed).
- De-feature (unpin / set to private) the Rust SDK and Python agent library built quickly in 2025.
- Rewrite the GitHub profile README around the through-line arc (same story as LinkedIn About, code-audience voice).
- Create an empty `agentic-portfolio` repository (public, no content yet — placeholder for the portfolio index).

### 9. Validate
- Run the Validation Commands listed below and confirm all pass.

---

## Acceptance Criteria
- All five orientation questions answered correctly from memory (no peeking).
- Architecture diagram drawn from memory covers all three tiers with named components and correct data-flow arrows.
- D18 reconnaissance complete: both injection points (`model_provider` via `AgentConfig`, persistence via `GenericRepository`) confirmed present and not violated.
- Customer Care workflow ran end-to-end at least once; `task_context` JSON inspected in Postgres and traced to every node output.
- LinkedIn: headline updated, About written with through-line arc and three case studies with real numbers; public-narrative rule followed.
- GitHub: stale repos archived, profile README rewritten, `agentic-portfolio` repo created.
- `uv run pylint app/` exits clean (no new errors introduced).
- `cd app && uv run python -c "from main import app"` succeeds.
- `cd app && uv run python -c "from worker.config import celery_app"` succeeds.

---

## Validation Commands
```bash
uv run pylint app/
uv run pytest
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
```

---

## Notes
*(filled in as work happens)*
