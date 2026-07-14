---
type: TaskSpec
title: Task Spec — Bastion Program Block OR.U (Eval + Success-Metrics Engine)
description: Decomposed task spec for OR.U — offline eval harness, scorer library, regression history, one-change self-improvement gate, coding slice, and eval CLI.
doc_id: or-u-eval-engine-tasks
layer: [engine]
project: orchestrator
status: active
keywords: [eval harness, success metrics, LLM-as-judge, regression history, self-improvement loop, model routing, coding eval]
related: [master-plan, status]
---

# Task Spec — Bastion Program, Block OR.U (Eval + success-metrics engine)

**Status:** Not started · **Last run:** never

## Goal
Stand up an evaluation + success-metrics engine: an offline eval harness with a scorer library
(deterministic / reference-based / blind LLM-as-judge), persisted regression history across runs,
a keep-if-better/revert-if-worse gate for the one-change self-improvement loop, and the coding
domain (Block Z's SDLC runs) as the first slice.

## Context Pointers
- Block contract: `planning/master-plan.md` → "### OR.U — Eval + success-metrics engine (elevates Project H)".
- Build-detail seed: `planning/master-plan.md` → "### OR.1.H — Model Evaluation & Routing Harness"
  (scoring strategies by node type, blind/randomized judge, per-node routing config output).
- **Design principle (D33 / local D8): offline eval, not runtime router.** The harness runs
  occasionally and deliberately; routing decisions bake into per-node `model_provider` config at
  design time. No workflow/registry entries are needed — this is an offline CLI + library, like
  `scripts/index_brain.py`.
- Standing rules that bite here: every prompt is a `.j2` in `app/prompts/` via `PromptManager`
  (rule 2); every task ships tests (rule 1); persistence via `GenericRepository` (rule 7);
  Python 3.10+ type syntax, no f-strings in logging, `raise ... from e` (code style section).
- Test-suite constraint: the in-memory SQLite suite (`tests/conftest.py`) cannot compile
  PG-specific column types — it excludes `brain_documents`. The new eval tables must use
  SQLite-compilable types (follow `learning_artifact.py` / `event.py` patterns, not
  `brain_document.py`) so unit tests run without Docker.
- Out of scope (hard boundary from the block): model-routing *enforcement* (producing the routing
  config file is in; wiring it into runtime node config is not); per-harness evals beyond the
  coding slice; external-idea intake (Block W); autonomy promotion itself (Block X — this block
  only produces the signals that license it).

## Step-by-Step Tasks
See `tasks.json` in this directory — the task list is defined there, not here.

## Acceptance Criteria
- An eval slice runs **offline** via `scripts/run_eval.py` and scores pass-rate aggregated
  **by domain and by model**, printed as a table and persisted.
- Regression history persists across runs: two successive runs of the same slice produce two
  queryable run records, and the second can be compared against the first.
- The scorer library covers the three Project-H strategies: deterministic/structural
  (schema-valid, required fields, values in range), reference-based (compare against a labeled
  set), and LLM-as-judge with **blind scoring** (model identity stripped) and **randomized
  candidate order**, its rubric prompt loaded from `app/prompts/eval_judge.j2` via `PromptManager`.
- A representative slice gates a change via the one-change loop: given a baseline run and a
  candidate run, the gate returns keep-if-better / revert-if-worse, demonstrated in tests for
  both directions plus the tie case.
- The coding domain is the first slice: it scores recorded SDLC run records (pass-rate,
  retry rate, review-verdict rate) with deterministic scorers, proven against fixtures.
- `--emit-routing` writes a per-node routing config file (quality retention vs cost per model);
  nothing in `app/core/` or `app/workflows/` reads it (enforcement out of scope).
- The orchestrator gate holds: full pytest suite passes with no decrease in collected-test
  count, `ruff check app/` clean, `pylint app/` 10.00/10, `alembic upgrade head` applies cleanly.

## Validation Commands
```
uv run python -m pytest
uv run python -m ruff check app/
uv run python -m pylint app/
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
```
<!-- Standard project checks per planning/harness.json (validation.checks[]); the harness also
     runs the standing-rules forbidden-pattern scan, net-new-lint baseline diff, and
     pytest-count delta automatically. -->

## Notes
- Slug convention follows prior program blocks (`or-o-widen-index-corpus`, `or-g-graph-aware-rag`).
- Alembic: new model must be imported in `app/alembic/env.py` (the "required for autogenerate
  support" block) and exported from `app/database/__init__.py`.
- `app/evals/__init__.py` is owned by Task 2 and stays a docstring-only module marker; later
  tasks import submodules directly (`from evals.judge import ...`) and never edit it — this keeps
  task file ownership disjoint for parallel-merge safety.

## Amendment Log
<!-- Append-only. Pipeline stages append one dated line here when they deviate from the spec. -->
_No amendments yet._
