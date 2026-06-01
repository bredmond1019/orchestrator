# Review Task — Assess progress against the current task spec.

## Instructions

1. Read `planning/STATUS.md` to find the current block identifier.
2. Check whether the matching task spec exists in `planning/tasks/`. If no spec file exists for the current block, say so plainly and suggest running `/next-task` — do not fabricate a review.
3. Read the matching task spec file in `planning/tasks/` (e.g. `planning/tasks/phaseN-blockX.md`).
4. Read actual repo state for the files relevant to that spec (check `git status` and the Context Pointers section of the spec).
5. For each Step-by-Step task in the spec, report whether it appears **Done** or **Outstanding**, with one-sentence evidence.
6. Flag any drift from the Acceptance Criteria.
7. Do not edit any file. This command is read-only.

## Context / Files to Read

- `planning/STATUS.md`
- The current `planning/tasks/phaseN-blockX.md`
- Repo files named in the spec's Context Pointers (only those)
