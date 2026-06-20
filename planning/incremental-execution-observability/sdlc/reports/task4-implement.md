# Implementation Report — incremental-execution-observability-task4

**Date:** 2026-06-20
**Plan:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 4 — Worker wires persistence at each boundary (Phase 1d)

## What Was Built or Changed
- `app/worker/tasks.py`: replaced the single terminal `model_dump` write with an injected
  `persist_progress(task_context)` closure passed as `on_progress` to `workflow.run(...)`.
  The closure assigns `db_event.task_context = task_context.model_dump(mode="json")` and calls
  `session.flush()` at each node boundary — inside the existing `db_session` transaction (the
  context manager still owns commit/rollback). The terminal `repository.update(obj=db_event)`
  remains the final authoritative write.
- Added `from core.task import TaskContext` for the closure type hint (sorted under the `core`
  import group, before `database`).
- `tests/worker/test_tasks.py` (new): unit coverage for the worker wiring — flush-per-boundary,
  callable `on_progress` injection, terminal authoritative write, and missing-event guard. Mocks
  `db_session`, `GenericRepository`, and `WorkflowRegistry` so the test is hermetic (no DB/Celery).

## Files Created or Modified
| File | Action |
|---|---|
| app/worker/tasks.py | modified |
| tests/worker/__init__.py | created |
| tests/worker/test_tasks.py | created |

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

ruff: All checks passed. pylint: 10.00/10. pytest: 233 passed (collection up from 229).
No "bastion" reference in `app/`.

## Decisions and Trade-offs
- The brain stays deployment-agnostic: persistence lives entirely in the worker closure. No
  DB/session code was added to `workflow.py` or any node (Rule 7 preserved).
- `flush()` (not `commit()`) per boundary keeps the incremental writes inside the open
  transaction; the `db_session` context manager remains the single owner of commit/rollback.
- The framework-level `on_progress` invocation contract is already covered by
  `tests/core/test_workflow.py`; the new `tests/worker/test_tasks.py` covers the worker-specific
  persistence path that no other test exercised, satisfying the "every change ships with tests" rule.
- The `tests/` tree was absent from the worktree's sparse checkout; added it via
  `git sparse-checkout add tests` so the validation suite (testpaths = tests) runs.

## Follow-up Work
- None for Task 4. Phase 2 (usage capture), Phase 3 (graph endpoint), and the broader Phase 1
  framework tests are owned by other tasks in this spec.

## git diff --stat
```
 app/worker/tasks.py | 15 +++++++++++----
 1 file changed, 11 insertions(+), 4 deletions(-)
```
(plus new untracked test files: tests/worker/__init__.py, tests/worker/test_tasks.py)
