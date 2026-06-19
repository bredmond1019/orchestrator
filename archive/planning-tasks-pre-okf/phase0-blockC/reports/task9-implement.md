# Implementation Report — phase0-blockC-task9

**Date:** 2026-06-08
**Plan:** planning/tasks/phase0-blockC/tasks.md
**Scope:** Task 9

## What Was Built or Changed

- Created `tests/core/test_nodes_router.py` — 23 unit tests covering `BaseRouter` and `RouterNode` in `app/core/nodes/router.py`.
- Tests are organized into six test classes covering all required scenarios from the spec:
  - `TestBaseRouterProcess` — verifies `process()` writes `{"next_node": <name>}` under the router's class name in `task_context.nodes` and returns the same context object.
  - `TestBaseRouterRouteFirstMatchWins` — verifies route evaluation is ordered and the first matching route's node is returned even when multiple routes could match.
  - `TestBaseRouterRouteFallback` — verifies the fallback node is returned when no route matches, and that the fallback is not used when a route does match.
  - `TestBaseRouterRouteNoFallbackNoMatch` — verifies `route()` returns `None` when `routes` is empty or all routes return `None` and `fallback` is `None`.
  - `TestBaseRouterRouteSkipsNoneReturn` — verifies `route()` skips `RouterNode`s that return `None` and continues evaluating subsequent routes.
  - `TestBaseRouterRouteKeyErrorPropagates` — verifies `KeyError` raised by `get_node_output()` inside a `RouterNode.determine_next_node()` propagates out of `route()` unswallowed, with the descriptive message naming the missing node, listing available nodes, and referencing WorkflowSchema.

## Files Created or Modified

| File | Action |
|---|---|
| `tests/core/test_nodes_router.py` | created |
| `planning/tasks/phase0-blockC/reports/task9-implement.md` | created |

## Validation Output

**Commands run:**
```
uv run pytest tests/core/test_nodes_router.py -v
uv run pytest -v
uv run ruff check app/
```

**Results:**
```
# Router tests only
============================= 23 passed in 0.05s ==============================

# Full suite
============================== 110 passed in 0.60s ==============================

# Ruff (pre-existing errors, not introduced by Task 9)
app/core/nodes/agent.py:29 — UP042 (pre-existing)
app/database/repository.py:16 — UP046 (pre-existing)
app/services/prompt_loader.py:82 — B904 (pre-existing)
Found 3 errors (all pre-existing, zero introduced by this task)
```

Status: PASSED

## Decisions and Trade-offs

- Stub `Node` subclasses (`StubNodeAlpha`, `StubNodeBeta`, `StubNodeGamma`) and stub `RouterNode`/`BaseRouter` subclasses are defined at the module level rather than inside individual tests. This keeps test bodies readable and avoids repeated inline class definitions.
- `process()` is only tested with successful routing (a router that always finds a match), because `process()` calls `next_node.node_name` unconditionally — calling it with a `None`-returning router would raise `AttributeError`, not a meaningful test failure. The `route()` returning `None` behavior is tested separately on `route()` directly.
- The `KeyError` propagation tests verify both that the error is not swallowed and that the descriptive message (node name, available nodes list, WorkflowSchema hint) is present — this exercises the `get_node_output()` fix from Task 5 through the router path.
- No changes were made to `app/` source files — Task 9 is tests-only.

## Follow-up Work

- The `customer_care` workflow uses direct `task_context.nodes["NodeName"]` key access in its router nodes. Per CLAUDE.md rule 3, those files are frozen and must not be changed. New router nodes (Project A onwards) should use `task_context.get_node_output()`.
- Pre-existing ruff errors in `app/core/nodes/agent.py` (UP042), `app/database/repository.py` (UP046), and `app/services/prompt_loader.py` (B904) are deferred — they are not touched by this task and are tracked in the known-bugs table.

## git diff --stat

```
(only untracked file — tests/core/test_nodes_router.py is new, not yet committed)
```
