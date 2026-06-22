# Implementation Report — incremental-execution-observability-task5

**Date:** 2026-06-20
**Plan:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 5

## What Was Built or Changed
- Added `tests/core/test_observability.py` — the Phase 1 observability test suite (5 tests):
  - `test_node_runs_reach_success` — happy-path PENDING -> RUNNING -> SUCCESS with timestamps.
  - `test_failed_node_records_error_and_propagates` — FAILED envelope (status/error/completed_at) observable via the live seeded context while the exception still propagates.
  - `test_on_progress_called_once_before_first_node_and_per_boundary` — spy asserts 3 snapshots (1 seed + 2 boundaries), first all PENDING, last all SUCCESS.
  - `test_default_on_progress_none_is_noop` — backward compatibility: terminal cleanup + node-output contract intact.
  - `test_mid_run_snapshot_is_partial` — the observability guarantee: a mid-run `model_dump(mode="json")` shows StepNodeA `success` while StepNodeB is still `pending`.
- Fixed a load-bearing production defect surfaced by the mid-run snapshot test (see Decisions): `app/core/task.py` now strips the transient runtime `metadata["nodes"]` registry from serialized output via a `field_serializer`, so `TaskContext.model_dump(mode="json")` is safe at any point during a run.

## Files Created or Modified
| File | Action |
|---|---|
| tests/core/test_observability.py | created |
| app/core/task.py | modified |

## Validation Output
**Commands run:**
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run ruff check app/
uv run pylint app/
uv run pytest --collect-only -q   (233 baseline -> 238 collected)
uv run pytest                     (238 passed)
```
**Result:** PASSED

## Decisions and Trade-offs
- **Sparse checkout:** the worktree was provisioned with a generic (Next.js-shaped) sparse-checkout profile that omitted `tests/`. Ran `git sparse-checkout add tests app/worker` so the existing suite and worker source were materialized; no tracked content changed.
- **Real defect fix in `task.py` (cross-task but load-bearing):** the mid-run snapshot test (a required Task 5 acceptance criterion) initially failed with `PydanticSerializationError: Unable to serialize unknown type: <class 'abc.ABCMeta'>`. Root cause: `Workflow.run` stashes the node-class registry under `metadata["nodes"]` for `ParallelNode` to read at runtime, then pops it on completion. The Phase 1d worker (`worker/tasks.py::persist_progress`) calls `model_dump(mode="json")` at every node boundary — i.e. while that registry is populated — so any real workflow would crash the worker at its first boundary. Task 4's worker test mocked `workflow.run`, so it never exercised the real `metadata["nodes"]` path and the bug went undetected. The minimal, principled fix is a `field_serializer("metadata")` on `TaskContext` that drops the transient `nodes` key from dumps only; `ParallelNode`'s runtime access (`task_context.metadata["nodes"][self.__class__]`) is unchanged, and the "TaskContext survives `model_dump(mode="json")`" invariant (Phase 1a) now holds mid-run. This keeps the test faithful to the acceptance criteria (plain `model_dump(mode="json")`) instead of papering over the crash by excluding fields in the test.
- Followed the breakdown's stub-node/stub-workflow pattern (mirrors `tests/core/test_workflow.py`); used `customer_care`-free fixtures per Rule 3.

## Follow-up Work
- None required for Task 5. Note for reviewers: the `task.py` serializer fix also hardens the Task 4 worker path; the existing worker test still passes but does not cover the real (un-mocked) registry path — a future integration test running a real workflow through `persist_progress` would close that gap.

## git diff --stat
```
 app/core/task.py | 18 +++++++++++++++++-
 1 file changed, 17 insertions(+), 1 deletion(-)
```
(plus new untracked file `tests/core/test_observability.py`)
