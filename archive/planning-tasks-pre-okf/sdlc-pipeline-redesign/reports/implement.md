# Implementation Report — SDLC Pipeline Redesign

**Date:** 2026-06-07
**Plan:** ad-hoc (designed in-session via plan mode)
**Scope:** All tasks — full SDLC slash command pipeline redesign

---

## Original Request

The user asked for a clean, fully-connected Software Development Lifecycle pipeline implemented as Claude slash commands. The key requirements were:

1. Each SDLC step runs in its own fresh agent context window, starting with `/prime`
2. Each step reads the previous step's output from a predictable, named file path
3. A consistent naming convention across all steps and all phases/blocks
4. `/test` must write its results to a file (not just output to chat)
5. `/review-task` must run tests fresh as a verification step, not just read a stale report
6. A new `/document` step that gates on the review verdict being PASS before touching docs
7. The pipeline must support both full-block runs and task-scoped runs (e.g. "only task 3")
8. The README must document the full pipeline so any agent can orient quickly

The project has multiple phases (0–3) with blocks/projects within each (A, B, C, D or numbered 1–4). The pipeline must handle the full range of `phaseX-blockY` identifiers.

---

## Design Decisions Made

### Naming Convention

All report files live in `planning/tasks/reports/`. Pattern: `{spec-stem}[-taskN]-{step}.md`

| Step | Full-block | Task-scoped |
|---|---|---|
| Implement | `phase0-blockC-implement.md` | `phase0-blockC-task3-implement.md` |
| Test | `phase0-blockC-test.md` | `phase0-blockC-task3-test.md` |
| Review | `phase0-blockC-review.md` | `phase0-blockC-task3-review.md` |
| Document | `phase0-blockC-document.md` | `phase0-blockC-task3-document.md` |

The task spec itself stays at `planning/tasks/phase0-blockC.md` (unchanged). The optional breakdown stays at `planning/tasks/breakdown-phase0-blockC.md` (unchanged).

**Migration note:** Two existing reports (`phase0-blockC-task1.md`, `phase0-blockC-task1-review.md`) use the old convention with no step-suffix. They are left as-is — no rename needed.

### Argument Convention

Every pipeline step after `/generate-tasks` takes the same form: `planning/tasks/<spec>.md [N]`

Split on last space. Trailing number = task N. No number = full block. The same path is copy-pasted through the entire pipeline.

### Review Verdict Gating

The review step runs a **fresh test suite** as the authoritative verification (not the historical test report). The `/document` step gates strictly on the review report's `**Overall verdict:** PASS` line — it stops immediately if the verdict is FAIL or PARTIAL.

### `/test` is non-destructive to existing behavior

When called with no arguments, `/test` still outputs JSON to chat only (unchanged behavior). The file-writing behavior is additive and only activates when a spec path is provided.

### `/update-docs` vs `/document`

`/update-docs` is preserved as a standalone git-diff-driven tool for ad-hoc doc patching. `/document` is the pipeline-aware version: it reads the implement report's file list (not git diff) to scope updates, and gates on review PASS.

---

## Full Pipeline

```
/generate-tasks phase0-blockC          → planning/tasks/phase0-blockC.md
      ↓  (optional)
/breakdown planning/tasks/phase0-blockC.md  → planning/tasks/breakdown-phase0-blockC.md
      ↓
/implement planning/tasks/phase0-blockC.md [N]
      → planning/tasks/reports/phase0-blockC[-taskN]-implement.md
      ↓
/test planning/tasks/phase0-blockC.md [N]
      → planning/tasks/reports/phase0-blockC[-taskN]-test.md
      ↓
/review-task planning/tasks/phase0-blockC.md [N]   (runs fresh tests; gates on PASS)
      → planning/tasks/reports/phase0-blockC[-taskN]-review.md
      ↓  (gates on PASS verdict)
/document planning/tasks/phase0-blockC.md [N]
      → planning/tasks/reports/phase0-blockC[-taskN]-document.md
      ↓
/log-work [notes]                      → STATUS.md, DEVLOG.md
```

---

## Files Created or Modified

| File | Action | Change Summary |
|---|---|---|
| `.claude/commands/implement.md` | modified | Report path suffix changed from `.md` to `-implement.md`; next-step hint added |
| `.claude/commands/test.md` | modified | Added `## Variables` section; Step 0 arg-parsing instruction; `## File Output` section that writes `*-test.md` |
| `.claude/commands/review-task.md` | modified | Full rewrite: derives `-implement.md` + `-test.md` paths; reads both as historical context; Step 8 replaced with fresh test run; report format adds `## Fresh Test Run` section and verdict rules; next-step hint added |
| `.claude/commands/document.md` | created | New command: gates on review PASS; reads implement report file list; surgically patches `docs/`; writes `*-document.md` |
| `.claude/commands/generate-tasks.md` | modified | Report section updated to show both next-step options (breakdown or implement directly) |
| `.claude/commands/README.md` | modified | Added `## SDLC Pipeline` section with full flow diagram and argument convention; `/implement` and `/review-task` descriptions updated; `/test` and `/document` entries added; `## Documentation` section added |

---

## Detailed Changes Per File

### `implement.md`

**Before (report path derivation):**
```
- Plan only: → planning/tasks/reports/phase0-blockC.md
- Plan + task: → planning/tasks/reports/phase0-blockC-task3.md
```

