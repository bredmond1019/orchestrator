---
type: Reference
title: SDLC Dynamic Workflows Reference
description: Reference for the dynamic SDLC workflow scripts and how they compose pipeline stages at runtime.
---

# SDLC Dynamic Workflows Reference

*Automated, multi-agent SDLC pipelines — invoke once and the full pipeline runs end-to-end.*
*These are alternatives to running the manual slash commands (`/implement`, `/test`, etc.) step by step.*

---

## Overview

Two dynamic workflows automate the full SDLC pipeline:

| Workflow | Invocation | When to use |
|---|---|---|
| `/sdlc-run` | `/sdlc-run phase0-blockC [N]` | Single sequential task — runs on the current branch, updates STATUS/DEVLOG directly |
| `/sdlc-task` | `/sdlc-task phase0-blockC N` | Parallel-safe — auto-creates an isolated worktree, defers STATUS/DEVLOG to merge time |

Both run the same pipeline: scout → plan → implement → fix (if needed) → test → review → document → wrap-up. The differences are isolation, STATUS/DEVLOG timing, and whether a task number is required.

---

## Quick Reference

| Step | `/sdlc-run` | `/sdlc-task` |
|---|---|---|
| Worktree | None — runs on main branch | Auto-created at `trees/<branchName>/` |
| Task number | Optional (omit = full block) | Required |
| Branch | `main` | `<blockId-lowercased>-task<N>` |
| status.md update | During wrap-up (log-work agent) | Deferred — applied at `/clean-worktree` time |
| log.md update | During wrap-up (log-work agent) | Deferred — applied at `/clean-worktree` time |
| Report files | `planning/tasks/<block>/reports/` | Same path, inside the worktree |
| Merge step | Not needed | `/clean-worktree <branchName>` |
| Parallel-safe | No — STATUS/DEVLOG writes conflict | Yes — no shared file writes during the run |
| Max fix attempts | 3 | 3 |
| Resumable | Yes — scout detects existing reports | Yes — scout detects existing reports |

---

## Pipeline Stages (both workflows)

Both workflows run the same ordered stages. Each stage is a separate agent with its own context window; agents communicate only through report files on disk.

```
┌─────────────┐
│  Worktree   │  sdlc-task only — auto-create isolated branch + directory
└──────┬──────┘
       │
┌──────▼──────┐
│    Scout    │  Read existing report files → determine which stage to start from
└──────┬──────┘
       │
┌──────▼──────┐
│    Plan     │  Generate tasks.md spec (skipped if spec already exists)
└──────┬──────┘
       │
┌──────▼──────┐
│  Implement  │  Execute the task; commit feat: or fix: with code + implement report
└──────┬──────┘
       │
 ┌─────▼──────────────────────────────────────┐
 │         RETRY LOOP (max 3 attempts)         │
 │                                             │
 │  ┌──────────┐                               │
 │  │   Test   │  8-check suite (imports,      │
 │  └────┬─────┘  ruff, pylint, pytest)        │
 │       │                                     │
 │  ┌────▼─────┐                               │
 │  │  Review  │  Fresh pytest + criteria       │
 │  └────┬─────┘  check → PASS / FAIL /        │
 │       │        PARTIAL                       │
 │       │                                     │
 │    FAIL/PARTIAL?                            │
 │       │                                     │
 │  ┌────▼─────┐                               │
 │  │   Fix    │  Targeted fix → back to Test  │
 │  └──────────┘                               │
 └─────────────────────────────────────────────┘
       │
    PASS
       │
┌──────▼──────┐
│  Document   │  Surgically patch docs/; gates on PASS verdict
└──────┬──────┘
       │
┌──────▼──────┐
│   Wrap-up   │  sdlc-run: update STATUS + DEVLOG directly
│             │  sdlc-task: write task log (STATUS/DEVLOG deferred to merge)
└─────────────┘
```

### Breakdown file (optional)

If `/breakdown` has been run for the current block, both workflows automatically check for `planning/tasks/<blockId>/breakdown.md` at the start of the implement and fix stages.

| Agent | Behavior when breakdown.md exists |
|---|---|
| Implement | Finds the `### Step N:` section; uses its atomic sub-steps as the primary execution guide. Inline `Verify:` checkpoints are run live before advancing. |
| Fix | Reads the `### Step N:` section for original-intent context only; never re-implements from scratch. |

`tasks.md` remains the authoritative source for scope and acceptance criteria. `breakdown.md` is authoritative for _how_ to execute — exact file paths, function names, and atomic change boundaries.

If no `breakdown.md` exists the workflows proceed on `tasks.md` alone.

---

## Model Tiering & Token Cost

Each pipeline stage runs as its own agent, so each can run on a different model. `sdlc-task` tiers them from a single `MODEL` map at the top of the file. The guiding principle:

