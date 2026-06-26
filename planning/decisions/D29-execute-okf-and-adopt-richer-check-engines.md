---
type: Decision
title: Execute the OKF Phase 2 migration; adopt base-template's richer-check + token-telemetry engines
description: The OKF Phase 2 conventions agreed in D27 are now executed in this repo, in lockstep with pulling base-template's rewritten SDLC engines (richer-check kinds, per-stage token telemetry).
doc_id: D29-execute-okf-and-adopt-richer-check-engines
layer: [engine, meta]
project: python-orchestration
status: active
keywords: [OKF Phase 2 migration, SDLC engines, richer-check, token telemetry, harness.json]
related: [D27-adopt-okf-phase-2-conventions, planning-index]
---

# D29 — Execute OKF Phase 2; adopt base-template's richer-check + telemetry engines

**Decided:** The OKF Phase 2 conventions agreed in [D27](D27-adopt-okf-phase-2-conventions.md) are now
**executed** in this repo, in lockstep with pulling base-template's rewritten SDLC engines:

- **Engines replaced** from base-template (provenance commit `45504b5`): `.claude/workflows/{sdlc-run,
  sdlc-task,sdlc-block}.js` plus `harness.schema.json` and `templates/spec-template.md`. These are the
  agnostic, zero-stack-default engines (base-template D5) carrying **per-stage token telemetry**
  (`tracedAgent` + `filesReadKb` probe + metrics emit) and the **richer validation check kinds**
  (base-template D6). The OKF-agnostic command set replaced the old pre-OKF commands.
- **Validation externalized to `planning/harness.json`.** The old engine hardcoded an 8-check Python
  suite (CHECK 0–8.5). That suite is now expressed faithfully in `harness.json` via the new kinds —
  `forbidden-pattern-scan` (CLAUDE.md standing rules), `warning-scan` (Pydantic field-shadow warnings
  on app/worker import), `baseline-diff` (ruff net-new violations vs a worktree-creation baseline),
  `count-delta` (pytest collection count must not regress), plus plain commands (imports, pylint,
  full pytest = authoritative). **No validation behavior was lost** in the move.
- **Lowercase doc names** (`CONTEXT→context`, `STATUS→status`, `MASTER_PLAN→master-plan`,
  `DEVLOG→log`, `planning/README→planning/index`); references updated across the docs.
- **Pre-OKF tasks archived.** The 153 finished files under `planning/tasks/` moved to
  `archive/planning-tasks-pre-okf/`. New work uses the concept-folder model: `planning/<concept>/
  tasks.md` with pipeline state under `planning/<concept>/sdlc/`.
- **Brain-level / one-off harness files pruned:** `commands/{new-project,scaffold-project,blog-idea}.md`
  and `workflows/review-and-merge-tasks-9-12.js` removed. Project-specific workflows
  (`health-check.js`, `test-planning.js`, `generate-new-docs.js`) kept.

**Why:** D27 decided the conventions but the engines still hardcoded the old uppercase names, the
`planning/tasks/<stem>/` model, and the Python validation suite. Importing the token-telemetry work
(the catalyst) required adopting base-template's engines, which assume the OKF layout and read
`harness.json` — so the rename, the structure change, and the engine swap had to land together (the
lockstep D27 anticipated). The richer check kinds (base-template D6) were created specifically so this
migration would not silently drop the net-new-lint / count-delta / warning / standing-rule mechanics.

**This does not touch D28.** Node-level execution state lives in the application/framework code
(`Workflow.run`, the Celery worker, `TaskContext`), not in `.claude/workflows/` — the engine swap is
orthogonal to it.

**Rejected:**
- *Grafting telemetry onto the old engines* — would have kept the pre-OKF layout and the hardcoded
  stack, diverging permanently from base-template. Rejected for full convergence.
- *Simplifying the validation suite to plain `ruff`/`pytest` gating* — would have dropped the
  net-new-diff, count-delta, and warning capture this repo already relied on. Rejected; preserved via
  the richer kinds instead.

**Provenance / verification:** base-template `45504b5`. `node --check` passes on all three engines;
`harness.json` parses (10 checks). Live `/sdlc-task` baseline capture is the next step (tracked in
`status.md` and base-template `planning/plans/sdlc-telemetry-updates.md`).
