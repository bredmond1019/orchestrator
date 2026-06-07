# Plan — Create a plan for a task, scaled to its complexity.

## Variables

$ARGUMENTS — description of the task to plan.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user to describe the task.
2. THINK HARD about task type and complexity before writing anything:
   - `task_type`: `chore` | `feature` | `refactor` | `fix` | `enhancement`
   - `complexity`: `simple` | `medium` | `complex`
   - Simple tasks (chores, targeted fixes): focus on specific changes and validation.
   - Complex tasks (features, refactors): include design rationale, implementation phases, and testing strategy.
3. Research the codebase: read `CLAUDE.md`, then files directly relevant to the task.
4. Create a plan using the Plan Format below, omitting sections marked as conditional when they don't apply.
5. Save it to `planning/tasks/plan-{descriptive-name}.md` where `{descriptive-name}` is a short slug (e.g. `fix-ghost-row`, `refactor-router-keys`, `add-workflow-logging`).
6. Return only the path to the file created.

## Codebase Structure

- `CLAUDE.md` — standing rules, known bugs, build/test/run commands (start here)
- `app/` — FastAPI app (`main.py`), Celery worker (`worker/`), core utilities (`core/`)
- `app/workflows/` — workflow DAGs and per-workflow node directories
- `app/schemas/` — Pydantic event schemas
- `app/prompts/` — Jinja2 prompt templates (never hardcode prompts in Python)
- `app/api/` — FastAPI routes and endpoints
- `app/database/` — SQLAlchemy models, sessions, repository
- `planning/tasks/` — task specs and plan files

## Plan Format

```md
# Plan: <task name>

## Metadata
prompt: `{$ARGUMENTS}`
task_type: <chore|feature|refactor|fix|enhancement>
complexity: <simple|medium|complex>

## Task Description
<describe the task in detail based on the prompt>

## Objective
<one sentence: what will be true when this plan is fully executed>

<!-- Include for feature/refactor/complex tasks: -->
## Problem Statement
<the specific problem or opportunity this task addresses>

## Solution Approach
<the proposed solution and why it fits the codebase>
<!-- end conditional -->

## Relevant Files
<list files relevant to the task with bullet points explaining why each is needed>

### New Files
<list any new files to be created, if applicable>

<!-- Include for medium/complex tasks: -->
## Implementation Phases
### Phase 1: Foundation
<any foundational work that must land first>

### Phase 2: Core Implementation
<the main body of work>

### Phase 3: Integration & Validation
<integration with existing systems, tests, final checks>
<!-- end conditional -->

## Step by Step Tasks
IMPORTANT: Execute every step in order, top to bottom.

### 1. <First Task Name>
- <specific action>
- <specific action>

### 2. <Second Task Name>
- <specific action>

### N. Validate
- Run the Validation Commands listed below and confirm all pass.

<!-- Include for feature/complex tasks: -->
## Testing Strategy
<unit tests needed; edge cases to cover; any integration test requirements>
<!-- end conditional -->

## Acceptance Criteria
<list specific, measurable conditions that must be true for this task to be done>

## Validation Commands
```
uv run pylint app/
uv run pytest
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
```
<add any task-specific checks above the four standard lines>

## Notes
<optional: dependencies, new libraries needed (`uv add <pkg>`), constraints, follow-ups>
```

## Report

Output the path to the plan file created and the next-step options:
```
planning/tasks/plan-{name}.md

Next (optional — decompose into atomic sub-steps):
  /breakdown planning/tasks/plan-{name}.md

Next (skip breakdown — implement directly):
  /implement planning/tasks/plan-{name}.md
```
