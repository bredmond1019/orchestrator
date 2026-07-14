---
type: Reference
title: Offline Eval Harness (Bastion Program Block OR.U)
description: The app/evals/ library and scripts/run_eval.py CLI — scorers, LLM-as-judge, slices, the runner/regression-history persistence, and the one-change self-improvement gate.
doc_id: evals
layer: [engine]
project: orchestrator
status: active
keywords: [evals, eval harness, scorers, llm-as-judge, regression history, self-improvement gate, run_eval.py, coding slice]
related: [api-reference, scripts, data-contract, sdlc-flow-workflow]
---

# Offline Eval Harness (Bastion Program Block OR.U)

`app/evals/` is an offline library — it has no `TaskContext`/workflow coupling and is not run by
Celery. It scores model/pipeline outputs against `EvalCase`s, persists the results as regression
history, and exposes a one-change self-improvement gate. `scripts/run_eval.py` is the CLI that
drives it end to end.

## Data model (`app/database/eval_record.py`)

Two SQLAlchemy tables (migration `f6a7b8c9d0e1_create_eval_runs_and_results_tables.py`), kept
SQLite-compilable so the in-memory test suite can create them without Docker:

| Table | Purpose |
|---|---|
| `EvalRun` | One row per `(slice_name, model_name)` execution: `pass_rate`, `case_count`, `passed_count`, optional `total_cost` / `total_duration_seconds`, free-form `meta`. |
| `EvalResult` | One row per scored case within a run (FK `run_id -> eval_runs.id`): `case_id`, `scorer`, `passed`, optional `score`, free-form `detail`. |

Both are exported from `app/database/__init__.py` and registered in `app/alembic/env.py`.

## Scorers (`app/evals/scorers.py`)

Common signature: `(output, case) -> ScoreResult` (`passed: bool`, `score: float | None`,
`detail: dict | None`). `case` is duck-typed (via `getattr`) against `EvalCase`'s attributes, so
this module has no dependency on `evals.slice`.

- `deterministic_scorer` — validates `output` against `case.schema_cls`, `case.required_fields`,
  and `case.value_ranges`; each check is independently optional (a check not declared on the case
  is skipped, not failed).
- `reference_scorer` — normalized field matching against `case.reference`; an empty/absent
  reference is a trivial pass (`score=1.0`).

## LLM-as-judge (`app/evals/judge.py`)

Blind, randomized LLM-as-judge scorer for open-ended prose outputs:

1. **Strips model identity** — candidates are addressed only as `candidate_1`, `candidate_2`, ...
2. **Randomizes presentation order** via an injectable `rng`/seed (reproducible in tests);
   `anonymize_candidates(candidates, rng)` is exposed standalone so tests can assert the shuffle
   and the label→candidate_id mapping independently of the (mocked) model call.
3. Renders the rubric (`rubric_criteria: list[str]`) through `app/prompts/eval_judge.j2` via
   `PromptManager` (standing rule 2 — no hardcoded prompt strings).
4. Maps judge verdicts back to original candidates as `evals.scorers.ScoreResult`.

The judge model call is a plain injectable `JudgeCallable`, not an `AgentNode` subclass (this
library is offline, no `TaskContext`). Default judge model: `claude-opus-4-8`, used only when no
`judge_call` is injected.

## Cases and slices (`app/evals/slice.py`)

- `EvalCase` — `case_id`, `input`, optional `expected`/`reference`/`schema_cls`/
  `required_fields`/`value_ranges` (mirrors what `deterministic_scorer`/`reference_scorer` read).
- `EvalSlice` — a named, domain-tagged collection of `EvalCase`s bound to exactly **one** scorer,
  run against one or more models under test. Built offline; nothing here talks to a database or a
  model.

## Runner and regression history (`app/evals/runner.py`)