> **Match the model to the work: Opus plans, Haiku does the mechanics, Sonnet does the judgment in between.**

A sharp spec + breakdown makes implementation, testing, and verification well-scoped enough that Sonnet does them reliably — so only spec authoring needs Opus, while the purely-procedural stages drop to Haiku.

| Stage | Model | Why |
|---|---|---|
| `generate-tasks` | **opus** | Planning — authors the spec that drives everything. (Fallback only; see below.) |
| `scout` | **haiku** | Deterministic decision tree: `ls` a few files, apply a fixed 7-rule priority order to pick the start stage. No judgment. |
| `test` | **haiku** | Runs 8 fixed commands and reads exit codes; `review` re-runs `pytest` authoritatively, so a sloppy test report can't ship a bug. |
| `finalize` | **haiku** | Fills a **JS-precomputed** stage table and runs scripted `git add`s; it's the last step and can't break the pipeline. |
| `worktree-setup` | sonnet | Scripted git, but it runs once and a failure **aborts the whole pipeline** — high blast radius, tiny saving, so it stays on Sonnet. |
| `implement` | sonnet | Writes code + tests against a scoped spec/breakdown. |
| `fix` | sonnet | Targeted fixes; failures escalate, never silently ship. |
| `review` | sonnet | Verifies criteria — **gated by an authoritative fresh-test run**, so a cheap reviewer can't pass failing tests. |
| `document`, `task-log` | sonnet | Surgical doc patches and the **human-facing** DEVLOG/STATUS prose — quality matters, so they stay on Sonnet. |

Change one value in `MODEL` to re-tier; nothing else moves. Valid values: `'haiku' | 'sonnet' | 'opus' | undefined` (inherit the session model).

> The same three Haiku candidates (`scout`, `test`, `finalize`) — plus the trivial `start-block` agent — are tiered identically in **`sdlc-run`** (the sequential sibling). Before this, `sdlc-run` had *no* `MODEL` map, so every stage inherited the session model: launched from an Opus session, even scout/test/finalize ran on Opus. It now carries the same `MODEL` map and staged escalation as `sdlc-task`.

### Where the planning leverage actually is

Inside `sdlc-task`, `generate-tasks` is only a **fallback** that fires when the spec file is missing. Normally `tasks.md` and `breakdown.md` are authored **upstream** by the `/generate-tasks` and `/breakdown` skills — which run on your **session** model, not a per-agent override. So to cash in "Opus for planning," **run those two skills on an Opus session**, then let the pipeline grind on Sonnet. That upstream spec quality is exactly what makes Sonnet-everywhere-else reliable.

### Staged model escalation

`review` is the verdict gate and `fix` is the riskiest stage (debugging can get deep) — but neither needs Opus by default, because the structure protects them: review is gated by fresh tests, and a weak fix fails the loop and escalates rather than shipping. To cover the genuinely-hard case without paying Opus on every task, `sdlc-task` escalates the model **only on the last attempt before giving up**:

- the **final fix pass** (`fixPass === MAX_REVIEW_ATTEMPTS`) and
- the **final review attempt** (`reviewAttempts === MAX_REVIEW_ATTEMPTS`)

run on `ESCALATION_MODEL` (default `opus`). The first two fix/review cycles stay on Sonnet; only a task that has already failed twice gets one Opus shot before it wraps up FAIL (or, under `/sdlc-block`, escalates to triage). This is strictly better than "all Sonnet" (which misses hard cases) or "all Opus" (which overpays for easy ones). Set `ESCALATION_MODEL = null` to disable.

### Other levers

- **Triage-gated retries** (`/sdlc-block` only) — a clean-slate retry re-runs a full pipeline, so the orchestrator only spends that on *transient/progressing* failures, never a stuck one.
- **Plan caching** (`/sdlc-block` only) — `execution-plan.json` is committed and reused, skipping the dependency analysis on re-runs.
- **Output capping** *(available, not enabled)* — `test`/`review` currently pipe full `pytest`/`pylint` output into the agent; capping with `| tail -80` would bound input tokens on large/failing suites at the cost of some context. Apply only if cost on big suites becomes a concern.

> Tiering matters most under `/sdlc-block`, which fans this pipeline across many tasks — every per-stage saving multiplies by task count. See [sdlc-orchestration.md](sdlc-orchestration.md) for the orchestrator's own tiering.

---

## `/sdlc-run` — Sequential Pipeline

### Usage

```
/sdlc-run phase0-blockC        # run all tasks in the block
/sdlc-run phase0-blockC 3      # scope every stage to task 3 only
```

### What it does

Runs the full pipeline on the **current branch** (usually `main`). No worktree is created. After the pipeline completes, status.md and log.md are updated directly by the log-work agent in the wrap-up stage.

