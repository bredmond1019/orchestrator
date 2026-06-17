---
type: Decision
title: D27 — Adopt OKF Phase 2 conventions (lowercase names, concept-folder planning, index.md)
description: This repo converges to the cross-repo OKF Phase 2 conventions settled in the company brain (D15–D18) during the WS7 lockstep workflow rewrite, and retires the deprecated scaffold-project command.
---

# D27 — Adopt OKF Phase 2 conventions (lowercase names, concept-folder planning, `index.md`)

**Decided:** This repo adopts the cross-repo OKF Phase 2 conventions settled in the company
brain (brain decisions D15–D18), applied during the WS7 lockstep workflow rewrite:

- **Lowercase document names** (brain D15): `STATUS.md`→`status.md`, `DEVLOG.md`→`log.md`,
  `MASTER_PLAN.md`→`master-plan.md`, `CONTEXT.md`→`context.md`; `decisions/` unchanged.
- **Concept-folder `planning/` model** (brain D16): replace `planning/tasks/<stem>/` with the
  brain's concept-folder model; SDLC machine artifacts (`execution-plan.json`, `reports/`) move
  to a reserved subfolder inside each concept folder (exact path fixed in the workflow rewrite).
  The loose planning docs (`Agentic_*.md`, `Test_Plan.md`) are reconciled into this model in the
  same pass.
- **`index.md` directory listings** (brain D17) across `planning/` and its subfolders.
- **Template propagation** (brain D18): harness improvements arrive from `base-template/` via
  manual pull + its changelog.

The three SDLC scripts (`sdlc-run.js`, `sdlc-task.js`, `sdlc-block.js`) are rewritten to the new
names/paths in lockstep with learn-ai and base-template. The deprecated `scaffold-project`
command is deleted once `/new-project` parity is confirmed.
**Why:** Phase 2 is workflow-coupled — the SDLC scripts hard-depend on the old filenames and the
`tasks/<stem>/` glob, and these scripts are duplicated across repos, so the rename + structure
change must land everywhere at once or the pipeline breaks. Converging on one canonical OKF shape
(base-template as reference) keeps generated projects and the existing repos identical. Full
rationale lives in the brain decisions D15–D18 and `planning/okf-phase-2/plan.md` (brain).
**Rejected:** Keeping UPPERCASE names / the `tasks/<stem>/` model to avoid churn — rejected in
favor of full convergence (brain D15/D16); the rename cost is absorbed by the workflow rewrite
that Phase 2 requires regardless. Retaining `scaffold-project` — rejected; `/new-project` (cloning
base-template) fully supersedes it.
