# Implementation Report — incremental-execution-observability-task2

**Date:** 2026-06-20
**Plan:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 2

## What Was Built or Changed
- Extended `Workflow.node_context` (`app/core/workflow.py`) to receive the live `TaskContext` and stamp the per-node `NodeRun` envelope: `RUNNING` + `started_at` on entry, `SUCCESS` + `completed_at` on clean exit (`else` branch), `FAILED` + `error` + `completed_at` in the `except` branch before re-raising.
- Added stdlib imports `from datetime import UTC, datetime` and broadened `from core.task import NodeRun, NodeStatus, TaskContext`.
- Updated the `node_context` call site inside `run()` to pass `task_context`.
- No node was edited; `customer_care` and its nodes remain frozen. No DB/session code added to `workflow.py`.
- Added focused tests in `tests/core/test_workflow.py` (`TestNodeContextEnvelope`) covering SUCCESS-with-timestamps, the FAILED envelope observable before re-raise, and JSON round-trip of `node_runs`.

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
uv run pytest --collect-only -q   (216 collected)
uv run pytest                     (216 passed)
grep -rni "bastion" app/          (no matches, exit 1)
```
**Result:** PASSED

## Decisions and Trade-offs
- Tests for the node_context envelope were added to the existing `tests/core/test_workflow.py` (the file that already tests `node_context`) rather than creating `tests/core/test_observability.py`, which is the deliverable owned by Task 5 of this spec. This keeps Task 2 shipping with its own validation (CLAUDE.md Rule 1) without colliding with a parallel task's file on merge.
- The `tests/` directory was excluded by the worktree's sparse-checkout (configured for a Next.js layout); added it via `git sparse-checkout add tests` so the project's pytest suite is present and runnable.
- `SUCCESS` is set in the `else` branch (not `finally`) so it is only stamped on a clean exit; `FAILED` is stamped in `except` before `raise`, preserving exception propagation.

## Follow-up Work
- The `on_progress` callback on `run()` (Task 3), worker persistence wiring (Task 4), token/usage capture (Task 6), and the graph endpoint (Task 7) are out of scope for Task 2.

## git diff --stat
```
 app/core/workflow.py        | 26 +++++++++++++++++++++----
 tests/core/test_workflow.py | 47 ++++++++++++++++++++++++++++++++++++++++++++-
 2 files changed, 68 insertions(+), 5 deletions(-)
```
