# Review Report — incremental-execution-observability-task8

**Date:** 2026-06-20
**Spec:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 8
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `TaskContext` has `node_runs: dict[str, NodeRun]` with `NodeStatus`/`NodeRun` (incl. `usage`); survives `model_dump(mode="json")` | MET | `app/core/task.py:14,21,33,71` — `NodeStatus(StrEnum)`, `NodeRun(BaseModel)` with `usage` field, `node_runs: dict[str, NodeRun]` on `TaskContext` |
| `Workflow.node_context` stamps `RUNNING`/`SUCCESS`/`FAILED` + timestamps + `error` without editing any node; `customer_care` and its nodes unchanged | MET | `app/core/workflow.py:58–91` — context manager stamps status; no `customer_care` node edits (verified by zero source changes in Task 8) |
| `Workflow.run(event, on_progress=None)` backward-compatible; callback fires once before first node (all `PENDING`) and once per node boundary | MET | `app/core/workflow.py:126–169` — `on_progress` param defaults `None`; seeded PENDING then invoked after each boundary |
| `app/worker/tasks.py` persists `db_event.task_context` incrementally (flush per boundary); retains terminal authoritative write; no DB/session code in `workflow.py` or any node | MET | `app/worker/tasks.py:46–55` — `persist_progress` closure flushes at each boundary; terminal `result_context` write follows; no session in workflow/nodes |
| `AgentNode` and `ToolUseNode` populate `NodeRun.usage` with `{input_tokens, output_tokens, model}`; non-LLM nodes leave it `None` | MET | `app/core/nodes/agent.py:81–88`, `app/core/nodes/tool_use.py:66–102` — both nodes capture usage into `run.usage`; other nodes do not set the field |
| `GET /workflows` and `GET /workflows/{type}/graph` return correct nodes/edges for `customer_care`; unknown type → 404 | MET | `app/api/graph.py:12–23` — both endpoints present; `HTTPException(status_code=404)` for unknown type; wired via `app/api/router.py:5,10` |
| No string "bastion" anywhere in `app/`; no breaking change to `nodes[name]` or `get_node_output()` | MET | `grep -rn "bastion" app/` — no results; `node_runs` is additive; existing `nodes` dict and `get_node_output()` untouched |
| New tests cover every phase; `uv run pytest` passes; collected-test count strictly greater than before | MET | 238 tests collected and all pass (238 passed, 7 warnings in 1.41s) |

## Fresh Test Results

**standing-rules (GATING):** PASS — no f-strings in logging calls, no `open()` without encoding violations, no params named `id` found in new code; no bastion refs.

**db-session-import (GATING):** PASS — `import database.session` exits clean.

**db-repository-import (GATING):** PASS — `import database.repository` exits clean.

**net-new-lint / ruff (GATING):** PASS — `uv run ruff check app/ --output-format=json` returns `[]` (no violations).

**pylint (GATING):** PASS — rated 10.00/10 (previous run: 10.00/10, +0.00).

**pytest-count (GATING):** PASS — 238 tests collected (no decrease).

**pytest (GATING):** PASS — 238 passed, 7 warnings in 1.41s.

## Verdict: PASS

All seven gating checks pass with zero failures. All eight acceptance criteria are met by the implementation from Tasks 1–7, which Task 8 validates. The `TaskContext`/`NodeRun` observability envelope, the `Workflow.node_context` stamping, the `on_progress` callback, incremental persistence in the worker, per-node token capture in `AgentNode`/`ToolUseNode`, and the graph introspection endpoints are all present and covered by the test suite. No bastion references exist in `app/`, no standing rules were violated, and pylint scores a perfect 10.00/10.

## Issues Found

None.

## Next Steps

The spec is complete. All phases (1a–1d, 2, 3) are implemented and validated. Phase 4 (promoted indexed `status` column) and Phase 5 (push/SSE) remain deferred per spec scope decision.
