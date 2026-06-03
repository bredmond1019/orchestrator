# Implement — Execute a plan file against the codebase.

## Variables

$ARGUMENTS — path to the plan file to implement (e.g. `planning/tasks/feature-summarizer.md`).

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user for the plan file path.
2. Run `/prime` to orient to the codebase before touching any code.
3. Read the plan file at `$ARGUMENTS` in full.
4. THINK HARD about the plan: understand the goal, relevant files, and each step before writing anything.
5. Execute every Step-by-Step task in the plan in order, top to bottom:
   - Follow existing code patterns and conventions (see CLAUDE.md).
   - Never hardcode a system prompt in Python — use `.j2` files in `app/prompts/` via `PromptManager`.
   - Every new workflow must ship with tests.
   - Register any new workflow in `app/workflows/workflow_registry.py`.
6. After all steps, run the plan's Validation Commands exactly as written. If no plan-specific commands exist, run the standard checks:
   ```
   uv run pylint app/
   uv run pytest
   cd app && uv run python -c "from main import app"
   cd app && uv run python -c "from worker.config import celery_app"
   ```
7. If validation fails, fix the failure before reporting.
8. Report the completed work (see Report).

## Context / Files to Read

- `$ARGUMENTS` (the plan file)
- `CLAUDE.md` (standing rules)
- Files listed in the plan's Relevant Files section

## Report

- Concise bullet list of what was built or changed.
- List of all files created or modified.
- Output of `git diff --stat`.
- Any important decisions or trade-offs made.
- Any follow-up work needed (do not invent scope beyond the plan).
