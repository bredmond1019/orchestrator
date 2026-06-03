# Build — Implement a task directly without creating a plan first.

## Variables

$ARGUMENTS — description of the task to implement.

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user to describe the task.
2. Run `/prime` to orient to the codebase before touching any code.
3. Read and understand the task in `$ARGUMENTS`.
4. THINK HARD: is this task well-scoped enough to build without a plan? If it involves a new workflow, a multi-phase feature, or significant new schema/API surface, suggest `/feature` or `/plan` instead. Otherwise proceed.
5. Implement the solution directly:
   - Follow existing code patterns and conventions (see CLAUDE.md).
   - Never hardcode a system prompt in Python — use `.j2` files in `app/prompts/` via `PromptManager`.
   - Every new workflow must ship with tests.
   - Register any new workflow in `app/workflows/workflow_registry.py`.
6. Run the standard validation checks:
   ```
   uv run pylint app/
   uv run pytest
   cd app && uv run python -c "from main import app"
   cd app && uv run python -c "from worker.config import celery_app"
   ```
7. If any check fails, fix it before reporting.
8. Show the proposed commit message and ask for confirmation, then commit (single commit, conventional format).

## Context / Files to Read

- `CLAUDE.md` (standing rules and known bugs)
- Files relevant to the task (read as needed)

## Report

- Concise bullet list of what was built or changed.
- List of all files created or modified.
- Output of `git diff --stat`.
- Any important decisions or trade-offs.
- Any follow-up tasks that may be needed.
