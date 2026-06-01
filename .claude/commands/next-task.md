# Next Task — Generate a task spec for the current/next block.

## Instructions

1. Read `planning/STATUS.md` to identify the current or next block (first item that is not `done`). If all blocks are `done`, say so and stop — do not invent a new block.
2. Read ONLY the relevant section for that block in:
   - `planning/Master_Plan_2026.md` (the phase/block definition)
   - `planning/Agentic_Engineering_Projects_and_Learning_Plan.md` (the matching project section)
3. THINK HARD about correct scope:
   - Do not invent work beyond what the block defines.
   - Size tasks to roughly 21 hours spread across Mon/Wed/Fri sessions.
   - Every workflow task must include writing tests (standing rule from CLAUDE.md).
   - Foundational steps come first; the final step validates.
4. Write the spec to `planning/tasks/phaseN-blockX.md` using the Output Format below.
5. Return only the path to the file created.

## Context / Files to Read

- `planning/STATUS.md`
- `planning/Master_Plan_2026.md` (relevant block section only)
- `planning/Agentic_Engineering_Projects_and_Learning_Plan.md` (relevant project section only)

## Output Format

```md
# Task Spec — Phase <N>, <Block/Project> <X>

## Goal
<one sentence, taken directly from the plan>

## Context Pointers
<which plan sections are relevant + which repo files / CLAUDE.md sections apply>

## Step-by-Step Tasks

### 1. <Foundational step>
- <bulleted actions>

### 2. <Next step>
- <bulleted actions>

<!-- ... continue; last step is always validation -->

### N. Validate
- Run the Validation Commands listed below and confirm all pass.

## Acceptance Criteria
- <specific, measurable condition>
- <specific, measurable condition>

## Validation Commands
```
uv run pytest
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
```
<!-- Add any workflow- or feature-specific checks above the three standard lines. -->

## Notes
<filled in as work happens>
```

## Report

Return only the path to the file created (e.g. `planning/tasks/phase1-block2.md`).
