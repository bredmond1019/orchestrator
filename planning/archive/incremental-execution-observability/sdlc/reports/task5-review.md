# Review Report — incremental-execution-observability-task5

**Date:** 2026-06-20
**Spec:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 5
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `TaskContext` has `node_runs: dict[str, NodeRun]` with `NodeStatus`/`NodeRun`; survives `model_dump(mode="json")` (usage field is Task 6 scope) | MET | `app/core/task.py:71-74`; `TestMidRunSnapshot` in `tests/core/test_observability.py` confirms JSON round-trip |
| `Workflow.node_context` stamps `RUNNING`/`SUCCESS`/`FAILED` + timestamps + `error` without any node being edited; `customer_care` frozen | MET | `TestHappyPathTransitions` asserts SUCCESS + timestamps; `TestFailureEnvelope` asserts FAILED + error + completed_at |
| `Workflow.run(event, on_progress=None)` backward-compatible; callback fires once before first node (all PENDING) and once per boundary | MET | `TestOnProgressSpy`: 3 calls for 2-node workflow (1 seed + 2 boundaries); `TestBackwardCompatibility` confirms no-callback path |
| `app/worker/tasks.py` persists incrementally at each boundary | SKIP | Task 4 scope — not Task 5 |
| `AgentNode` and `ToolUseNode` populate `NodeRun.usage` | SKIP | Task 6 scope — not Task 5 |
| `GET /workflows` and `GET /workflows/{type}/graph` return correct data | SKIP | Task 7 scope — not Task 5 |
| No "bastion" in `app/`; no breaking change to `nodes[name]` or `get_node_output()` | MET | `grep -rn "bastion" app/` returned empty; `get_node_output()` at `task.py:95-120` is untouched |
| New tests cover Phase 1; `uv run pytest` passes; collected count strictly greater than before | MET | 238 collected (+5 vs 233); 238 passed |
| CLAUDE.md standing rules: module docstring line 1, modern typing, no param named `id`, encoding, raise from e, no f-strings in logging | MET | ruff PASS; pylint 10.00/10; all standing-rule pattern scans returned empty |
| Real defect fixed: mid-run `model_dump(mode="json")` crash from non-serializable `metadata["nodes"]` class-keyed dict | MET | `_serialize_metadata` field_serializer at `task.py:76-90` strips transient key; `TestMidRunSnapshot` directly exercises this path |

## Fresh Test Results

**standing-rules (GATING):** PASS — all three pattern scans (f-string-in-logging, open-without-encoding, param-named-id) returned empty.

**db-session-import (GATING):** PASS — `cd app && uv run python -c 'import database.session'` exited 0.

**db-repository-import (GATING):** PASS — `cd app && uv run python -c 'import database.repository'` exited 0.

**net-new-lint / ruff (GATING):** PASS — `uv run ruff check app/` reports "All checks passed!"

**pylint (GATING):** PASS — `Your code has been rated at 10.00/10`

**pytest-count (GATING):** PASS — `238 tests collected` (implementer reports +5 from 233 baseline).

**pytest (GATING):** PASS — `238 passed, 7 warnings in 1.39s`

## Verdict: PASS

All seven gating checks pass with fresh execution. Task 5 delivers five new Phase 1 observability tests covering the full acceptance surface: happy-path PENDING → SUCCESS transitions, FAILED envelope with error and exception propagation, `on_progress` call-count/order spy (3 calls for 2-node workflow), backward-compatibility with no callback, and the observability guarantee via mid-run `model_dump(mode="json")` partial snapshot. The implementer also identified and fixed a real defect — a mid-run JSON serialization crash caused by non-serializable class objects stored in `metadata["nodes"]` — which is covered directly by the new `TestMidRunSnapshot` test. All CLAUDE.md standing rules are satisfied; no bastion references; `customer_care` is frozen and untouched.

## Issues Found

None.

## Next Steps

Task 5 is complete. Proceed to Task 6 (per-node token + cost capture in `AgentNode` and `ToolUseNode`, with `NodeRun.usage` population) and Task 7 (workflow graph introspection endpoints).
