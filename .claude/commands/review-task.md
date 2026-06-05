# Review Task — Verify a completed task against its spec and acceptance criteria.

## Variables

$ARGUMENTS — path to the task spec, with an optional task number suffix (same format as `/implement`).

Examples:
- `planning/tasks/phase0-blockC.md` — review all tasks in the spec
- `planning/tasks/phase0-blockC.md 1` — review only Task 1
- `planning/tasks/phase0-blockC.md 3` — review only Task 3

## Instructions

1. If `$ARGUMENTS` is not provided, stop and ask the user for the task spec path.
2. Parse `$ARGUMENTS`: split on the last space. If the trailing token is a number, treat it as the **task number** to review; the remainder is the task spec path.
3. Run `/prime` to orient to the codebase before reading any files.
4. **Derive the report file path** (written by `/implement`):
   - Plan only: `planning/tasks/phase0-blockC.md` → `planning/tasks/reports/phase0-blockC.md`
   - Plan + task N: `planning/tasks/phase0-blockC.md 3` → `planning/tasks/reports/phase0-blockC-task3.md`
5. Read the task spec in full.
6. Read the report file if it exists. If it does not exist, note that no `/implement` report was found — continue the review from source alone.
7. Read every file listed in the report's **Files Created or Modified** table (or, if no report, read the files most likely touched by the task based on the spec). Verify the actual content — do not trust the report alone.
8. **Run the validation commands** relevant to the scope being reviewed:
   - **Task-scoped review:** run only the commands directly tied to that task (import checks, specific `pytest` path). Do NOT run the full suite.
   - **Full review:** run the plan's complete Validation Commands block exactly as written. If none exist, run:
     ```
     uv run pytest --collect-only
     uv run pytest -v
     uv run pylint app/
     cd app && uv run python -c "from main import app"
     cd app && uv run python -c "from worker.config import celery_app"
     ```
9. **Check every Acceptance Criterion** in the spec against the actual code and validation output:
   - For each criterion: state whether it is **MET**, **PARTIAL**, or **NOT MET**, and cite the evidence (file + line, test name, command output).
   - A criterion is MET only when you can point to code or test output that directly satisfies it.
   - Do not mark anything MET based solely on the implementation report — verify in source.
10. Write the review report file and summarize to the user (see Report).

## Context / Files to Read

- `$ARGUMENTS` (the task spec)
- `planning/tasks/reports/<derived-path>` (the implementation report, if present)
- `CLAUDE.md` (standing rules — check for violations)
- All files created or modified by the implementation

## Report

**Derive the review report file path:**
- Plan only: `planning/tasks/phase0-blockC.md` → `planning/tasks/reports/phase0-blockC-review.md`
- Plan + task N: `planning/tasks/phase0-blockC.md 3` → `planning/tasks/reports/phase0-blockC-task3-review.md`

**Write the review report file** in this exact format:

```markdown
# Review Report — <plan filename> [Task <N> | All Tasks]

**Date:** <YYYY-MM-DD>
**Plan:** <plan file path>
**Scope:** Task <N> | All tasks
**Implementation report:** found / not found
**Overall verdict:** PASS / FAIL / PARTIAL

## Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | <criterion text, truncated to ~80 chars> | MET / PARTIAL / NOT MET | file:line or test name or command output |
| 2 | … | … | … |

## Validation Commands

**Commands run:**
\`\`\`
<exact commands>
\`\`\`

**Output:**
\`\`\`
<stdout/stderr, truncated to relevant lines>
\`\`\`

## CLAUDE.md Rule Violations

- <any standing-rule violation found, or "None">

## Issues Found

- <concrete problem with file + line reference, or "None">

## Verdict

<One paragraph: overall assessment, what passed, what failed, what must be fixed before this task is considered done. If PASS, state clearly. If FAIL or PARTIAL, list the blocking items.>
```

Then summarize the verdict and any blocking issues to the user in the chat.
