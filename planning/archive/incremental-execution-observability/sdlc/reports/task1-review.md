# Review Report — incremental-execution-observability-task1

**Date:** 2026-06-20
**Spec:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 1 — Status/timing envelope on `TaskContext` (Phase 1a)
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `TaskContext` has `node_runs: dict[str, NodeRun]` with `NodeStatus`/`NodeRun` (incl. `usage`); survives `model_dump(mode="json")` | MET | `app/core/task.py`: `NodeStatus(StrEnum)` with 4 values; `NodeRun(BaseModel)` with `status`, `started_at`, `completed_at`, `error`, `usage` fields; `node_runs: dict[str, NodeRun] = Field(default_factory=dict)` on `TaskContext`; verified `model_dump(mode="json")` serializes enum to string "success" |
| `Workflow.node_context` stamps `RUNNING`/`SUCCESS`/`FAILED` + timestamps + `error`; `customer_care` unchanged | SKIP | Task 2 scope — `workflow.py` not in Task 1 step list |
| `Workflow.run(event, on_progress=None)` backward-compatible; callback fires before first node and per boundary | SKIP | Task 3 scope |
| `app/worker/tasks.py` persists incrementally; no DB/session in `workflow.py` or nodes | SKIP | Task 4 scope |
| `AgentNode` and `ToolUseNode` populate `NodeRun.usage`; non-LLM nodes leave it `None` | SKIP | Task 6 scope |
| `GET /workflows` and `GET /workflows/{type}/graph` correct for `customer_care`; unknown → 404 | SKIP | Task 7 scope |
| No "bastion" in `app/`; no breaking change to `nodes[name]` or `get_node_output()` | MET | `grep -r "bastion" app/` empty; `get_node_output()` and `update_node()` signatures unchanged; verified programmatically |
| New tests cover every phase; pytest passes; collected-test count strictly greater than before | SKIP | Tests for Phase 1 explicitly scoped to Task 5; current suite (210 tests) passes; test count delta evaluated at Task 5 |

## Fresh Test Results

**standing-rules (GATING):** PASS — no f-strings in logging calls, no `open()` without encoding, no param named `id` in `task.py`

**db-session-import (GATING):** PASS — `cd app && uv run python -c 'import database.session'` exits 0

**db-repository-import (GATING):** PASS — `cd app && uv run python -c 'import database.repository'` exits 0

**net-new-lint / ruff (GATING):** PASS — `uv run ruff check app/` → "All checks passed!"

**pylint (GATING):** PASS — rated 10.00/10

**pytest-count (GATING):** PASS — 210 tests collected (no decrease)

**pytest (GATING):** PASS — 210 passed, 7 warnings in 1.40s

## Verdict: PASS

Task 1 delivered exactly what its spec step requires: `NodeStatus(StrEnum)`, `NodeRun(BaseModel)` (including the `usage` slot for Phase 2), and `node_runs: dict[str, NodeRun]` on `TaskContext`, all in `app/core/task.py`. The `model_dump(mode="json")` round-trip serializes enum values to strings correctly. The parallel/additive design leaves `nodes`, `update_node()`, and `get_node_output()` fully intact. No "bastion" reference was introduced. All 7 gating checks pass (ruff clean, pylint 10.00/10, 210 tests pass). The five acceptance criteria that span later tasks (Tasks 2–7) are correctly skipped for this review scope.

## Issues Found

None.

## Next Steps

Proceed to Task 2 (framework stamps the envelope in `node_context`) in the normal pipeline sequence.
