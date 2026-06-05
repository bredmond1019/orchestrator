# Slash Commands

Custom Claude Code commands for this repo. Invoke with `/command-name` in the prompt.

---

## Orientation & Status

### `/prime`
**Orient to this repo at the start of a session.**

Reads `README.md`, `CLAUDE.md`, `docs/app-architecture-overview.md`, and `planning/CONTEXT.md`; runs `git ls-files`; then summarizes the codebase, directory layout, current phase, and anything flagged as standing rules or known bugs. Read-only.

_No variables._

### `/status`
**Report current focus and sequence state.**

Reads only `planning/STATUS.md` and reports the Current focus line, what's In Progress, and what's Next. Read-only; reads nothing else.

_No variables._

### `/process-tasks`
**Analyze the block sequence and report what is eligible to start.**

Reads `STATUS.md`, applies sequential eligibility rules (a block is ready only if all blocks above it are `done`), and returns a status table for every block. Identifies the next eligible block. Read-only.

_No variables._

---

## Planning

### `/next-task`
**Generate a task spec for the current/next block.**

Reads `STATUS.md` to find the first non-`done` block, reads only the relevant sections of the two plan files, then writes a full task spec to `planning/tasks/phaseN-blockX.md`. Stops and says so if all blocks are already done. Returns only the path to the file created.

_No variables._

### `/plan`
**Create a plan for a task, scaled to its complexity.**

Researches the codebase, determines task type and complexity, and writes a plan to `planning/tasks/plan-{name}.md`. Includes implementation phases and testing strategy for complex tasks; keeps it lean for simple ones. Returns only the path to the file created.

| Variable | Description |
|---|---|
| `$ARGUMENTS` | Required. Description of the task to plan. |

### `/feature`
**Create a comprehensive plan to implement a new feature.**

Reads `CLAUDE.md` and the architecture overview, then writes a full feature plan to `planning/tasks/feature-{name}.md` — including User Story, Problem/Solution statements, three implementation phases, Testing Strategy, Acceptance Criteria, and Validation Commands. Returns only the path to the file created.

| Variable | Description |
|---|---|
| `$ARGUMENTS` | Required. Description of the feature to plan. |

### `/chore`
**Plan a maintenance or housekeeping task.**

Researches the codebase and writes a focused chore plan to `planning/tasks/chore-{name}.md`. Lighter than `/plan` — no phases or testing strategy. Returns only the path to the file created.

| Variable | Description |
|---|---|
| `$ARGUMENTS` | Required. Description of the chore. |

---

## Implementation

### `/breakdown`
**Decompose a task spec into agent-executable sub-steps.**

Reads a task spec from `planning/tasks/` (or defaults to the current block's spec), reads the actual source files each step touches to learn exact class/method names and file paths, then writes a granular breakdown to `planning/tasks/breakdown-{name}.md`. Every sub-step is atomic: one file, one change, one command — precise enough to execute without interpretation. Includes inline **Verify** checks after each group. Acceptance Criteria and Validation Commands are copied verbatim from the source spec.

| Variable | Description |
|---|---|
| `$ARGUMENTS` | Optional. Path to the spec file to break down. Defaults to the current block's spec from STATUS.md. |

### `/implement`
**Execute a plan file against the codebase.**

Runs `/prime` to orient, reads the given plan file, executes every step in order following CLAUDE.md conventions, runs the plan's Validation Commands (falling back to the standard three checks), then reports the completed work with `git diff --stat`.

| Variable | Description |
|---|---|
| `$ARGUMENTS` | Required. Path to the plan file (e.g. `planning/tasks/feature-summarizer.md`). |

### `/build`
**Implement a task directly without creating a plan first.**

Runs `/prime`, then implements the described task directly. For tasks too large for this (new workflows, multi-phase features), suggests `/feature` or `/plan` instead. Runs standard validation checks, shows commit message for confirmation, then commits.

| Variable | Description |
|---|---|
| `$ARGUMENTS` | Required. Description of the task to implement. |

---

## Tracking & Progress

### `/start-block`
**Mark a block as in-progress in STATUS.md.**

Reads `STATUS.md`, finds the target block (defaulting to the first non-done block), checks that all preceding blocks are done, then flips the status to `in_progress` and updates Current focus and Last updated.

| Variable | Description |
|---|---|
| `$ARGUMENTS` | Optional. Block identifier to start (e.g. `phase1-block2`). Defaults to first non-done block. |

### `/update-task`
**Record progress in the current task spec.**

Reads the current task spec from `planning/tasks/`, optionally marks a step as done (prepends ✅), and/or appends a dated note to the `## Notes` section. Operates on the spec file only; does not touch STATUS.md.

| Variable | Description |
|---|---|
| `$1` | Step number to mark done. Pass `0` to only append a note. |
| `$ARGUMENTS` | Note text to append to the Notes section. |

### `/review-task`
**Assess progress against the current task spec.**

Reads `STATUS.md`, the matching task spec in `planning/tasks/`, and the repo files named in the spec's Context Pointers. Reports each Step-by-Step task as Done or Outstanding with one-sentence evidence, and flags any drift from Acceptance Criteria. If no spec exists for the current block, says so and suggests `/next-task`. Read-only.

_No variables._

### `/validate-task`
**Run validation commands and check acceptance criteria.**

Reads `STATUS.md` and the current task spec, then runs every command in the spec's Validation Commands section. Reports a PASS/FAIL table per Acceptance Criterion. Will not declare anything done if a command fails. If no spec exists for the current block, says so and suggests `/next-task`.

_No variables._

---

## Health & Housekeeping

### `/check`
**Lint, run the full test suite, and verify the app and worker construct cleanly.**

Runs four commands inline (no servers started, no ports bound, no manual interruption needed):

```
uv run pylint app/
uv run pytest
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
```

Reports pylint errors, failing test names, or construction errors concisely; one line if everything passes.

_No variables._

### `/log-work`
**Sync STATUS.md and append a dated DEVLOG entry for completed work.**

Reads `STATUS.md`, the current task spec, and `DEVLOG.md`; runs `git diff --stat`. Updates `STATUS.md` (flips statuses, advances Current focus, bumps Last updated, logs deviations) and appends a new entry to `DEVLOG.md`. Will prompt you to add settled architectural choices to `DECISIONS.md` — never edits it directly. Never touches the master plan files.

_No variables._

### `/update-docs`
**Patch docs/*.md to reflect recent source changes.**

Surgically updates existing reference docs when code has changed. Determines changed source files from `git diff`, maps them to the docs that reference them, and rewrites only the affected sections. Reports what was updated, what was clean, and anything too large for surgical patching (flagged `NEEDS_REVIEW`). Never rewrites a doc wholesale — use `/generate-new-docs` for that.

| Variable | Description |
|---|---|
| `$ARGUMENTS` | Optional. Git ref or range to diff against (e.g. `HEAD~3`, `main..HEAD`). Defaults to `HEAD~1` plus unstaged changes. |

### `/commit`
**Stage and commit changes with a conventional message.**

Inspects `git status` and `git diff --stat`, then chooses a commit strategy:

- Only code changed → one code commit
- Only planning/docs changed → one `docs:` commit
- Both changed → two commits (code first, then docs)

Drafts a conventional message (`feat:`, `fix:`, `docs:`, etc.), shows it for confirmation before committing. Never pushes, never uses `--no-verify`, never uses `git add -A`.

| Variable | Description |
|---|---|
| `$ARGUMENTS` | Optional. A message override or scope hint incorporated into the commit message. |
