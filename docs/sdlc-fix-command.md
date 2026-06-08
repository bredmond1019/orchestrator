# SDLC Pipeline: `/fix` Command Design Report

*Added 2026-06-08. Documents the problem, design decisions, and resulting workflow changes.*

---

## The Problem

The SDLC pipeline has a gap in its review loop. When `/review-task` produces a FAIL or PARTIAL
verdict, the prior guidance was:

> "Fix the issues above, then: `/review-task planning/tasks/phase0-blockC.md [N]`"

This is vague in two ways:

1. **No targeted tool.** The natural instinct is to reach for `/implement`, but `/implement`
   re-executes every step in the spec from scratch. It has no knowledge of the review report —
   it cannot distinguish passing criteria from failing ones. The result is broad, unfocused
   re-implementation when only a surgical fix is needed.

2. **No agent context.** Neither `/implement` nor any other command was instructed to read the
   review report. The agent executing the fix had to rely on the user pasting the relevant
   failures into the prompt manually.

---

## Design Decisions

### Decision 1: A dedicated `/fix` command, not a modification to `/implement`

The cleaner fix would have been to update `/implement` to check for an existing review report
and use it when present. We rejected this for one reason: **conditional behavior based on
filesystem state is hard to reason about.**

`/implement` has one clear job — execute the spec. If it silently changes behavior depending
on whether a `-review.md` file happens to exist, the pipeline becomes harder to predict and
debug. A user asking "why did `/implement` behave differently this time?" has no obvious answer.

A dedicated `/fix` command makes intent explicit. When the user runs `/fix`, they are declaring:
"I am in fix mode. A review has already run and failed. Fix only what the review identified."
That intent is legible at a glance.

### Decision 2: `/fix` writes to the `-implement.md` slot, not a new `-fix.md` slot

This was the central architectural question. The naive design would write a separate
`-fix.md` report. The problem: every downstream command reads `-implement.md`.

| Command | Reads `-implement.md`? | Why |
|---|---|---|
| `/review-task` | Yes | Historical context; extracts "Files Created or Modified" to know what source files to verify |
| `/document` | Yes | Uses "Files Created or Modified" table as the authoritative list of what changed, to scope doc updates |

If `/fix` wrote to a new `-fix.md` slot, both `/review-task` and `/document` would need
conditional logic to check for it — preferring the fix report over the implement report when
one exists. This pushes the exact problem we wanted to avoid (conditional behavior based on
filesystem state) into *two other commands* instead of just one.

**The reframe that resolves this:** The `-implement.md` file is not "the output of the
`/implement` command." It is "the current state of Phase 2 work." Both `/implement` and `/fix`
are Phase 2 activities. Whichever ran last owns the slot.

This means:
- `/test`, `/review-task`, and `/document` require **zero changes** — they continue reading
  `-implement.md` and find current, accurate content regardless of whether it was written by
  `/implement` or `/fix`.
- Git history preserves every prior version of the implement report automatically.
- Multiple fix passes overwrite the slot each time, incrementing the fix pass counter in the
  report header.

### Decision 3: `/fix` is self-gating, not conditionally invoked by other commands

`/fix` enforces its own preconditions:

- **Hard stop** if no review report exists: the user must run `/review-task` first.
- **Soft stop** if the verdict is already PASS: redirect to `/document` — nothing to fix.

This keeps other commands clean. No command in the pipeline needs to know about `/fix` or
check for it.

---

## What Changed

### New file: `.claude/commands/fix.md`

The command definition. Key behaviors:

1. Derives the review report path from `$ARGUMENTS` (same naming convention as all other commands)
2. Hard-stops if review report is absent; soft-stops if verdict is PASS
3. Extracts failing criteria (NOT MET / PARTIAL rows) and Issues Found from the review report
4. Reads the current `-implement.md` to get the baseline file list and prior fix pass count
5. Reads affected source files and makes only targeted fixes
6. Compiles the complete file list (union of prior implement table + any new files touched)
7. Runs the spec's Validation Commands — not the full 8-test suite (that belongs to `/test`)
8. Overwrites `-implement.md` with a "Fix Pass N" report that preserves the `## Files Created or Modified` table structure
9. Outputs: `Next: /test <spec> [N]` → `then: /review-task <spec> [N]`

