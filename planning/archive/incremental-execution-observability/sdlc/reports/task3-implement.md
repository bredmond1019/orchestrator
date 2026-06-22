# Implementation Report — incremental-execution-observability-task3

**Date:** 2026-06-20
**Plan:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 3 — Injected progress callback on `Workflow.run()` (Phase 1c)

## What Was Built or Changed
- Added `from collections.abc import Callable` to `app/core/workflow.py` imports.
- Extended `Workflow.run()` with an injected `on_progress: Callable[[TaskContext], None] | None = None`
  parameter (default `None` → no-op via an `if on_progress:` guard). Docstring documents the broad
  single-`TaskContext` signature so a future publisher (Phase 5) can be layered in without changing
  the deployment-agnostic framework.
- Before the first node, every node in `self.nodes` is seeded `PENDING` in `task_context.node_runs`
  via `setdefault`, then `on_progress` is invoked once so a freshly-dispatched run shows the full DAG
  pending.
- `on_progress(task_context)` is invoked after each node boundary (after the `node_context` block
  exits, before computing the next node). On failure the exception propagates out of `node_context`
  before this line, leaving the already-stamped FAILED envelope for the worker's terminal write.
- No DB/session code added — the framework stays deployment-agnostic (CLAUDE.md Rule 7).
- Added a `TestOnProgressCallback` suite (6 tests) to `tests/core/test_workflow.py`.

## Files Created or Modified
| File | Action |
|---|---|
| app/core/workflow.py | modified |
| tests/core/test_workflow.py | modified |

## Validation Output
**Commands run:**
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run ruff check app/
uv run pylint app/
uv run pytest --collect-only -q
uv run pytest
```
**Result:** PASSED

- ruff: All checks passed
- pylint: 10.00/10
- pytest --collect-only: 229 tests collected (up from 223 baseline; +6 new)
- pytest: 229 passed
- Signature check: `'on_progress' in inspect.signature(Workflow.run).parameters` → True
- No "bastion" string in `app/`

## Decisions and Trade-offs
- Used `setdefault` to seed PENDING so the seeding loop never clobbers a `NodeRun` that
  `node_context` might already have created (consistent with the existing `node_context` pattern).
- Added a `# pylint: disable=no-member` comment on the `node_runs.setdefault` line, matching the
  established convention in `app/core/task.py` (pylint cannot infer Pydantic field members).
- Tests use plain spy closures collecting status snapshots rather than a mock library, keeping the
  assertions hermetic and order-explicit (call count 4 = 1 seed + 3 boundaries for the 3-node linear
  workflow).

## Follow-up Work
- Task 4 (worker wires the `on_progress` closure to persist `db_event.task_context` per boundary)
  is out of scope here and remains for its own task.

## git diff --stat
```
 app/core/workflow.py        | 26 ++++++++++++-
 tests/core/test_workflow.py | 92 +++++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 117 insertions(+), 1 deletion(-)
```
