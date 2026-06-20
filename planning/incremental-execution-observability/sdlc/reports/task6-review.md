# Review Report — incremental-execution-observability-task6

**Date:** 2026-06-20
**Spec:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 6
**Verdict:** PASS

## Acceptance Criteria Check

Task 6 is scoped to "Per-node token + cost capture (Phase 2)". The full Acceptance Criteria section spans all tasks, so criteria that belong to other tasks are marked SKIP.

| Criterion | Status | Evidence |
|---|---|---|
| `TaskContext` has `node_runs: dict[str, NodeRun]` with `NodeStatus`/`NodeRun` (incl. `usage`); survives `model_dump(mode="json")` | MET | `app/core/task.py:37` — `NodeRun.usage: dict \| None = None`; field added in earlier tasks, `usage` field added here |
| `AgentNode` and `ToolUseNode` populate `NodeRun.usage` with `{input_tokens, output_tokens, model}`; non-LLM nodes leave it `None` | MET | `agent.py:65-91` `run_agent_recorded`; `tool_use.py:100-106`; `PlainNode` test at `tests/core/test_nodes_usage.py:195` confirms `None` |
| New tests cover Phase 2; `uv run pytest` passes; collected-test count strictly greater than before | MET | 220 tests collected and all pass; `tests/core/test_nodes_usage.py` adds 7 tests covering ToolUseNode usage, AgentNode usage (both token-name variants), return-value passthrough, and non-LLM node |
| `Workflow.node_context` stamps RUNNING/SUCCESS/FAILED + timestamps without editing nodes; `customer_care` unchanged | SKIP (Task 2 scope — no edits to customer_care confirmed via git log) |
| `Workflow.run(event, on_progress=None)` backward-compatible; callback fires pre-first-node and per boundary | SKIP (Task 3 scope) |
| `app/worker/tasks.py` incremental flush per boundary; no DB/session in `workflow.py` or nodes | SKIP (Task 4 scope) |
| `GET /workflows` and `GET /workflows/{type}/graph` return correct nodes/edges; unknown type → 404 | SKIP (Task 7 scope) |
| No string "bastion" anywhere in `app/`; no breaking change to `nodes[name]` or `get_node_output()` | MET | `grep -rn "bastion" app/` returned no results; `get_node_output()` untouched |
| CLAUDE.md standing rules: no f-strings in logging, `encoding=` on `open()`, no param named `id`, module docstring line 1, `X \| None` typing | MET | ruff clean (zero violations); pylint 10.00/10; `tool_use.py` has module docstring on line 1; `agent.py` uses `str \| None`-style typing |

## Fresh Test Results

**db-session-import** (gating): PASS
```
cd app && uv run python -c 'import database.session'  — exit 0
```

**db-repository-import** (gating): PASS
```
cd app && uv run python -c 'import database.repository'  — exit 0
```

**net-new-lint / ruff** (gating): PASS
```
uv run ruff check app/ --output-format=json  — []  (zero violations)
```

**pylint** (gating): PASS
```
Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)
```

**pytest-count** (gating): PASS
```
220 tests collected in 1.14s
```

**pytest** (gating, authoritative): PASS
```
220 passed, 7 warnings in 1.45s
```

## Verdict: PASS

All Task 6 acceptance criteria are fully met. `AgentNode` exposes `run_agent_recorded()` which stamps `{input_tokens, output_tokens, model}` on `NodeRun.usage` using a `getattr` fallback that handles both the current and older pydantic-ai token-name variants. `ToolUseNode.process()` accumulates tokens across loop iterations and writes the same usage shape at the end. Non-LLM nodes leave `usage` as `None`. The new `tests/core/test_nodes_usage.py` file adds comprehensive coverage for all three cases. All six gating checks pass with exit 0. No CLAUDE.md standing-rule violations were found.

## Issues Found

None.

## Next Steps

Task 6 is complete. Proceed to Task 7 (Workflow graph introspection endpoint — Phase 3).
