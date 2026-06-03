# Update Task — Record progress in the current task spec.

## Variables

$1 — step number to mark done (e.g. `3`). Pass `0` to only append a note without marking a step.
$ARGUMENTS — the note text to append to the spec's `## Notes` section.

## Instructions

1. Read `planning/STATUS.md` to identify the current block.
2. Find the matching task spec in `planning/tasks/`. If none exists, say so and stop — suggest running `/next-task`.
3. Read the task spec.
4. If `$1` is a non-zero step number, mark that step's heading as done by prepending `✅` to the `### <N>.` line. If the step is already marked done, report that and skip.
5. If note text was provided in `$ARGUMENTS`, append it to the `## Notes` section of the spec, prefixed with today's date:
   ```
   **YYYY-MM-DD**: <note text>
   ```
6. Write the updated spec back. Preserve all other content and formatting.
7. Report what changed (see Report).

## Context / Files to Read

- `planning/STATUS.md`
- The current `planning/tasks/phaseN-blockX.md`

## Report

- Which step was marked done (if any).
- The note appended (if any).
- One-line success or failure of the file write.