The fix report format matches the implement report structure so downstream commands find what
they expect. The only visible difference is the title ("Fix Pass N" instead of "Implementation
Report") and added sections ("Failures Addressed", "Changes Made").

### Modified: `.claude/commands/review-task.md`

Updated the next-step hint at the bottom. Previously:
```
If verdict is not PASS: Fix the issues above, then: /review-task planning/tasks/phase0-blockC.md [N]
```

Now:
```
If verdict is not PASS: /fix planning/tasks/phase0-blockC.md [N]
                        then: /test planning/tasks/phase0-blockC.md [N]
                        then: /review-task planning/tasks/phase0-blockC.md [N]
```

### Modified: `.claude/commands/README.md`

- `/fix` row added to the Phase Table (Phase 2)
- Pipeline Flow updated: PHASE 4 — REVIEW now has an explicit PASS/FAIL/PARTIAL branch showing the `/fix` loop
- Report File Naming table: `fix` row added with note that it overwrites the implement slot
- New `/fix` subsection added under Phase 2 — Implement

### Modified: `docs/sdlc-workflow.md`

- Quick Reference table: `/fix` row added after `/implement`
- Flow Diagram: FAIL/PARTIAL branch expanded from a vague "back to IMPLEMENT" box to a full `/fix` box showing its inputs, outputs, and `→ /test → /review-task` loop
- Report Files table: `fix` row added with shared-slot note
- Gates table: third gate added for `/fix`'s own preconditions
- File Ownership table: `/fix` added as a writer of `planning/tasks/reports/*`

---

## The New Workflow

```
PHASE 2 — IMPLEMENT
  /implement planning/tasks/phase0-blockC.md [N]
        → planning/tasks/reports/phase0-blockC[-taskN]-implement.md

PHASE 3 — TEST
  /test planning/tasks/phase0-blockC.md [N]
        → planning/tasks/reports/phase0-blockC[-taskN]-test.md

PHASE 4 — REVIEW
  /review-task planning/tasks/phase0-blockC.md [N]
        → planning/tasks/reports/phase0-blockC[-taskN]-review.md

        if PASS ─────────────────────────────────────────► PHASE 5
        if FAIL/PARTIAL ──────────────────────────────► PHASE 2 — FIX:

  /fix planning/tasks/phase0-blockC.md [N]
        reads:  review report (failing criteria + issues)
                implement report (prior file list + fix pass count)
                source files
        writes: planning/tasks/reports/phase0-blockC[-taskN]-implement.md
                (overwrites; title becomes "Fix Pass N")

  /test planning/tasks/phase0-blockC.md [N]     ◄── same command, same args
  /review-task planning/tasks/phase0-blockC.md [N]   ◄── same command, same args

        repeat until PASS

PHASE 5 — DOCUMENT  (unchanged — still reads -implement.md)
  /document planning/tasks/phase0-blockC.md [N]
```

### Commands that did not change

| Command | Why unchanged |
|---|---|
| `/test` | Does not read any prior report — only uses spec for naming |
| `/review-task` | Already reads `-implement.md` conditionally; the fix report lands in the same slot |
| `/document` | Already reads `-implement.md` for the Files Created or Modified table; the fix report preserves that structure |

---

## Edge Cases

| Scenario | Behavior |
|---|---|
| `/fix` run without a prior `/review-task` | Hard stop: "Cannot fix: no review report found. Run `/review-task` first." |
| `/fix` run after a PASS verdict | Soft stop: "Review verdict is PASS — no fix needed. Run `/document`." |
| No prior implement report exists | Graceful fallback: infer files from spec and review Issues Found; note absence in report |
| PARTIAL verdict with no failing criteria (test failure only) | Issues Found is the fix target; no criteria re-work needed |
| Fix validation still fails after changes | Report written with `Status: FAILED`; user warned; loop continues via `/test` → `/review-task` |
| Multiple consecutive fix passes | Fix pass counter incremented each time; git history preserves all prior states |
