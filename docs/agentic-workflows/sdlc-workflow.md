---
type: Reference
title: SDLC Workflow Reference
description: Reference for the end-to-end SDLC workflow pipeline and its stages.
---

# SDLC Workflow Reference

*The complete development lifecycle for this repo — slash commands, inputs, outputs, and flow.*
*Invoke any command with `/command-name` in Claude Code.*

---

## Quick Reference

| Stage | Command | Input | Output |
|---|---|---|---|
| **Project Init** | `/new-project <desc>` | description or spec file | `planning/intake.md` |
| **Project Init** | `/scaffold-project` | `planning/intake.md` | 8 planning files |
| **Session Start** | `/session-recap` | DEVLOG + STATUS + spec + reports dir | chat only |
| **Session Start** | `/status` | `planning/STATUS.md` | chat only |
| **Session Start** | `/process-tasks` | `planning/STATUS.md` | chat only |
| **Block Setup** | `/start-block [id]` | `planning/STATUS.md` | `planning/STATUS.md` |
| **1 — Plan** | `/generate-tasks <id>` | MASTER_PLAN + CLAUDE.md | `planning/tasks/<block>/tasks.md` |
| **1 — Plan (opt.)** | `/breakdown [spec]` | spec file + source files | `planning/tasks/<block>/breakdown.md` |
| **2 — Implement** | `/implement <spec> [N]` | spec file + source files | code changes + implement report |
| **2 — Fix** | `/fix <spec> [N]` | review report (FAIL/PARTIAL) + implement report + source files | implement report (overwritten) |
| **2 — Track** | `/update-task [id] <step>` | spec file | spec file (in-place) |
| **2 — Commit** | `/commit [hint]` | git diff | git history |
| **3 — Test** | `/test <spec> [N]` | spec file | test report |
| **4 — Review** | `/review-task <spec> [N]` | spec + implement + test reports | review report (PASS/FAIL) |
| **5 — Document** | `/document <spec> [N]` | review report (must be PASS) + implement report | patched `docs/*.md` + document report |
| **6 — Wrap-up** | `/log-work [notes]` | STATUS + spec + DEVLOG + git diff | updated STATUS.md + DEVLOG.md |
| **Ad-hoc** | `/plan <desc>` | description | `planning/tasks/plan-{name}/tasks.md` |
| **Ad-hoc** | `/feature <desc>` | description | `planning/tasks/feature-{name}/tasks.md` |
| **Ad-hoc** | `/chore <desc>` | description | `planning/tasks/chore-{name}/tasks.md` |
| **Worktree** | `/init-worktree <block> [N]` | block ID + optional task number | `trees/<worktree-name>/` (isolated branch) |
| **Worktree** | `/clean-worktree <block> [N]` | block ID + optional task number | fast-forward merge → `main`; branch + dir removed |

---

## Flow Diagram