- `run_slice(eval_slice, session, executor)` — executes the slice against every model in
  `eval_slice.models`, aggregates pass-rate by `(domain, model)`, and persists one `EvalRun` row
  per model plus one `EvalResult` row per case via `GenericRepository`. Returns `list[EvalRun]`
  (one per model under test).
- `get_run_history(session, slice_name, model_name)` — chronological `EvalRun` history for a
  `(slice_name, model_name)` pair.
- `compare_runs(...)` — signed pass-rate delta between two runs.

`executor: Executor` is an injectable `(case, model_name) -> output` callable — nothing in this
module specifies how outputs are produced, keeping the runner offline/unit-testable.

## One-change self-improvement gate (`app/evals/gate.py`)

`gate_change(session, slice_name, model_name, baseline_run_id=None, min_delta=0.0) -> GateDecision`
— keep-if-better / revert-if-worse:

- Baseline: explicit `baseline_run_id`, else the previous run in `get_run_history` (candidate is
  the latest run).
- Rule: **keep** if `candidate.pass_rate >= baseline.pass_rate + min_delta`; otherwise **revert**.
  A tie at the default `min_delta=0.0` keeps (a no-worse change is not reverted).
- No baseline at all (first-ever run) always keeps, with a reason explaining there was nothing to
  compare against.
- Raises `ValueError` (fail loudly, no silent `None` decision) if there is no run at all for the
  slice/model, or an explicit `baseline_run_id` doesn't match any run in history.

`GateDecision` fields: `decision` (`"keep"`/`"revert"`), `baseline_run_id`, `candidate_run_id`,
`delta` (signed, `None` if no baseline), `reason`.

## Coding domain slice (`app/evals/slices/coding.py`)

The first registered domain — scores `SDLCFlowWorkflow` run telemetry rather than invoking a live
model. `load_coding_records(session)` is a thin live-query helper against the `events` table;
`build_coding_slice(records, models=...)` stays offline/pure.

A "record" mirrors the real `TaskContext` storage shape (standing rule 9):
`{"nodes": {"UpdateTaskStatusNode": {"result": SDLCState.model_dump()}, "ConsolidatedReviewNode":
{"result": {...}}}}`, falling back to `LoadTaskStateNode` for a run that bailed before any task
mutation.

Three scorers compose into `coding_scorer` (`EvalSlice` binds one scorer per slice):

| Metric | Meaning |
|---|---|
| `spec_shipped_pass_rate_scorer` | Fraction of the spec's tasks that reached `DONE` (a `MAJOR_BAIL`-mutated `FAILED` task is excluded). |
| `retry_rate_scorer` | Fraction of tasks with `attempt_count > 1`. |
| `review_pass_rate_scorer` | `1.0` if `ConsolidatedReviewNode` verdict is `PASS`, `0.0` for `FAIL`/`PARTIAL`, `None` if the run never reached review — a documented telemetry limitation (a single run record only retains the *last* task's review verdict), not an invented layout. |

`coding_scorer`'s overall `passed` follows the primary block-contract criterion (every task
`DONE`, none `FAILED`); the other two metrics are informational, surfaced in `detail` for the CLI
table.

## CLI (`scripts/run_eval.py`)

See [scripts.md](scripts.md#scripts-run_evalpy--offline-eval-cli-oru) for full usage.

```bash
python scripts/run_eval.py --slice coding [--models MODEL ...] [--dry-run]
python scripts/run_eval.py --slice coding --gate [--baseline RUN_ID] [--min-delta F]
python scripts/run_eval.py --slice coding --emit-routing PATH [--quality-floor F]
```

Design principle (D33 / local D8): this is an **offline eval harness, not a runtime router** —
`--emit-routing` only ever *produces* a routing config JSON file (per-model quality vs. cost, plus
the cheapest model meeting `--quality-floor`); nothing in `app/core/` or `app/workflows/` reads it.
Wiring routing config into runtime node config is a separate, out-of-scope block.

Adding a new domain slice: register its `(loader, builder)` pair in `_SLICE_REGISTRY` — no other
CLI wiring is needed.
