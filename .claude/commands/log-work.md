# Log Work — Sync STATUS.md and append a DEVLOG entry for completed work.

## Variables

$ARGUMENTS — optional free-text explanation of what was done today. May be brief ("finished
             the session.py import-time fix") or detailed (several sentences). If provided,
             it is woven into the DEVLOG prose entry as the primary narrative — do not
             discard or summarise it down. If omitted, derive the narrative from git history
             and the task spec alone.

## Execution Model

Spawn a Haiku subagent (Agent tool, `model: "haiku"`) to execute all steps below.
Pass the resolved `$ARGUMENTS` value and the complete Instructions section in the subagent prompt.
Return the subagent's result to the user.

## Instructions

1. Read `planning/STATUS.md` and the current task spec at `planning/tasks/phaseN-blockX/tasks.md`.
2. Run `git diff --stat` and `git log --oneline -10` to see what changed.

3. **Determine STATUS.md changes — ask before writing if uncertain.**
   - From git history, the task spec, and `$ARGUMENTS`, identify which blocks are newly complete
     and what the next focus should be.
   - If you are confident (e.g. a block's acceptance criteria are clearly met and git confirms
     it), state the proposed changes and proceed.
   - If you are NOT certain which block(s) to flip to `done`, or which block becomes the new
     current focus, STOP and ask the user:
     > "Before I update STATUS.md, I want to confirm: should I mark [block X] as done and
     > set the current focus to [block Y]? Or did something differ from the plan?"
     Wait for confirmation before writing any STATUS.md changes.
   - Changes to make once confirmed:
     - Flip newly-completed block statuses to `done`.
     - Update the **Current focus** line to the next block.
     - Bump the **Last updated** date.
     - Append to the **Decisions & Deviations** log if reality diverged from the plan.

4. Append a new dated entry to `DEVLOG.md` in this exact format:
   ```
   ## YYYY-MM-DD

   <One paragraph of prose: what was built or changed, why, and any notable decisions or
   surprises. If $ARGUMENTS was provided, use it as the primary narrative — include the
   user's own words and context, not just what git can infer.>

   ```diff
   <git diff --stat output, pasted verbatim>
   ```
   ```

5. If a settled architectural choice was made during this work, **prompt the user to add it
   to `planning/DECISIONS.md`** — do not edit DECISIONS.md yourself.
6. Never edit the master plan files (`MASTER_PLAN.md`, `Agentic_Engineering_Projects_and_Learning_Plan.md`).

7. **Sync the company brain.** After STATUS.md and DEVLOG.md are confirmed:
   - Read `../docs/projects/python-orchestration.md` in the company brain.
   - Update the **Current Status** date and focus line to match the new STATUS.md state.
   - Update status values in the Phase Progress Table for any rows that changed.
   - Open `../README.md` and update the Quick Status section for python-orchestration-system:
     the Current focus line and any changed status rows.
   - Surgical updates only — do not rewrite sections that didn't change.
   - If the brain docs are already in sync with STATUS.md, skip this step silently.

## Context / Files to Read

- `planning/STATUS.md`
- The current `planning/tasks/phaseN-blockX/tasks.md`
- `DEVLOG.md`
- `../docs/projects/python-orchestration.md` (brain sync target)
- `../README.md` (brain sync target)