```
╔══════════════════════════════════════════════════════════════╗
║                  PROJECT INITIALIZATION (once)               ║
║                                                              ║
║  /new-project <description or path/to/spec.md>              ║
║      │  reads: inline text OR spec file, existing repo       ║
║      │  asks: identity, tech, phases, business questions     ║
║      ↓  writes: planning/intake.md                          ║
║                                                              ║
║  /scaffold-project [intake path]                             ║
║      │  reads: planning/intake.md                           ║
║      ↓  writes: planning/CONTEXT.md                         ║
║                  planning/STATUS.md                          ║
║                  planning/DECISIONS.md                       ║
║                  planning/MASTER_PLAN.md                     ║
║                  planning/README.md                          ║
║                  planning/tasks/  (stub)                     ║
║                  CLAUDE.md                                   ║
║                  README.md                                   ║
║                  DEVLOG.md                                   ║
╚══════════════════════════════════════════════════════════════╝
                            │
                            ▼
╔══════════════════════════════════════════════════════════════╗
║              SESSION START (read-only, each session)         ║
║                                                              ║
║  /session-recap  reads: DEVLOG (last 3), STATUS, current     ║
║                         spec, <block>/reports/ listing       ║
║                  out:   chat — recent work, next command      ║
║                                                              ║
║  /status         reads: STATUS.md only                       ║
║                  out:   chat — current focus + in-progress   ║
║                                                              ║
║  /process-tasks  reads: STATUS.md                            ║
║                  out:   chat — eligibility table             ║
╚══════════════════════════════════════════════════════════════╝
                            │
                            ▼
╔══════════════════════════════════════════════════════════════╗
║                      BLOCK SETUP                             ║
║                                                              ║
║  /start-block [phase0-blockC]                                ║
║      reads: planning/STATUS.md                               ║
║      writes: planning/STATUS.md                              ║
║              (block → in_progress, Current focus updated)    ║
╚══════════════════════════════════════════════════════════════╝
                            │
                            ▼
╔══════════════════════════════════════════════════════════════╗
║                   PHASE 1 — PLAN                             ║
║                                                              ║
║  /generate-tasks phase0-blockC                               ║
║      reads: MASTER_PLAN.md (target section only)             ║
║             Projects_and_Learning_Plan.md (matching section) ║
║             CLAUDE.md (standing rules, known bugs)           ║
║      writes: planning/tasks/phase0-blockC/tasks.md ◄─ SPEC  ║
║                                                              ║
║                    │ (optional)                              ║
║                    ▼                                         ║
║  /breakdown [planning/tasks/phase0-blockC/tasks.md]          ║
║      reads: spec file                                        ║
║             source files each step touches                   ║
║      writes: planning/tasks/phase0-blockC/breakdown.md       ║
║              (atomic sub-steps with exact file paths)        ║
╚══════════════════════════════════════════════════════════════╝
                            │
                   spec file passes through
                   every remaining stage
                            │
                            ▼
╔══════════════════════════════════════════════════════════════╗
║                 PHASE 2 — IMPLEMENT                          ║
║                                                              ║
║  /implement planning/tasks/phase0-blockC/tasks.md [N]        ║
║      reads: spec file (full block or task N)                 ║
║             CLAUDE.md                                        ║
║             source files to touch                            ║
║      writes: code changes in working tree                    ║
║              planning/tasks/phase0-blockC/reports/           ║
║                [taskN-]implement.md                          ║
║                                                              ║
║  (during implementation, as needed)                          ║
║                                                              ║
║  /update-task [phase0-blockC] <step> [note]                  ║
║      reads: spec file                                        ║
║      writes: spec file in-place (✅ step, appends note)      ║
║                                                              ║
║  /commit [hint]                                              ║
║      reads: git status + git diff                            ║
║      writes: git history (conventional commit message)       ║
╚══════════════════════════════════════════════════════════════╝
                            │
                            ▼
╔══════════════════════════════════════════════════════════════╗
║                   PHASE 3 — TEST                             ║
║                                                              ║
║  /test planning/tasks/phase0-blockC/tasks.md [N]             ║
║      reads: spec file (for context and report naming)        ║
║      runs: import checks → ruff → pylint → pytest collect    ║
║             → pytest full                                    ║
║      writes: planning/tasks/phase0-blockC/reports/           ║
║                [taskN-]test.md                               ║
╚══════════════════════════════════════════════════════════════╝
                            │
                            ▼
╔══════════════════════════════════════════════════════════════╗
║                  PHASE 4 — REVIEW                            ║
║                                                              ║
║  /review-task planning/tasks/phase0-blockC/tasks.md [N]      ║
║      reads: spec file (acceptance criteria)                  ║
║             implement report (historical context)            ║
║             test report (historical context)                 ║
║      runs:  FRESH test suite (authoritative)                 ║
║      writes: planning/tasks/phase0-blockC/reports/           ║
║                [taskN-]review.md                             ║
║              verdict: PASS | PARTIAL | FAIL                  ║
╚══════════════════════════════════════════════════════════════╝
                 │                    │
              PASS                 FAIL/PARTIAL
                 │                    │
                 ▼                    ▼
╔═════════════════════╗    ╔══════════════════════════╗
║  PHASE 5 — DOCUMENT ║    ║  PHASE 2 — FIX           ║
║                     ║    ║                          ║
║  /document          ║    ║  /fix <spec> [N]         ║
║   <spec> [N]        ║    ║    reads: review report  ║
║                     ║    ║    (failing criteria +   ║
║  reads:             ║    ║     issues found)        ║
║   review report     ║    ║    implement report      ║
║   (gates on PASS)   ║    ║    (prior file list)     ║
║   implement report  ║    ║    source files          ║
║   (Files Modified   ║    ║    writes: implement     ║
║    table)           ║    ║    report (overwritten)  ║
║   affected source   ║    ║                          ║
║   files             ║    ║  /test <spec> [N]        ║
║  writes:            ║    ║  /review-task <spec> [N] ║
║   docs/*.md         ║    ║    (repeat until PASS)   ║
║   (surgical patches ║    ╚══════════════════════════╝
║    only)            ║
║   document report   ║
╚══════════════════════╝
                 │
                 ▼
╔══════════════════════════════════════════════════════════════╗
║                  PHASE 6 — WRAP-UP                           ║
║                                                              ║
║  /log-work [notes]                                           ║
║      reads: planning/STATUS.md                               ║
║             planning/tasks/phase0-blockC/tasks.md            ║
║             DEVLOG.md                                        ║
║             git diff --stat + git log --oneline -10          ║
║      writes: planning/STATUS.md                              ║
║              (block → done, Current focus → next block,      ║
║               date bumped, deviations logged)                ║
║              DEVLOG.md (new dated entry appended)            ║
║      prompts: add settled choices to DECISIONS.md            ║
║              (never self-edits DECISIONS.md)                 ║
╚══════════════════════════════════════════════════════════════╝
                            │
                            ▼
                  loop back to /start-block
                  for the next block
```

