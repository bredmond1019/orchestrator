# CLAUDE.md — Orchestration Repo

Event-driven AI pipeline framework: FastAPI → Celery → Workflow DAG → TaskContext.

## Before you start

- **Strategic context:** `planning/CONTEXT.md` (read first) → `planning/STATUS.md` (current state)
- **Architecture reference:** `docs/app-architecture-overview.md`
- **Decisions log:** `planning/DECISIONS.md` — check before relitigating any settled choice

---

## Standing rules

1. **Every new workflow ships with tests.** No exceptions. See `planning/Test_Plan.md` for scope (Option A).
2. **Never hardcode a system prompt in Python.** All prompts are `.j2` files in `app/prompts/`, loaded via `PromptManager`.
3. **`customer_care` is reference-only.** Do not extend it, add tests for it, or treat it as a pattern to modify. New workflows go alongside it.
4. **New projects = new workflow directories.** Add `app/workflows/<name>_workflow.py` + `app/workflows/<name>_workflow_nodes/` + `app/schemas/<name>_schema.py`. Use `createworkflow` (see below).
5. **Python stays Python.** Do not suggest Rust rewrites of any part of this repo.
6. **Register every new workflow** in `app/workflows/workflow_registry.py`.

---

## Known bugs (unfixed in core — fix these when you touch the relevant code)

| Location | Bug |
|---|---|
| `database/repository.py` `GenericRepository.exists()` | Uses `self.model.query.filter_by(...).exists()` — SQLAlchemy 2.x AttributeError |
| `api/endpoint.py` | Commit happens before `send_task`; if `send_task` fails the row is orphaned (ghost row) |
| `database/session.py` line 15 | `create_engine(...)` runs at import time — side effect on module load |
| `worker/config.py` line 45–46 | `Celery(...)` and `config_from_object(...)` run at import time — side effect on module load |
| Router nodes | Route keys are hard-coded strings; prefer a clear `KeyError` message over a silent miss |

---

## Build / test / run

```bash
# Install dependencies (from repo root)
uv sync

# Run the API (from app/)
cd app && uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# Run the Celery worker (from app/)
cd app && uv run celery -A worker.config.celery_app worker --loglevel=info

# Apply DB migrations (from app/)
cd app && alembic upgrade head

# Lint
uv run pylint app/

# Run tests
uv run pytest

# Full Docker stack
cd docker && ./start.sh    # up (reads docker/.env)
cd docker && ./stop.sh     # down
```

---

## Adding a new workflow

```bash
# From repo root — interactive, prompts for snake_case name
uv run createworkflow
```

This scaffolds:
- `app/workflows/<name>_workflow.py` — Workflow subclass with a stub `WorkflowSchema`
- `app/workflows/<name>_workflow_nodes/__init__.py` + `initial_node.py`
- `app/schemas/<name>_schema.py` — Pydantic event schema

After scaffolding:
1. Fill in the schema fields.
2. Add real nodes under `<name>_workflow_nodes/`.
3. Wire the `WorkflowSchema` (`start`, `nodes`, `connections`).
4. Register in `app/workflows/workflow_registry.py`.
5. Add a `app/prompts/<name>_*.j2` for every system prompt.
6. Write tests before marking the workflow done.

---

## What NOT to touch

- `app/workflows/customer_care_workflow*` — reference implementation, frozen
- `app/core/commands/` — excluded from ruff and pylint, do not reformat
- `app/alembic/` — migration history, excluded from pylint, never hand-edit generated files