Best for:
- Sequential single-task work where parallel safety is not needed
- Resuming a partially-completed block (scout picks up where reports left off)
- Full-block runs (all tasks in one pipeline invocation)

### Flow

```
╔═══════════════════════════════════════════════════════════╗
║                /sdlc-run phase0-blockC [N]                ║
║                                                           ║
║  Scout → Plan → Implement → Test → Review                 ║
║         ↑          ↓ (FAIL/PARTIAL, max 3)                ║
║         └──── Fix ─┘                                      ║
║                   ↓ (PASS)                                ║
║              Document → Wrap-up                           ║
║                                                           ║
║  Wrap-up writes:                                          ║
║    planning/status.md    (updated directly)               ║
║    log.md             (new entry prepended)            ║
║    planning/tasks/<block>/reports/[taskN-]workflow.md     ║
╚═══════════════════════════════════════════════════════════╝
```

### Commit strategy

Each agent commits its own work immediately:

| Stage | Commit prefix | What is committed |
|---|---|---|
| Implement | `feat: implement <stem>` | code + implement report |
| Fix (each pass) | `fix: fix pass N for <stem>` | targeted changes + updated implement report |
| Document | `docs: update docs for <stem>` | patched docs/ files + document report |
| Wrap-up | `chore: wrap up <stem>` | status.md, log.md, test/review/workflow reports |

### Resumption

Re-run the same command if the pipeline is interrupted. The scout reads existing report files and skips completed stages:

| Report files present | Scout starts from |
|---|---|
| None | `implement` (or `generate-tasks` if no spec) |
| `implement.md` only | `test` |
| `implement.md` + `test.md` | `review` |
| `review.md` with FAIL/PARTIAL | `fix` |
| `review.md` with PASS | `document` |
| `document.md` | `wrap-up` |

---

## `/sdlc-task` — Parallel-Safe Isolated Pipeline

### Usage

```
/sdlc-task phase0-blockC 8     # run task 8 in its own worktree
/sdlc-task phase0-blockC 9     # can run simultaneously in a separate session
```

Task number is **required**. For full-block runs, use `/sdlc-run` instead.

### What it does

Creates an isolated git worktree at `trees/<branchName>/`, runs the full pipeline inside it, and writes a task log file instead of touching status.md or log.md. Because nothing shared is written during the run, multiple tasks can execute simultaneously without conflicts.

After the pipeline completes, merge the branch back to main:

```
/clean-worktree <branchName>
```

`/clean-worktree` merges the branch, reads the task log, applies the status.md and log.md updates, and removes the worktree.

### Flow

```
╔═══════════════════════════════════════════════════════════╗
║              /sdlc-task phase0-blockC 8                   ║
║                                                           ║
║  [Worktree] Auto-create trees/phase0-blockc-task8/        ║
║             branch: phase0-blockc-task8                   ║
║                                                           ║
║  All subsequent agents cd into the worktree.              ║
║  All git commits go to branch phase0-blockc-task8.        ║
║  status.md and log.md are NEVER touched.               ║
║                                                           ║
║  Scout → Plan → Implement → Test → Review                 ║
║         ↑          ↓ (FAIL/PARTIAL, max 3)                ║
║         └──── Fix ─┘                                      ║
║                   ↓ (PASS)                                ║
║              Document → Wrap-up                           ║
║                                                           ║
║  Wrap-up writes:                                          ║
║    planning/tasks/<block>/reports/task8-log.md  ← deferred║
║    planning/tasks/<block>/reports/task8-workflow.md       ║
╚═══════════════════════════════════════════════════════════╝
                         │
                 pipeline complete
                         │
                         ▼
╔═══════════════════════════════════════════════════════════╗
║         /clean-worktree phase0-blockc-task8               ║
║         (run from main repo session)                      ║
║                                                           ║
║  1. Show uncommitted changes (warn if any)                ║
║  2. Show unpushed commits (for review)                    ║
║  3. git merge --ff-only phase0-blockc-task8               ║
║  4. Read task8-log.md → apply status.md + log.md       ║
║     Mark log Applied: true                                ║
║     Commit: chore: apply task log for phase0-blockC-task8 ║
║  5. git worktree remove trees/phase0-blockc-task8         ║
║  6. git branch -D phase0-blockc-task8                     ║
╚═══════════════════════════════════════════════════════════╝
```

### Worktree naming convention

The branch and directory name are derived deterministically:

```
blockId:   phase0-blockC   taskN: 8
branch:    phase0-blockc-task8
directory: trees/phase0-blockc-task8/
```

If that name is already taken (branch or worktree exists), the setup agent auto-increments a suffix:

```
phase0-blockc-task8-2
phase0-blockc-task8-3
...  (capped at -10)
```

The final branch name is always printed in the pipeline output and written to the task log. Pass it exactly to `/clean-worktree`.

### Sparse checkout