---

## The Spec File

The spec file (`planning/tasks/phase0-blockC/tasks.md`) is the thread that runs through Phases 1–6. Every command from `/implement` onward takes it as its primary argument.

```
/generate-tasks  ──writes──▶  planning/tasks/phase0-blockC/tasks.md
                                          │
                    ┌─────────────────────┼──────────────────────┐
                    ▼                     ▼                      ▼
              /implement             /test                /review-task
              (reads spec)           (reads spec          (reads spec
                                      for naming)          for criteria)
```

**The `[N]` optional task number** scopes the entire pipeline (implement → test → review → document) to a single task within the spec. Use the same `N` for every step — it determines all report filenames.

```
/implement   planning/tasks/phase0-blockC/tasks.md 3
/test        planning/tasks/phase0-blockC/tasks.md 3
/review-task planning/tasks/phase0-blockC/tasks.md 3
/document    planning/tasks/phase0-blockC/tasks.md 3
```

All four write to `planning/tasks/phase0-blockC/reports/task3-{step}.md`.

---

## Directory Layout

Each block gets its own directory under `planning/tasks/`. All reports live in a `reports/` subdirectory alongside the spec:

```
planning/tasks/
  phase0-blockC/
    tasks.md          ← spec (written by /generate-tasks)
    breakdown.md      ← optional (written by /breakdown)
    reports/
      implement.md    ← or task3-implement.md for task-scoped
      test.md         ← or task3-test.md
      review.md       ← or task3-review.md
      document.md     ← or task3-document.md
  phase1-block1/
    tasks.md
    reports/
      ...
```

## Report Files

Reports live at `planning/tasks/<block>/reports/`. Naming pattern: `[taskN-]{step}.md`

| Step | Full-block report | Task-scoped report |
|---|---|---|
| implement | `implement.md` | `task3-implement.md` |
| fix | *(overwrites implement slot)* | *(overwrites implement slot)* |
| test | `test.md` | `task3-test.md` |
| review | `review.md` | `task3-review.md` |
| document | `document.md` | `task3-document.md` |

