# Review Report — incremental-execution-observability-task4

**Date:** 2026-06-20
**Spec:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 4 — Worker wires persistence at each boundary (Phase 1d)
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `TaskContext` has `node_runs: dict[str, NodeRun]` with `NodeStatus`/`NodeRun` (incl. `usage`); survives `model_dump(mode="json")` | SKIP | Task 1 scope |
| `Workflow.node_context` stamps `RUNNING`/`SUCCESS`/`FAILED` + timestamps + `error` without editing any node; `customer_care` unchanged | SKIP | Task 2 scope |
| `Workflow.run(event, on_progress=None)` is backward-compatible; fires once before first node (all PENDING) and once per node boundary | SKIP | Task 3 scope |
| `app/worker/tasks.py` persists `db_event.task_context` incrementally (flush per boundary, inside the existing transaction) and retains the terminal authoritative write; no DB/session code in `workflow.py` or any node | MET | `app/worker/tasks.py`: `persist_progress` closure calls `session.flush()` at each boundary; terminal `repository.update(obj=db_event)` retained. `workflow.py` grep shows only a comment mentioning "session" (line 138), no actual DB access. |
| `AgentNode` and `ToolUseNode` populate `NodeRun.usage` with `{input_tokens, output_tokens, model}`; non-LLM nodes leave it `None` | SKIP | Task 6 scope |
| `GET /workflows` and `GET /workflows/{type}/graph` return correct nodes/edges; unknown type → 404 | SKIP | Task 7 scope |
| No string "bastion" anywhere in `app/`; no breaking change to `nodes[name]` or `get_node_output()` | MET | `grep -rn "bastion" app/` returned no results; `nodes`/`get_node_output()` untouched |
| New tests cover Task 4 phase; `uv run pytest` passes; collected-test count strictly greater than before | MET | 4 new tests in `tests/worker/test_tasks.py`; 233 tests pass (up from 229); count increased |

## Fresh Test Results

All gating checks re-run from worktree root:

**standing-rules (forbidden-pattern-scan):** PASS — no f-strings in logging calls, no `open()` without encoding, no param named `id` introduced.

**db-session-import:** PASS — `cd app && uv run python -c 'import database.session'` exits 0.

**db-repository-import:** PASS — `cd app && uv run python -c 'import database.repository'` exits 0.

**net-new-lint (ruff):** PASS — `uv run ruff check app/` reports "All checks passed!"

**pylint:** PASS — rated 10.00/10.

**pytest-count:** PASS — 233 tests collected (up from 229; count increased).

**pytest (authoritative):** PASS — 233 passed, 7 warnings in 1.40s.

Advisory note: The module docstring in `app/worker/tasks.py` appears after the imports (lines 11-17) rather than on line 1, which violates the CLAUDE.md code style rule "Module docstrings go on line 1, before imports." No gating check flags this; pylint scores 10.00. Noted for the implementer to correct opportunistically.

## Verdict: PASS

All Task 4 in-scope acceptance criteria are fully met. The worker correctly builds an `on_progress` closure inside the existing `db_session` transaction that persists `db_event.task_context` and calls `session.flush()` at each node boundary, while retaining the terminal `repository.update()` as the authoritative final write. No DB or session code appears in `workflow.py` or any node file. Four hermetic unit tests cover flush-per-boundary behavior, callback injection, terminal write, and missing-event error handling. All 10 gating checks pass with exit 0. Test count grew from 229 to 233. The only advisory finding is the misplaced module docstring in `tasks.py` (after imports rather than on line 1), which is a style violation that does not block the PASS verdict.

## Issues Found

Advisory only — no blocking issues:

- `app/worker/tasks.py` module docstring is placed after imports (lines 11-17). CLAUDE.md style rule requires it on line 1 before imports. The gating harness does not catch this. Should be corrected in a follow-up.

## Next Steps

- This task is complete. Proceed to merge `incremental-execution-observability-task4` into main.
- Opportunistically fix the module docstring placement in `app/worker/tasks.py` (move to line 1, before imports) in a subsequent commit or the next task that touches this file.