The worktree uses cone-mode sparse checkout. Included paths:

| Path | Why |
|---|---|
| `app/` | All code changes |
| `tests/` | Test files |
| `docs/` | Document stage patches `docs/*.md` |
| `planning/` | Scout reads status.md; spec + reports live here |
| `.claude/` | Commands and workflows resolve from the worktree CWD |
| *(root files)* | `CLAUDE.md`, `pyproject.toml`, `uv.lock`, `log.md`, etc. — auto-included by cone mode |

### The task log

Instead of updating status.md and log.md during the pipeline, the wrap-up agent writes a structured `task<N>-log.md`:

```markdown
# Task Log — phase0-blockC task 8

**Block:** phase0-blockC
**Task:** 8
**Verdict:** PASS
**Date:** 2026-06-08
**Branch:** phase0-blockc-task8
**Applied:** false

---

## status.md — Block Status
[present only if block was "Not started" — value: "In progress"]

## status.md — Current Focus Line
Phase 0, Block C — Task 9: Validate

## status.md — Last Updated Line
2026-06-08 — Block C in progress (Tasks 1–8 complete; Tasks 9–N next — ...)

## status.md — Block Notes Column
Tasks 1–8 complete; Task 9 (Validate) next.

---

## DEVLOG Entry

## 2026-06-08 (task 8 — ...)

[paragraph describing what was done, verdict, any findings]

```git log --oneline output```
```

`/clean-worktree` reads this file, applies each section to the correct location in status.md and log.md, then flips `Applied: false` → `Applied: true` and commits. If the log has already been applied, it is skipped.

---

## Parallel Task Execution

Run multiple tasks simultaneously — each in its own worktree session:

```
Main session                   Session A                    Session B
─────────────                  ─────────────────────────    ─────────────────────────
                                                            (both start simultaneously)
                               /sdlc-task phase0-blockC 8  /sdlc-task phase0-blockC 9
                               ... pipeline running ...     ... pipeline running ...
                               ← task 8 complete            ← task 9 complete

/clean-worktree phase0-blockc-task8   ← merge task 8 FIRST
/clean-worktree phase0-blockc-task9   ← then task 9
```

**Merge in task-number order.** Each task log's `## status.md — Current Focus Line` says "next up is task N+1." If you merge task 9 before task 8, status.md ends up pointing at task 10 before task 8 has been applied. Merge in ascending order to keep Current focus accurate.

**Before starting parallel tasks**, if the block is "Not started", run `/start-block phase0-blockC` from the main session first — this flips status.md to "In progress" immediately so all worktrees see the correct block status when their scouts run. Alternatively, the task log for the first-merged task will flip it during `/clean-worktree`.

---

## Report Files

Both workflows write to the same report directory: `planning/tasks/<block>/reports/`

| Report | Written by | Read by |
|---|---|---|
| `task<N>-implement.md` | Implement agent; overwritten by each Fix pass | Review agent |
| `task<N>-test.md` | Test agent | Review agent |
| `task<N>-review.md` | Review agent | Document agent; Fix agent |
| `task<N>-document.md` | Document agent | — |
| `task<N>-log.md` | Wrap-up (sdlc-task only) | `/clean-worktree` |
| `task<N>-workflow.md` | Finalize agent | Human review; `/review-workflow` |

Full-block runs (no task number) use the same names without the `task<N>-` prefix.

---

## Choosing Between the Three Approaches

| Situation | Recommended |
|---|---|
| Step-by-step with human checkpoints between stages | Manual slash commands (`/implement`, `/test`, etc.) |
| Single task or full block, no parallelism needed | `/sdlc-run` |
| Multiple tasks running at the same time | `/sdlc-task` (one per session) |
| Risky or experimental work — keep main clean until done | `/sdlc-task` (or `/init-worktree` + `/sdlc-run`) |
| Resume an interrupted pipeline run | Either workflow — scout auto-detects stage from reports |

---

## Edge Cases

| Situation | Behavior |
|---|---|
| Spec file missing when pipeline starts | Scout sets `generate-tasks` as start stage; Plan agent writes the spec first |
| Review FAIL after 3 attempts | Pipeline skips document and wraps up with FAIL status; fix manually then re-run |
| Worktree name collision (`-task8` already exists) | Setup agent tries `-2`, `-3` ... up to `-10`; reports the chosen name |
| main has advanced since worktree was created | `/clean-worktree` `--ff-only` fails cleanly; worktree left intact; rebase or merge-commit options printed |
| Task log already applied | `/clean-worktree` detects `Applied: true` and skips STATUS/DEVLOG update |
| Pipeline crash mid-stage | Per-stage commits preserve completed work on the branch; re-run the same command to resume |
| Block is "Not started" in status.md | sdlc-run flips it immediately; sdlc-task records it in the task log (applied at merge time) |