**Note:** `/fix` does not have its own named report slot — it overwrites `implement.md` in place. Both `/review-task` and `/document` continue reading from that path unchanged.

Each step reads the previous step's report as historical context. `/review-task` is the only step that re-runs live tests rather than trusting the test report.

---

## Worktree Isolation (Optional)

By default the SDLC pipeline runs on `main` — every commit lands immediately. Worktree isolation wraps the same pipeline in a dedicated branch and directory so `main` stays clean until the work is fully reviewed and ready to merge.

**When to use it:**
- Running a long or risky block where you want a clean merge point rather than incremental commits on `main`
- Running multiple blocks in parallel (each in its own worktree session)
- Experimenting with an implementation approach before committing to `main`

**Naming convention:** the worktree name is derived deterministically — block ID lowercased, plus an optional `-task<N>` suffix.

```
phase0-blockC      → trees/phase0-blockc/    (branch: phase0-blockc)
phase0-blockC 3    → trees/phase0-blockc-task3/  (branch: phase0-blockc-task3)
```

### Flow

```
╔══════════════════════════════════════════════════════════════╗
║               WORKTREE SETUP (main repo session)             ║
║                                                              ║
║  /init-worktree phase1-block1                                ║
║      checks: no name collision in git worktree list          ║
║      creates: trees/phase1-block1/  (branch: phase1-block1) ║
║      sparse checkout:                                        ║
║        app/  tests/  docs/  planning/  .claude/              ║
║        + all root-level files (CLAUDE.md, pyproject.toml…)  ║
║      copies: .env from repo root (if present)                ║
║      writes: empty initial commit on branch phase1-block1    ║
║      prints: path to open as a new Claude Code session       ║
╚══════════════════════════════════════════════════════════════╝
                            │
                            ▼
╔══════════════════════════════════════════════════════════════╗
║         FULL PIPELINE  (new Claude Code session)             ║
║         CWD = trees/phase1-block1/                           ║
║                                                              ║
║  /sdlc-run phase1-block1   (or any manual pipeline steps)    ║
║                                                              ║
║  All relative paths resolve correctly inside the worktree.   ║
║  Every git commit goes to branch phase1-block1, not main.    ║
║                                                              ║
║  Stages: implement → test → review → document → wrap-up      ║
║  (same gates, same reports, same conventions as normal flow) ║
╚══════════════════════════════════════════════════════════════╝
                            │
                            ▼
╔══════════════════════════════════════════════════════════════╗
║              MERGE + CLEANUP (main repo session)             ║
║                                                              ║
║  /clean-worktree phase1-block1                               ║
║      shows: uncommitted changes (warns if any)               ║
║      shows: unpushed commits on the branch (for review)      ║
║      merges: git merge --ff-only phase1-block1 → main        ║
║        if fast-forward fails: stops, worktree left intact    ║
║        resolution options printed (merge commit / rebase)    ║
║      removes: trees/phase1-block1/ directory                 ║
║      deletes: branch phase1-block1                           ║
║      verifies: git log shows pipeline commits on main        ║
╚══════════════════════════════════════════════════════════════╝
```

### Sparse Checkout Details

The worktree uses git cone-mode sparse checkout. Only the listed directories are present in the working tree; everything else (docker/, playground/, etc.) is excluded.

| Path | Why included |
|---|---|
| `app/` | All code changes happen here |
| `tests/` | Test files; implement and test stages write here |
| `docs/` | Document stage patches `docs/*.md` |
| `planning/` | Scout reads STATUS.md; plan reads MASTER\_PLAN; wrap-up writes STATUS.md + reports |
| `.claude/` | Commands and `sdlc-run.js` must resolve from the worktree CWD |
| *(root files)* | `CLAUDE.md`, `pyproject.toml`, `pytest.ini`, `uv.lock`, etc. — included automatically by cone mode |

