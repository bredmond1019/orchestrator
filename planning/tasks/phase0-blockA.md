# Task Spec — Phase 0, Block A

## Goal
Own the core engine mentally and establish digital presence with three foregrounded case studies.

## Context Pointers
- **Master Plan:** Phase 0 → Foundation Block A (Digital Presence + Codebase Ownership)
- **Projects Plan:** Part 1 (Component Reference), Part 2 (Phase 0 Codebase Orientation — the five questions)
- **Repo files to read:** `app/core/workflow.py`, `app/core/task.py`, `app/core/nodes/agent.py`, `app/core/nodes/parallel.py`, `app/core/nodes/router.py`, `app/core/schema.py`, `app/core/validate.py`, `app/services/prompt_loader.py`, and the Customer Care workflow under `app/workflows/customer_care_workflow*`
- **CLAUDE.md:** standing rules, known bugs table, build/run commands

---

## Step-by-Step Tasks

### 1. Read the core engine — deep read, not a skim
- Open `app/core/workflow.py`. Read `run()` line by line: why does validation happen in `__init__`, not `run()`? How does the `while current_node_class:` loop advance? Where does routing happen?
- Open `app/core/task.py`. Understand `TaskContext`: what fields it carries, how `update_node` writes state, why it's passed by reference.
- Open `app/core/nodes/agent.py`. Understand `AgentConfig` and how it maps to a pydantic-ai `Agent`. Where does the provider switch happen? What does `OutputType` do?
- Open `app/core/nodes/parallel.py`. How does `ThreadPoolExecutor` run nodes? Where is the gap (parallel results not merged back cleanly)?
- Open `app/core/nodes/router.py`. How does `BaseRouter` match conditions? What happens on no-match?
- Open `app/core/schema.py`. What does `WorkflowSchema` contain? What is `NodeConfig`?
- Open `app/core/validate.py`. DFS cycle detection + BFS reachability — trace both paths.
- Open `app/services/prompt_loader.py`. How does `PromptManager` load and render a `.j2` file? What does the frontmatter do?

### 2. Read the Customer Care reference workflow
- Read `app/workflows/customer_care_workflow.py` — how `WorkflowSchema` is wired; where `start`, `nodes`, `connections` are declared.
- Read `app/workflows/customer_care_workflow_nodes/analyze_ticket_node.py` — how `ParallelNode` is used in practice.
- Read `app/workflows/customer_care_workflow_nodes/ticket_router_node.py` — how a `RouterNode` subclass is written.
- Read `app/workflows/customer_care_workflow_nodes/generate_response_node.py` — how `AgentNode` + `PromptManager` wire together.
- Read `app/schemas/customer_care_schema.py` — the event schema pattern.
- Read one `.j2` prompt file in `app/prompts/` — understand the frontmatter + Jinja2 body.
- **Do not extend or modify any of this.** Read only.

### 3. Run the Customer Care workflow end-to-end
- Start the Docker stack: `cd docker && ./start.sh`
- Apply DB migrations: `cd app && alembic upgrade head`
- POST a sample event (e.g. `requests/events/refund.json`) via `python requests/send_event.py` or curl.
- Tail the Celery worker logs to watch each node execute: `cd docker && ./logs.sh`
- Inspect the `task_context` JSON written to Postgres for the resulting `Event` row.
- Trace every hop: FastAPI endpoint → Celery queue → worker → WorkflowRegistry → Workflow.run() → each node → DB write.

### 4. Draw the architecture from memory and answer the five questions
- Close all files. On paper or whiteboard, draw the three-tier diagram: Infrastructure / Core Engine / Support Services, with every component and its connections.
- Answer these five without looking:
  1. A workflow has 5 nodes. Node 3 needs data Node 1 produced. How does it access it?
  2. Two nodes run in parallel then merge. Which node type, and what's the thread-safety consideration?
  3. Branch: content is "spam" → node A, else → node B. How?
  4. Iterate a system prompt without restarting the server — how does PromptManager enable this?
  5. A request hits the API. Walk every step until the result is in the DB.
- If any answer feels uncertain, re-read the relevant file and try again.

### 5. LinkedIn overhaul
- **Headline:** `AI / Agentic Systems Engineer | Multi-agent pipelines, orchestration & agentic harnesses | São Paulo`
- **About section:** the through-line arc (Dashboard → Helpscout → AI Scribe → early Claude Code/Aider → now). Teacher and builder, decade of shipping software, bilingual, rooted in São Paulo, open to local roles and consulting. Lead with the work, not the pivot.
- **Foreground the three case studies with real numbers:**
  - Internal Support Dashboard: 100+ daily cross-functional users, cut support wait 24–48hr, still in daily use.
  - Helpscout Support Automation: RAG + vector + semantic search in production, solo.
  - AI Scribe: contributed heavily to production healthcare AI through and past launch (frame as contribution, not sole architect).
- **Master's in Pure Mathematics** prominently.
- Follow the public narrative rule: Brandon/work/reasons as subject; never describe the company's conduct; never name the company.

### 6. GitHub cleanup
- Archive stale repos that don't represent current work.
- **Pin** the Python orchestration engine repo (and the Rust engine once you've done your walk-through review).
- **De-feature** (unpin, update descriptions) the Rust SDK and Python agent library — they become blog post material, not portfolio pins.
- Rewrite the GitHub profile README around the through-line arc.
- Create an empty `agentic-portfolio` repo (public, with a stub README) to signal active work.

### 7. Validate
- Run the Validation Commands listed below and confirm all pass.

---

## Acceptance Criteria
- Can draw the three-tier architecture (Infrastructure / Core Engine / Support Services) from memory with every component and connection, without looking.
- Can answer all five orientation questions (Step 4) from memory without hesitation.
- Have traced a real event through the Customer Care workflow end-to-end and can describe each hop.
- LinkedIn headline, About section, and three case studies (with numbers) are live.
- GitHub profile README reflects the through-line arc; orchestration engine repo is pinned; stale repos archived.
- `uv run pylint app/` and `uv run pytest` pass cleanly (no regressions introduced).
- The app and worker modules import cleanly (see Validation Commands).

---

## Validation Commands
```
uv run pylint app/
uv run pytest
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
```

---

## Notes
*(filled in as work happens)*
