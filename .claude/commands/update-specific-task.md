# Update Specific Task — Record progress in a named task spec.

## Variables

$ARGUMENTS — space-separated values in this order:
  1. Target spec identifier, e.g. `phase0-blockC` (optional — if omitted, you MUST ask before proceeding).
  2. Step number to mark done, e.g. `3`. Pass `0` to append a note without marking a step done.
  3. Note text (everything after the step number) to append to the spec's `## Notes` section.

Examples:
  `/update-specific-task phase0-blockC 2 Fixed the import-time side effect in session.py`
  `/update-specific-task phase0-blockC 0 Still investigating the ghost-row bug`
  `/update-specific-task 2 Finished scaffolding`   ← no spec given; must ask before acting

## Instructions

1. **Resolve the target spec.**
   - If a spec identifier was provided in `$ARGUMENTS` (first token matching `phaseN-blockX`
     or `phaseN-projectY`), normalise it to the filename form `phaseN-blockX.md` and verify
     the file exists at `planning/tasks/phaseN-blockX.md`.
   - If NO spec identifier is present, stop and ask:
     "Which task spec should I update? (e.g. phase0-blockC) — I will not assume."
     Wait for the user's reply before continuing.
   - If the resolved file does not exist, stop and say:
     "No spec found at planning/tasks/<name>.md — run `/generate-tasks <name>` to create it."

2. Read the resolved task spec file.

3. Parse the remaining arguments for step number and note text:
   - Step number: first integer token after the spec identifier (or first token if no spec was
     given and the user has since confirmed). `0` means note-only.
   - Note text: all remaining text after the step number. May be empty.

4. If a non-zero step number was given, mark that step heading done by prepending `✅` to the
   matching `### <N>.` line. If the step is already marked done, report that and skip.

5. If note text was provided, append it to the `## Notes` section of the spec, prefixed with
   today's date:
   ```
   **YYYY-MM-DD**: <note text>
   ```

6. Write the updated spec back. Preserve all other content and formatting exactly.

7. Report what changed (see Report).

## Context / Files to Read

- The named `planning/tasks/phaseN-blockX.md` (resolved in step 1)
- Do NOT read `planning/STATUS.md` — the target is given explicitly (or confirmed by the user).

## Report

- Which spec was updated (full relative path).
- Which step was marked done (if any), or "no step marked" if step was 0.
- The note appended (if any), or "no note added".
- One-line success or failure of the file write.