### Parallel Block Execution

Multiple worktrees can run simultaneously when blocks are independent (e.g., one block touches `app/workflows/`, another touches `app/database/`). Each runs in its own session and branch. Merge order matters only if the blocks modify overlapping files — in that case, merge whichever finishes first and resolve any conflicts in the second before running `/clean-worktree` on it.

```
Main session                   Session A (trees/phase1-block1/)    Session B (trees/phase1-block2/)
─────────────                  ────────────────────────────────    ────────────────────────────────
/init-worktree phase1-block1   →  /sdlc-run phase1-block1
/init-worktree phase1-block2                                       →  /sdlc-run phase1-block2
                               ← done
/clean-worktree phase1-block1  (fast-forward merge → main)
                                                                   ← done
/clean-worktree phase1-block2  (fast-forward or resolve conflicts)
```

### Edge Cases

| Situation | Behavior |
|---|---|
| Name collision on init | Aborts with message; suggests `/clean-worktree` first |
| Orphan branch (dir gone, branch exists) | Detected at init time; exact resolution command printed |
| Uncommitted changes at clean time | Warning + confirmation required before proceeding |
| `main` has advanced since init | `--ff-only` fails cleanly; worktree left intact; resolution options shown |
| Pipeline crash mid-run | Per-stage commits preserve completed work on the branch; `/clean-worktree` still works |

---

## Ad-Hoc Work (no phase/block)

For work outside the structured phase/block plan, generate a spec with one of the ad-hoc planners, then feed it into the same Phase 2–6 pipeline.

```
/plan <description>    → planning/tasks/plan-{name}/tasks.md
/feature <description> → planning/tasks/feature-{name}/tasks.md
/chore <description>   → planning/tasks/chore-{name}/tasks.md
                                    │
                    same pipeline: /implement → /test → /review-task
                                   → /document → /log-work
```

---

## Gates

Three hard gates prevent a step from running until its prerequisite is satisfied:

| Gate | Enforced by | Behavior on failure |
|---|---|---|
| Review must PASS before document | `/document` reads the review report verdict | Stops immediately if FAIL or PARTIAL |
| Fresh tests must pass before PASS verdict | `/review-task` runs live tests | A test failure always produces FAIL/PARTIAL, regardless of code review |
| Review report must exist and be non-PASS to run fix | `/fix` reads the review report verdict | Hard-stops if report absent; soft-stops if verdict is already PASS |

---

## File Ownership Summary

| File | Created by | Written by | Read by |
|---|---|---|---|
| `planning/intake.md` | `/new-project` | `/new-project` | `/scaffold-project` |
| `planning/CONTEXT.md` | `/scaffold-project` | manually | `/prime`, most commands |
| `planning/STATUS.md` | `/scaffold-project` | `/start-block`, `/log-work` | `/status`, `/process-tasks`, `/session-recap`, `/log-work` |
| `planning/DECISIONS.md` | `/scaffold-project` | manually (prompted by `/log-work`) | `/prime` |
| `planning/MASTER_PLAN.md` | `/scaffold-project` | manually | `/generate-tasks` |
| `planning/tasks/<block>/tasks.md` | `/generate-tasks` | `/update-task` | `/implement`, `/test`, `/review-task`, `/document`, `/log-work` |
| `planning/tasks/<block>/breakdown.md` | `/breakdown` | — | auto-checked by `/implement`, `/fix`, and dynamic workflow implement + fix agents (`/sdlc-run`, `/sdlc-task`); authoritative for HOW; tasks.md stays authoritative for WHAT |
| `planning/tasks/<block>/reports/*` | `/implement`, `/fix`, `/test`, `/review-task`, `/document` | each step | the next step in the pipeline |
| `DEVLOG.md` | `/scaffold-project` | `/log-work` | `/session-recap` |
| `docs/*.md` | manually or `/scaffold-project` | `/document` | `/prime` |
