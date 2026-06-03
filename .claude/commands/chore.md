# Chore — Plan a maintenance or housekeeping task.

## Variables

$ARGUMENTS — description of the chore to plan.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user to describe the chore.
2. Research the codebase: read `CLAUDE.md`, then any files directly relevant to the chore.
3. Create a plan using the Plan Format below.
4. Save it to `planning/tasks/chore-{descriptive-name}.md` where `{descriptive-name}` is a short slug based on the chore (e.g. `fix-session-import`, `update-router-keys`, `add-missing-indexes`).
5. Return only the path to the file created.

## Codebase Structure

- `CLAUDE.md` — standing rules, known bugs, build/test/run commands (start here)
- `app/` — FastAPI app (`main.py`), Celery worker (`worker/`), core utilities (`core/`)
- `app/workflows/` — workflow DAGs and per-workflow node directories
- `app/schemas/` — Pydantic event schemas
- `app/prompts/` — Jinja2 prompt templates (never hardcode prompts in Python)
- `app/api/` — FastAPI routes and endpoints
- `app/database/` — SQLAlchemy models, sessions, repository
- `planning/tasks/` — task specs (plan files live here)
- `docker/` — Docker stack (`start.sh` / `stop.sh`)

## Plan Format

```md
# Chore: <chore name>

## Metadata
prompt: `{$ARGUMENTS}`

## Chore Description
<describe the chore in detail — what it is, why it matters, any known constraints>

## Relevant Files
<list files relevant to the chore with bullet points explaining why each is needed>

### New Files
<list any new files that will be created, if applicable>

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. <First Task Name>
- <specific action>
- <specific action>

### 2. <Second Task Name>
- <specific action>

### N. Validate
- Run the Validation Commands listed below and confirm all pass.

## Validation Commands
```
uv run pylint app/
uv run pytest
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
```
<add any chore-specific checks above the four standard lines>

## Notes
<optional context, edge cases, or gotchas>
```

## Report

Return only the path to the plan file created.
