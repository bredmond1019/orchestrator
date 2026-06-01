# Validate Task — Run validation commands and check acceptance criteria.

## Instructions

1. Read `planning/STATUS.md` to find the current block identifier.
2. Check whether the matching task spec exists in `planning/tasks/`. If no spec file exists for the current block, say so plainly and suggest running `/next-task` — do not attempt to validate.
3. Read the matching task spec in `planning/tasks/phaseN-blockX.md`.
4. Run every command listed in the spec's **Validation Commands** section exactly as written.
5. For each **Acceptance Criterion**, report **PASS** or **FAIL** with the evidence (command output or file check).
6. Do not declare any criterion done if its command fails or its condition is unmet.
7. Do not edit any file. Summarize results as a PASS/FAIL table.

## Context / Files to Read

- `planning/STATUS.md`
- The current `planning/tasks/phaseN-blockX.md`
