# Update Docs — Sync STATUS.md and append a DEVLOG entry for completed work.

## Instructions

1. Read `planning/STATUS.md` and the current task spec in `planning/tasks/`.
2. Run `git diff --stat` and `git log --oneline -10` to see what changed.
3. Update `planning/STATUS.md`:
   - Flip any newly-completed block statuses to `done`.
   - Update the **Current focus** line to the next block.
   - Bump the **Last updated** date.
   - Append to the **Decisions & Deviations** log if reality diverged from the plan.
4. Append a new dated entry to `DEVLOG.md` in this exact format:
   ```
   ## YYYY-MM-DD

   <One paragraph of prose: what was built or changed, why, and any notable decisions or surprises.>

   ```diff
   <git diff --stat output, pasted verbatim>
   ```
   ```
5. If a settled architectural choice was made during this work, **prompt the user to add it to `planning/DECISIONS.md`** — do not edit DECISIONS.md yourself.
6. Never edit the master plan files (`Master_Plan_2026.md`, `Agentic_Engineering_Projects_and_Learning_Plan.md`).

## Context / Files to Read

- `planning/STATUS.md`
- The current `planning/tasks/phaseN-blockX.md`
- `DEVLOG.md`
