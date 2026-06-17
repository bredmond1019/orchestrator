# Generate Tasks — Generate a task spec for a specified phase and block.

## Variables

$ARGUMENTS — the target phase and block, e.g. `phase0-blockC` or `phase1-projectA`.
             Required. If omitted, stop and say: "Usage: /generate-tasks <phase>-<block>  (e.g. phase0-blockC)"

## Instructions

1. Run `/prime` to orient to the repo (standing rules, known bugs, architecture).

2. Parse `$ARGUMENTS` to extract the phase number and block/project identifier
   (e.g. `phase0-blockC` → phase 0, block C).
   - Accept any of these forms: `phase0-blockC`, `phase0blockC`, `0-C`, `Phase 0 Block C`.
   - If the argument cannot be parsed into a phase + block, stop and explain the expected format.

3. Check whether a spec already exists at `planning/tasks/phaseN-blockX/tasks.md` (using the
   normalized directory form, e.g. `planning/tasks/phase0-blockC/tasks.md`).
   - If it exists, read it and report: "Spec already exists at <path>. Overwrite? (re-run with
     `--force` appended to overwrite, or run `/breakdown <path>` to decompose it instead.)"
   - If `$ARGUMENTS` contains `--force`, proceed and overwrite.

4. Read ONLY the relevant section for the requested block in:
   - `planning/MASTER_PLAN.md` (the phase/block definition)
   - `planning/Agentic_Engineering_Projects_and_Learning_Plan.md` (the matching project section, if applicable)
   - Do NOT read STATUS.md — the target block is given explicitly.

5. THINK HARD about correct scope:
   - Do not invent work beyond what the block defines.
   - Size tasks to roughly 21 hours spread across Mon/Wed/Fri sessions.
   - Every workflow task must include writing tests (standing rule from CLAUDE.md).
   - Foundational steps come first; the final step is always Validate.

6. Create the directory `planning/tasks/phaseN-blockX/` if it does not exist, then write the spec to `planning/tasks/phaseN-blockX/tasks.md` using the Output Format below.

7. Report the path written and suggest the next step:
   "Spec written to planning/tasks/phaseN-blockX/tasks.md. Run `/breakdown planning/tasks/phaseN-blockX/tasks.md` to decompose into atomic sub-steps."

## Context / Files to Read

- `planning/MASTER_PLAN.md` (target block section only)
- `planning/Agentic_Engineering_Projects_and_Learning_Plan.md` (matching project section only, if applicable)
- `CLAUDE.md` (standing rules — tests, prompt files, workflow registration, known bugs)

## Output Format

```md
---
type: Specification
title: <Block/Project> <X>
description: <one sentence, taken directly from the plan>
---

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
uv run pylint app/
uv run pytest
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
```
<!-- Add any workflow- or feature-specific checks above the four standard lines. -->

## Notes
<filled in as work happens>
```

## Report

Output the path to the file created and the next-step options:
```
planning/tasks/phase0-blockC/tasks.md

Next (optional — decompose into atomic sub-steps):
  /breakdown planning/tasks/phase0-blockC/tasks.md

Next (skip breakdown — implement directly):
  /implement planning/tasks/phase0-blockC/tasks.md
```
