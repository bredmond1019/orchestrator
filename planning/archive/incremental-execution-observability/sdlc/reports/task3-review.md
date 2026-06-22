# Review Report — incremental-execution-observability-task3

**Date:** 2026-06-20
**Spec:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 3 — Injected progress callback on `Workflow.run()` (Phase 1c)
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `TaskContext` has `node_runs: dict[str, NodeRun]` with `NodeStatus`/`NodeRun` (incl. `usage`); survives `model_dump(mode="json")` | SKIP | Belongs to Tasks 1 and 6 (Phase 1a + Phase 2) — not Task 3's scope |
| `Workflow.node_context` stamps `RUNNING`/`SUCCESS`/`FAILED` + timestamps + `error` without any node being edited; `customer_care` unchanged | SKIP | Task 2's scope (Phase 1b) |
| `Workflow.run(event, on_progress=None)` is backward-compatible; with a callback it fires once before the first node (all `PENDING`) and once per node boundary | MET | `app/core/workflow.py:126` — signature present; lines 156–159 seed all nodes PENDING and emit initial snapshot; lines 168–169 emit post-boundary snapshot; `TestOnProgressCallback` (6 tests) validates seeding, call count, mid-run snapshot, terminal state, backward compat, and single-arg contract |
| `app/worker/tasks.py` persists `db_event.task_context` incrementally (flush per boundary) and retains terminal authoritative write; no DB/session code in `workflow.py` or any node | SKIP | Task 4's scope (Phase 1d) |
| `AgentNode` and `ToolUseNode` populate `NodeRun.usage`; non-LLM nodes leave it `None` | SKIP | Task 6's scope (Phase 2) |
| `GET /workflows` and `GET /workflows/{type}/graph` return correct nodes/edges; unknown type → 404 | SKIP | Task 7's scope (Phase 3) |
| No string "bastion" anywhere in `app/`; no breaking change to `nodes[name]` or `get_node_output()` | MET | `grep -rn "bastion" app/` → 0 hits; `get_node_output()` untouched; `nodes` dict untouched |
| New tests cover every phase above; `uv run pytest` passes; collected-test count strictly greater than before | MET (Task 3 scope) | 6 new tests in `TestOnProgressCallback`; pytest: 229 passed (increased); pylint: 10.00/10 |

## Fresh Test Results

All gating checks re-run from worktree root:

**standing-rules (forbidden-pattern-scan):** PASS
- No f-strings in logging calls in `app/` (grep found 0 violations)
- No bastion references in `app/` (0 hits)
- No parameter named `id` in new code

**db-session-import:** PASS
```
cd app && uv run python -c 'import database.session'  → exit 0
```

**db-repository-import:** PASS
```
cd app && uv run python -c 'import database.repository'  → exit 0
```

**net-new-lint (ruff):** PASS
```
uv run ruff check app/ → "All checks passed!"
```

**pylint:** PASS
```
uv run pylint app/ → "Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)"
```

**pytest-count:** PASS
```
uv run pytest --collect-only -q → 229 tests collected
```
(229 tests collected, strictly greater than pre-task baseline)

**pytest (authoritative):** PASS
```
uv run pytest → 229 passed, 7 warnings in 1.38s
```

## Verdict: PASS

All gating checks pass and the one in-scope acceptance criterion is fully met. `Workflow.run()` accepts `on_progress: Callable[[TaskContext], None] | None = None`, seeds every node `PENDING` before the first node, fires the callback once with the initial snapshot, and fires once per node boundary after `node_context` exits (success or failure). No persistence or session code was introduced in `workflow.py`. Six targeted tests in `TestOnProgressCallback` cover: initial PENDING seeding, N+1 call count, mid-run partial snapshot (the observability guarantee), terminal all-SUCCESS snapshot, backward compatibility (default `None`), and single-`TaskContext`-arg contract. The no-bastion and no-breaking-change guards hold. Pylint remains 10.00/10 and ruff is clean.

## Issues Found

None.

## Next Steps

Proceed to Task 4 — wire persistence in `app/worker/tasks.py` (Phase 1d): build an `on_progress` closure inside the existing `db_session` transaction that flushes `db_event.task_context` at each boundary, then pass it to `workflow.run(db_event.data, on_progress=...)`.
