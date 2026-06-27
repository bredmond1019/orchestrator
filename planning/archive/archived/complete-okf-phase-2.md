---
type: Plan
title: Complete OKF — Phase 2 (orchestrator execution)
description: pos's execution of the workflow-coupled OKF changes deferred from Phase 1 — file renames, README→index, planning/ structure convergence, SDLC workflow adaptation, and scaffold-project removal.
---

# Plan: Complete OKF — Phase 2 (orchestrator)

> **Part of a multi-repo initiative.** Master tracker (state, decisions, execution order):
> `../../../planning/okf-initiative/index.md` in the company brain. This is workstream WS7.

## Context

This is pos's execution half of the OKF Phase 2 work that Phase 1 deferred because it
touches the SDLC workflow JS. **The shared decisions are NOT made here** — they are owned
by the brain coordination plan: `../../../planning/okf-phase-2/plan.md`. Do not start
until D-a … D-d there are settled, or pos will diverge from learn-ai and the template.

> **Prerequisite:** `orchestrator/planning/plans/update-repo-to-complete-okf.md`
> (Phase 1) must be done first — atomic `planning/decisions/`, OKF `docs/`.

This repo is Claude-only (`.claude/`, no `.agents/`).

## Why this can't be done alone

The three SDLC scripts (`.claude/workflows/sdlc-run.js`, `sdlc-task.js`, `sdlc-block.js`)
hard-depend on `planning/status.md`, `planning/master-plan.md`, root `log.md`, and
`planning/tasks/<stem>/`. After base-template exists, the **canonical** workflow copy
lives there — pos should take the rewritten scripts from base-template rather than
re-deriving them.

---

## Work Items (apply the brain's settled decisions)

### 1. Canonical document names (per coordination D-a)
Rename `planning/status.md` / `planning/master-plan.md` / root `log.md` / `context.md`
to the agreed canonical names. Update every reference: `CLAUDE.md` (which cites several
decisions + planning paths), `planning/index.md`, `planning/context.md`, the workflows,
and the `.claude/commands/` that read these files.

### 2. `README.md` → `index.md` (per coordination D-c)
Rename `planning/index.md` to `index.md` if adopted; repoint references. Not
workflow-load-bearing, low risk.

### 3. `planning/` structure convergence (per coordination D-b)
If the brain's concept-folder model is adopted, migrate `planning/tasks/<stem>/` to the
agreed layout (this is the bulk of the work — coupled to the workflow rewrite). Add
subfolder `index.md` files where the model calls for them (`planning/tasks/`,
`planning/blog/`). Note pos has several loose top-level planning docs
(`Agentic_*.md`, `Test_Plan.md`) — decide whether they become concept folders or stay.

### 4. Adopt the rewritten SDLC workflows from base-template
Pull the canonical, OKF-adapted scripts from base-template (adjusting only genuinely
pos-specific bits — e.g. Python/uv/pytest gate commands). Correct the residual "add to
`DECISIONS.md`" prompt strings to point at `planning/decisions/`. Note pos also has
`test-planning.js` and `health-check.js` workflows — check them for the same path
assumptions.

### 5. Delete the deprecated `scaffold-project` command
Once `/new-project` + `base-template/` parity is confirmed by the brain coordination plan,
delete `.claude/commands/scaffold-project.md` here. Its useful section depth was folded
into the template during the base-template build.

## Acceptance Criteria

- All renamed/moved files match the brain's canonical names + structure; no reference
  resolves to an old path.
- The three SDLC workflows (and `test-planning.js` / `health-check.js`) match the canonical
  shape and pass an end-to-end `/sdlc-task` regression run on a throwaway spec.
- `scaffold-project.md` removed.
- Residual `DECISIONS.md` prompt strings corrected.
- DEVLOG entry records the change and links the coordination plan.

## Dependencies

- **Owned decisions:** `../../../planning/okf-phase-2/plan.md` (D-a … D-d).
- **Prerequisite:** pos Phase 1 (`update-repo-to-complete-okf.md`) + `base-template/`
  exists with the rewritten workflows + `/new-project` parity confirmed (for the
  scaffold-project deletion).