**After:**
```
- Plan only: → planning/tasks/reports/phase0-blockC-implement.md
- Plan + task: → planning/tasks/reports/phase0-blockC-task3-implement.md
```

Also added next-step hint at end of Report section:
```
Next: /test planning/tasks/phase0-blockC.md [N]
```

---

### `test.md`

**Added `## Variables` section** (before `## Purpose`) defining the optional spec-path argument and path derivation rules.

**Added Step 0** (before the `/prime` step) that parses `$ARGUMENTS` and derives the report file path.

**Added `## File Output` section** (after `## Report`) that defines the markdown report format written to `*-test.md` when a spec path is provided. The report includes: date, plan, scope, overall result summary table (8 rows, one per test), and the full JSON results verbatim.

The existing JSON-to-chat behavior and the IMPORTANT constraint on returning only JSON are unchanged.

---

### `review-task.md` (full rewrite)

**Step 4** replaced with dual path derivation — both the implement report (`-implement.md`) and the new test report (`-test.md`).

**Step 6** updated: reads both implement AND test reports as historical context. Explicitly notes that the test report is NOT authoritative — a fresh run is required.

**Step 8** replaced: was "run validation commands scoped to task or full block"; now "run a fresh test suite as authoritative verification." Language added: "A fresh test failure always prevents PASS, even if all acceptance criteria appear MET from reading the code."

**Report format** updated:
- Added `**Test report:** found / not found` to the header
- Added `## Fresh Test Run` section (commands run, output, Result: PASS/FAIL) between `## Acceptance Criteria` and `## CLAUDE.md Rule Violations`
- Added **Verdict rules** block before `## Verdict` defining exactly when PASS, PARTIAL, FAIL apply
- Added next-step hint at end based on verdict

---

### `document.md` (new)

Full spec for the new documentation step. Key behaviors:

1. Parses args (same `planning/tasks/phase0-blockC.md [N]` format)
2. Runs `/prime`
3. Derives and reads the review report — **stops immediately** if verdict is not PASS
4. Derives and reads the implement report — extracts the **Files Created or Modified** table as the authoritative source list (not git diff)
5. Maps changed source files to `docs/` files that reference them
6. Surgically patches only affected doc sections
7. Flags `docs/app-architecture-overview.md` as `NEEDS_REVIEW` for any architecture-level changes — never edits it automatically
8. Writes `*-document.md` report

---

### `generate-tasks.md`

Report section changed from a single next-step hint to two options:
```
Next (optional — decompose into atomic sub-steps):
  /breakdown planning/tasks/phase0-blockC.md

Next (skip breakdown — implement directly):
  /implement planning/tasks/phase0-blockC.md
```

---

### `README.md`

**Added `## SDLC Pipeline`** section immediately after the opening header block (before all other sections). Contains: the full pipeline flow diagram with `→` file output notation, the argument convention explanation, and the ad-hoc task note.

**Updated `### /implement`** description to note task number arg and `-implement.md` report suffix.

**Updated `### /review-task`** description: corrected from "no variables" to required `$ARGUMENTS`; describes fresh test run and PASS gating.

**Added `### /test`** entry under `## Health & Housekeeping` (it was missing entirely from the README).

**Added `## Documentation` section** before `## Health & Housekeeping` containing the `/document` entry.

---

## Commands Left Unchanged

`next-task.md`, `plan.md`, `breakdown.md`, `log-work.md`, `update-docs.md`, `update-task.md`, `update-specific-task.md`, `validate-task.md`, `start-block.md`, `status.md`, `prime.md`, `build.md`, `commit.md`, `feature.md`, `chore.md`, `check.md`

---

## What a Reviewer Should Check

1. **Naming consistency** — every path derivation example in implement, test, review-task, document, and README uses the same pattern `{spec-stem}[-taskN]-{step}.md`. Verify these are consistent across all four files.

2. **`review-task.md` fresh test gating** — confirm Step 8 says tests must pass for a PASS verdict, and that the Verdict rules block makes this explicit.

3. **`document.md` PASS gate** — confirm Step 5 stops execution unconditionally if verdict is not PASS, and that the gate text quotes the exact verdict values (FAIL/PARTIAL).

4. **`test.md` backward compatibility** — confirm that the IMPORTANT note about returning JSON-only to chat is preserved, and that the file write only happens when `$ARGUMENTS` is provided.

5. **README pipeline diagram** — confirm the diagram matches the actual file paths each command writes (not the old no-suffix convention).

6. **`generate-tasks.md`** — confirm the Report section shows two next-step options rather than one, and that `/implement` is presented as the "skip breakdown" option.

---

## git diff --stat

```
 .claude/commands/README.md         | 64 +++++++++++++++++++++++++++++++++++---
 .claude/commands/generate-tasks.md |  9 ++++--
 .claude/commands/implement.md      |  9 ++++--
 .claude/commands/review-task.md    | 56 +++++++++++++++++++++++++--------
 .claude/commands/test.md           | 55 ++++++++++++++++++++++++++++++++
 5 files changed, 171 insertions(+), 22 deletions(-)
```

Note: `document.md` is a new untracked file not yet in the diff above. It lives at `.claude/commands/document.md`.
