# Review Report — incremental-execution-observability-task2

**Date:** 2026-06-20
**Spec:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 2 (Step 2 — Framework stamps the envelope in `node_context`)
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `TaskContext` has `node_runs: dict[str, NodeRun]` with `NodeStatus`/`NodeRun` (incl. `usage`); survives `model_dump(mode="json")` | MET | `app/core/task.py`: `NodeStatus(StrEnum)`, `NodeRun(BaseModel)` with `usage: dict \| None`, `node_runs: dict[str, NodeRun]` on `TaskContext`; test `test_envelope_survives_json_dump` confirms JSON round-trip |
| `Workflow.node_context` stamps `RUNNING`/`SUCCESS`/`FAILED` + timestamps + `error` without any node being edited; `customer_care` and its nodes are unchanged | MET | `app/core/workflow.py:55-93`: `node_context(node_name, task_context)` stamps RUNNING+`started_at` on entry, SUCCESS+`completed_at` in `else`, FAILED+`error`+`completed_at` in `except`; no customer_care file in the commit diff; `TestNodeContextEnvelope` tests cover all three transitions |
| `Workflow.run(event, on_progress=None)` backward-compatible; callback fires once before first node and once per boundary | SKIP | Step 3 — explicitly deferred to Task 3 per implement report; `run()` does not yet have `on_progress` parameter |
| `app/worker/tasks.py` persists `db_event.task_context` incrementally (flush per boundary) | SKIP | Step 4 — future task scope |
| `AgentNode` and `ToolUseNode` populate `NodeRun.usage` with `{input_tokens, output_tokens, model}` | SKIP | Step 6 — future task scope |
| `GET /workflows` and `GET /workflows/{type}/graph` return correct nodes/edges; unknown type → 404 | SKIP | Step 7 — future task scope |
| No string "bastion" in `app/`; no breaking change to `nodes[name]` or `get_node_output()` | MET | `grep -rni "bastion" app/` exits 1 (no matches); `get_node_output()` signature and behavior unchanged (`app/core/task.py:79`) |
| New tests cover every phase built; `uv run pytest` passes; collected-test count strictly greater than before | MET | 216 tests collected (up from 213 pre-task per worktree history); 216 passed; `TestNodeContextEnvelope` adds 3 targeted tests |

## Fresh Test Results

| Check | Result |
|---|---|
| db-session-import | PASS (exit 0) |
| db-repository-import | PASS (exit 0) |
| net-new-lint (ruff) | PASS (exit 0, [] output) |
| pylint | PASS (10.00/10) |
| pytest-count | PASS (216 collected) |
| pytest | PASS (216 passed, 7 warnings) |
| standing-rules: f-string-in-logging | PASS (no matches) |
| standing-rules: no bastion ref | PASS (grep exit 1) |

All gating checks passed with exit 0. No failures.

## Verdict: PASS

Task 2 delivers exactly what step 2 of the spec requires: `Workflow.node_context` now receives the live `TaskContext` and stamps per-node `NodeRun` envelopes (RUNNING/SUCCESS/FAILED + ISO-8601 timestamps + error string) entirely within the framework, with no edits to any node or the `customer_care` workflow. The `on_progress` callback (step 3), worker persistence wiring (step 4), token capture (step 6), and the graph endpoint (step 7) are explicitly out of scope for this task. All gating checks pass, pylint is 10.00/10, ruff is clean, and 216 tests pass including three new tests in `TestNodeContextEnvelope` that cover the SUCCESS, FAILED, and JSON-round-trip scenarios. The implementation is fully compliant with CLAUDE.md standing rules (no f-strings in logging, no `id` parameter, no bastion references, no DB code in workflow.py).

## Issues Found

None.

## Next Steps

Task 2 is complete. Proceed to Task 3 (injected `on_progress` callback on `Workflow.run()`) which wires the callback interface so the worker (Task 4) can flush persistence at each node boundary.
