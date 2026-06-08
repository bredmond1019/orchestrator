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
| **1 — Plan** | `/generate-tasks <id>` | MASTER_PLAN + CLAUDE.md | `planning/tasks/<spec>.md` |
| **1 — Plan (opt.)** | `/breakdown [spec]` | spec file + source files | `planning/tasks/breakdown-<spec>.md` |
| **2 — Implement** | `/implement <spec> [N]` | spec file + source files | code changes + implement report |
| **2 — Track** | `/update-task [id] <step>` | spec file | spec file (in-place) |
| **2 — Commit** | `/commit [hint]` | git diff | git history |
| **3 — Test** | `/test <spec> [N]` | spec file | test report |
| **4 — Review** | `/review-task <spec> [N]` | spec + implement + test reports | review report (PASS/FAIL) |
| **5 — Document** | `/document <spec> [N]` | review report (must be PASS) + implement report | patched `docs/*.md` + document report |
| **6 — Wrap-up** | `/log-work [notes]` | STATUS + spec + DEVLOG + git diff | updated STATUS.md + DEVLOG.md |
| **Ad-hoc** | `/plan <desc>` | description | `planning/tasks/plan-{name}.md` |
| **Ad-hoc** | `/feature <desc>` | description | `planning/tasks/feature-{name}.md` |
| **Ad-hoc** | `/chore <desc>` | description | `planning/tasks/chore-{name}.md` |

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
║                         spec, reports/ listing               ║
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
║      writes: planning/tasks/phase0-blockC.md   ◄── SPEC FILE ║
║                                                              ║
║                    │ (optional)                              ║
║                    ▼                                         ║
║  /breakdown [planning/tasks/phase0-blockC.md]                ║
║      reads: spec file                                        ║
║             source files each step touches                   ║
║      writes: planning/tasks/breakdown-phase0-blockC.md       ║
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
║  /implement planning/tasks/phase0-blockC.md [N]              ║
║      reads: spec file (full block or task N)                 ║
║             CLAUDE.md                                        ║
║             source files to touch                            ║
║      writes: code changes in working tree                    ║
║              planning/tasks/reports/                         ║
║                phase0-blockC[-taskN]-implement.md            ║
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
║  /test planning/tasks/phase0-blockC.md [N]                   ║
║      reads: spec file (for context and report naming)        ║
║      runs: import checks → ruff → pylint → pytest collect    ║
║             → pytest full                                    ║
║      writes: planning/tasks/reports/                         ║
║                phase0-blockC[-taskN]-test.md                 ║
╚══════════════════════════════════════════════════════════════╝
                            │
                            ▼
╔══════════════════════════════════════════════════════════════╗
║                  PHASE 4 — REVIEW                            ║
║                                                              ║
║  /review-task planning/tasks/phase0-blockC.md [N]            ║
║      reads: spec file (acceptance criteria)                  ║
║             implement report (historical context)            ║
║             test report (historical context)                 ║
║      runs:  FRESH test suite (authoritative)                 ║
║      writes: planning/tasks/reports/                         ║
║                phase0-blockC[-taskN]-review.md               ║
║              verdict: PASS | PARTIAL | FAIL                  ║
╚══════════════════════════════════════════════════════════════╝
                 │                    │
              PASS                 FAIL/PARTIAL
                 │                    │
                 ▼                    ▼
╔═════════════════════╗    ╔══════════════════════╗
║  PHASE 5 — DOCUMENT ║    ║  back to IMPLEMENT   ║
║                     ║    ║  fix the issues,     ║
║  /document          ║    ║  re-run /test and    ║
║   <spec> [N]        ║    ║  /review-task        ║
║                     ║    ╚══════════════════════╝
║  reads:             ║
║   review report     ║
║   (gates on PASS)   ║
║   implement report  ║
║   (Files Modified   ║
║    table)           ║
║   affected source   ║
║   files             ║
║  writes:            ║
║   docs/*.md         ║
║   (surgical patches ║
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
║             planning/tasks/phase0-blockC.md                  ║
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

The spec file (`planning/tasks/phase0-blockC.md`) is the thread that runs through Phases 1–6. Every command from `/implement` onward takes it as its primary argument.

```
/generate-tasks  ──writes──▶  planning/tasks/phase0-blockC.md
                                          │
                    ┌─────────────────────┼──────────────────────┐
                    ▼                     ▼                      ▼
              /implement             /test                /review-task
              (reads spec)           (reads spec          (reads spec
                                      for naming)          for criteria)
```

**The `[N]` optional task number** scopes the entire pipeline (implement → test → review → document) to a single task within the spec. Use the same `N` for every step — it determines all report filenames.

```
/implement planning/tasks/phase0-blockC.md 3
/test      planning/tasks/phase0-blockC.md 3
/review-task planning/tasks/phase0-blockC.md 3
/document  planning/tasks/phase0-blockC.md 3
```

All four write to `reports/phase0-blockC-task3-{step}.md`.

---

## Report Files

All pipeline reports live in `planning/tasks/reports/`. Naming pattern: `{spec-stem}[-taskN]-{step}.md`

| Step | Full-block report | Task-scoped report |
|---|---|---|
| implement | `phase0-blockC-implement.md` | `phase0-blockC-task3-implement.md` |
| test | `phase0-blockC-test.md` | `phase0-blockC-task3-test.md` |
| review | `phase0-blockC-review.md` | `phase0-blockC-task3-review.md` |
| document | `phase0-blockC-document.md` | `phase0-blockC-task3-document.md` |

Each step reads the previous step's report as historical context. `/review-task` is the only step that re-runs live tests rather than trusting the test report.

---

## Ad-Hoc Work (no phase/block)

For work outside the structured phase/block plan, generate a spec with one of the ad-hoc planners, then feed it into the same Phase 2–6 pipeline.

```
/plan <description>    → planning/tasks/plan-{name}.md
/feature <description> → planning/tasks/feature-{name}.md
/chore <description>   → planning/tasks/chore-{name}.md
                                    │
                    same pipeline: /implement → /test → /review-task
                                   → /document → /log-work
```

---

## Gates

Two hard gates prevent a step from running until its prerequisite is satisfied:

| Gate | Enforced by | Behavior on failure |
|---|---|---|
| Review must PASS before document | `/document` reads the review report verdict | Stops immediately if FAIL or PARTIAL |
| Fresh tests must pass before PASS verdict | `/review-task` runs live tests | A test failure always produces FAIL/PARTIAL, regardless of code review |

---

## File Ownership Summary

| File | Created by | Written by | Read by |
|---|---|---|---|
| `planning/intake.md` | `/new-project` | `/new-project` | `/scaffold-project` |
| `planning/CONTEXT.md` | `/scaffold-project` | manually | `/prime`, most commands |
| `planning/STATUS.md` | `/scaffold-project` | `/start-block`, `/log-work` | `/status`, `/process-tasks`, `/session-recap`, `/log-work` |
| `planning/DECISIONS.md` | `/scaffold-project` | manually (prompted by `/log-work`) | `/prime` |
| `planning/MASTER_PLAN.md` | `/scaffold-project` | manually | `/generate-tasks` |
| `planning/tasks/<spec>.md` | `/generate-tasks` | `/update-task` | `/implement`, `/test`, `/review-task`, `/document`, `/log-work` |
| `planning/tasks/reports/*` | `/implement`, `/test`, `/review-task`, `/document` | each step | the next step in the pipeline |
| `DEVLOG.md` | `/scaffold-project` | `/log-work` | `/session-recap` |
| `docs/*.md` | manually or `/scaffold-project` | `/document` | `/prime` |
