# Feature — Create a comprehensive plan to implement a new feature.

## Variables

$ARGUMENTS — description of the feature to plan.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user to describe the feature.
2. THINK HARD about the feature's scope, design, and how it fits the existing system before writing anything.
3. Research the codebase: read `CLAUDE.md` and `docs/app-architecture-overview.md`, then any files directly relevant to the feature.
4. Create a plan using the Plan Format below.
5. Save it to `planning/tasks/feature-{descriptive-name}.md` where `{descriptive-name}` is a short slug (e.g. `add-summarizer-workflow`, `implement-retry-logic`, `add-webhook-events`).
6. Return only the path to the file created.

## Codebase Structure

- `CLAUDE.md` — standing rules, known bugs, build/test/run commands (start here)
- `docs/app-architecture-overview.md` — system architecture reference
- `app/` — FastAPI app (`main.py`), Celery worker (`worker/`), core utilities (`core/`)
- `app/workflows/` — workflow DAGs and per-workflow node directories
- `app/schemas/` — Pydantic event schemas
- `app/prompts/` — Jinja2 prompt templates (never hardcode prompts in Python)
- `app/api/` — FastAPI routes and endpoints
- `app/database/` — SQLAlchemy models, sessions, repository
- `app/workflows/workflow_registry.py` — register every new workflow here
- `planning/tasks/` — task specs and plan files

## Plan Format

```md
# Feature: <feature name>

## Metadata
prompt: `{$ARGUMENTS}`

## Feature Description
<describe the feature in detail — what it does, why it's needed, who/what benefits>

## User Story
As a <type of user or system component>
I want to <action or goal>
So that <benefit or outcome>

## Problem Statement
<the specific problem or gap this feature addresses>

## Solution Statement
<the proposed approach and why it fits this codebase's patterns>

## Relevant Files
<list files relevant to the feature with bullet points explaining why each is needed>

### New Files
<list all new files to be created with a one-line description of each>

## Implementation Plan

### Phase 1: Foundation
<schema changes, new Pydantic models, migrations, scaffolding — anything that must land first>

### Phase 2: Core Implementation
<the workflow nodes, service logic, prompt templates, and main business logic>

### Phase 3: Integration
<API wiring, worker task registration, workflow registry, end-to-end hookup>

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.
Include writing tests throughout — do not leave them to the end.

### 1. <First Task Name>
- <specific action>
- <specific action>

### 2. <Second Task Name>
- <specific action>

### N. Validate
- Run the Validation Commands listed below and confirm all pass.

## Testing Strategy

### Unit Tests
<list the unit tests to write and what each should cover>

### Edge Cases
<list edge cases that must be tested>

## Acceptance Criteria
<list specific, measurable conditions that must be true for the feature to be done>

## Validation Commands
```
uv run pylint app/
uv run pytest
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
```
<add any feature-specific end-to-end or integration checks above the four standard lines>

## Notes
<dependencies, new libraries needed (`uv add <pkg>`), future considerations, known constraints>
```

## Report

Output the path to the plan file created and the next-step options:
```
planning/tasks/feature-{name}.md

Next (optional — decompose into atomic sub-steps):
  /breakdown planning/tasks/feature-{name}.md

Next (skip breakdown — implement directly):
  /implement planning/tasks/feature-{name}.md
```
