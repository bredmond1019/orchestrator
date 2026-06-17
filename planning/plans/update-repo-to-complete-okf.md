---
type: Plan
title: Update python-orchestration-system to Complete OKF (Phase 1)
description: Close the deliberately-deferred OKF gaps in the orchestration repo without disturbing the SDLC workflows — split DECISIONS, OKF-frontmatter docs/, update log-work.
---

# Plan: Update python-orchestration-system to Complete OKF — Phase 1

> **Part of a multi-repo initiative.** Master tracker (state, decisions, execution order):
> `../../../planning/okf-initiative/index.md` in the company brain. This is workstream WS2.

## Context

The 2026-06-17 OKF migration intentionally stopped short here to avoid disturbing the
JS SDLC pipeline (`sdlc-task.js`, `sdlc-block.js`, `sdlc-run.js`). Frontmatter was
added everywhere, but the aggregate `DECISIONS.md` and the un-OKF'd `docs/` folder were
left in the old shape. This plan closes those gaps with **additive, workflow-safe**
changes only.

**This is Phase 1.** It touches **no workflow JS**, renames no load-bearing file, and
does not converge `planning/` onto the brain's new structure. Those are Phase 2 (see
*Out of Scope*). This repo is Claude-only (`.claude/`, no `.agents/`), so there are no
Antigravity skill twins to update.

## Load-bearing files — DO NOT touch in this phase

The workflows hard-depend on these names/paths. Leave them exactly as they are:

- `planning/STATUS.md` (read + single authoritative update at merge)
- `planning/MASTER_PLAN.md` (read for block context)
- **root** `DEVLOG.md` (read + prepend below frontmatter)
- `planning/tasks/<stem>/tasks.md`, `execution-plan.json`, `reports/`
- All `.claude/workflows/*.js`

Verified safe: the workflows **never read or write `DECISIONS.md`** — they only surface
a free-text `notes` field to the human at merge time. Splitting decisions is safe at the
workflow layer; only `log-work` and a few prose pointers reference it.

---

## Work Items

### 1. Split `DECISIONS.md` → `planning/decisions/` (atomic OKF)

Mirror what the brain repo did for `docs/decisions/`.

- Create `planning/decisions/D{N}-<kebab-title>.md` per decision, each with:
  ```yaml
  ---
  type: Decision
  title: D{N} — Short Title
  description: One-sentence summary.
  ---
  ```
  Preserve each entry's **Decided / Why / Rejected** body verbatim. Note this repo
  already has a deep decisions log (D1–D20+ referenced in CLAUDE.md) — split *all* of
  them, keeping the existing numbering.
- Create `planning/decisions/index.md` (`type: Index`) — the registry, newest at the
  bottom, append-only convention preserved.
- Delete the old aggregate `planning/DECISIONS.md`.
- Update prose pointers to the new path (NOT the workflow JS):
  - `CLAUDE.md` — "Before you start" references D6/D16/D17/D18/D20 and
    `planning/DECISIONS.md`; repoint to `planning/decisions/`.
  - `planning/CONTEXT.md` — Document Set table row.
  - `planning/README.md` — files table.

> **Known seam (accepted):** workflow `notes`-field prompt strings still say
> "DECISIONS.md". Descriptive only, no file operations — corrected in Phase 2. Record
> this in the DEVLOG entry so it isn't read as an oversight.

### 2. Update the `log-work` command to write atomic decisions

`.claude/commands/log-work.md` (no `.agents` twin in this repo).

- Replace the step that points the user at `planning/DECISIONS.md` with the brain
  `log-decision` pattern: on a settled choice, **ask first**, then create
  `planning/decisions/D{N+1}-<kebab>.md` with OKF frontmatter and register it in
  `planning/decisions/index.md`. Keep the ask-first guard.

### 3. OKF-frontmatter the `docs/` folder + add `docs/index.md`

`docs/` (developer reference) currently has **no** OKF treatment.

- Add frontmatter to `docs/api-reference.md` (`type: Reference`),
  `docs/configuration.md` (`type: Reference`),
  `docs/app-architecture-overview.md` (`type: Architecture`), and the markdown under
  `docs/agentic-workflows/` (`type: Reference`) and `docs/architecture_review/`
  (`type: Reference`).
- Create `docs/index.md` (`type: Index`) listing the docs with one-line descriptions.
- Content unchanged — frontmatter prepend only. The CLAUDE.md "Documentation" table
  links to `docs/api-reference.md` and `docs/configuration.md`; those links still
  resolve (no rename).

### 4. Note on `scaffold-project.md` — do NOT bring to complete OKF

`scaffold-project` is a deprecated first pass that the brain's `/new-project` +
`base-template/` repo supersede (see `../../planning/base-project-template/plan.md`). Its
useful section depth (the A–H specs) is being folded into the template, not preserved here.
Do **not** invest in making it
OKF-complete here — its replacement is handled centrally. Leave it as-is; its removal is
tracked in the new-project plan.

---

## Acceptance Criteria

- `planning/decisions/` exists with one atomic file per prior decision + an `index.md`
  registry; old `planning/DECISIONS.md` removed; CLAUDE.md / CONTEXT.md / README pointers
  updated.
- `log-work.md` creates atomic decision files instead of pointing at a single aggregate,
  ask-first guard intact.
- Every file in `docs/` carries OKF frontmatter; `docs/index.md` exists.
- A careful read of the three workflow scripts confirms no reference resolves to a
  moved/renamed file. No workflow JS was modified.
- DEVLOG entry records the change and the accepted "DECISIONS.md string" seam.

## Out of Scope — Phase 2 (named, deferred)

> Now captured as a real plan: `complete-okf-phase-2.md` (this repo), coordinated by the
> brain's `../../../planning/okf-phase-2/plan.md`.

1. `README.md` → `index.md` renames across `planning/` and subfolders.
2. `index.md` files inside `planning/tasks/`, `planning/blog/`.
3. Adapting `sdlc-block.js` / `sdlc-task.js` / `sdlc-run.js` to the OKF model (and
   correcting residual "DECISIONS.md" prompt strings).
4. Converging `planning/` onto the brain's structure model (concept-folders,
   flat-vs-subdirectory, workspace vs committed-effort).
5. Standardizing the canonical names of `MASTER_PLAN` / `STATUS` / `DEVLOG`.
6. Removing the deprecated `scaffold-project` command once `/new-project` fully covers it.
