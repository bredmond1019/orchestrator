# Document — Update docs to reflect a completed, reviewed implementation.

Gates on the review verdict being PASS. Uses the implement report's file list to scope
doc updates surgically, without relying on git diff alone.

## Variables

$ARGUMENTS — path to the task spec with optional task number. Same format as `/implement`.

Examples:
- `planning/tasks/phase0-blockC/tasks.md` — document all tasks in the block
- `planning/tasks/phase0-blockC/tasks.md 3` — document task 3 only

## Instructions

1. If `$ARGUMENTS` is not provided, stop:
   > "Usage: /document planning/tasks/<spec>.md [N]"

2. Parse `$ARGUMENTS`: split on the last space. Trailing number = task N; remainder = spec path.

3. Run `/prime` to orient to the codebase before reading any files.

4. **Derive the review report path** (reports live in the spec's `reports/` sibling directory):
   - Plan only: `planning/tasks/phase0-blockC/tasks.md` → `planning/tasks/phase0-blockC/reports/review.md`
   - Plan + task N: `planning/tasks/phase0-blockC/tasks.md 3` → `planning/tasks/phase0-blockC/reports/task3-review.md`

5. Read the review report. Check the **Overall verdict** line.
   **If the verdict is not PASS, STOP immediately:**
   > "Cannot document: review verdict is [FAIL/PARTIAL]. Resolve all blocking issues and
   > re-run `/review-task [args]` until the verdict is PASS."

6. **Derive the implement report path:**
   - Plan only: `planning/tasks/phase0-blockC/tasks.md` → `planning/tasks/phase0-blockC/reports/implement.md`
   - Plan + task N: `planning/tasks/phase0-blockC/tasks.md 3` → `planning/tasks/phase0-blockC/reports/task3-implement.md`

7. Read the implement report. Extract the **Files Created or Modified** table. This is the
   authoritative list of changed source files — do not guess from git or the spec.

8. Read every file in `docs/`. For each doc, check whether it references any of the changed
   source files (look for `**Source:**` annotations, code paths, class/function names that
   appear in the changed files). Build a map: `{ doc_path → [changed_source_files_it_covers] }`.
   If no docs reference any changed file, note "No docs affected" and skip to step 10.

9. For each affected doc + changed source pair:
   a. Read the full current doc and the full changed source file.
   b. Identify only the sections that describe the changed code.
   c. Rewrite those sections to match the source exactly. Leave all other sections untouched.
   d. If a change is too large for surgical patching (e.g. an entire class was replaced),
      flag it as `NEEDS_REVIEW` and skip — do not attempt a full rewrite.

10. Apply all surgical updates.

11. Write the document report and summarize to the user (see Report).

## Rules

- **Surgical only.** Never rewrite a doc section not covered by the changed source files.
- **Source is authoritative.** If the doc and source disagree, the source wins.
- **No invention.** Do not add new sections or cover APIs not already in the doc — that is `/generate-new-docs` territory.
- **Never touch** `planning/`, `DEVLOG.md`, `STATUS.md`, or `CLAUDE.md`.
- **Flag** `docs/app-architecture-overview.md` as `NEEDS_REVIEW` if architecture-level source files changed (files in `app/core/`, `app/worker/config.py`, `app/main.py`). Never edit it automatically.
- **Gate strictly on PASS.** Never run doc updates if the review verdict is not PASS.

## Context / Files to Read

- Review report (derived from $ARGUMENTS) — read first; gate on PASS
- Implement report (derived from $ARGUMENTS) — for the changed file list
- `docs/` — all existing reference docs
- Changed source files identified from the implement report

## Report

**Derive the document report file path** (reports live in the spec's `reports/` sibling directory):
- Plan only: `planning/tasks/phase0-blockC/tasks.md` → `planning/tasks/phase0-blockC/reports/document.md`
- Plan + task N: `planning/tasks/phase0-blockC/tasks.md 3` → `planning/tasks/phase0-blockC/reports/task3-document.md`

Create `planning/tasks/phase0-blockC/reports/` if it does not exist.

**Write the report file in this exact format:**

```markdown
# Document Report — <spec filename> [Task <N> | All Tasks]

**Date:** <YYYY-MM-DD>
**Plan:** <spec file path>
**Scope:** Task <N> | All tasks
**Review verdict confirmed:** PASS
**Implement report read:** <path>
**Source files scanned:** <N>
**Docs updated:** <N>

## Docs Updated

| Doc | Sections Updated |
|---|---|
| docs/api-reference.md | "GenericRepository.exists()" subsection |

## Docs Checked — No Changes Needed

- docs/configuration.md — no references to changed source files

## NEEDS_REVIEW

- docs/app-architecture-overview.md — architecture-level file `app/core/workflow.py` modified; manual review required

## Source Files Covered

| Source File | Action | Docs Updated |
|---|---|---|
| app/database/repository.py | modified | docs/api-reference.md |
| app/core/task.py | modified | (no docs reference this file) |

## Next Step

`/log-work [notes about what was completed]`
```

Then summarize the updates to the user in the chat.
