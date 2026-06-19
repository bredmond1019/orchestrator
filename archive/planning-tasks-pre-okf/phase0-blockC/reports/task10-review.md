# Review Report — phase0-blockC-task10

**Date:** 2026-06-08
**Spec:** planning/tasks/phase0-blockC/tasks.md
**Scope:** Task 10 — Write `ParallelNode` unit tests
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| All parallel nodes run — mock each to write a unique key to `task_context`; assert all keys present after `execute_nodes_in_parallel()` | MET | `TestAllNodesRun` (4 tests): `test_all_three_nodes_write_their_keys`, `test_each_node_writes_correct_value`, `test_single_parallel_node_runs`, `test_empty_parallel_nodes_list_runs_cleanly` |
| Parallel execution is actually concurrent — use threading synchronisation to verify nodes overlap | MET | `TestConcurrentExecution::test_nodes_overlap_in_time` uses `threading.Barrier(2)` — deadlocks if serial; `test_all_nodes_complete_before_execute_returns` verifies all futures awaited |
| A node that raises in a parallel context — assert the exception propagates | MET | `TestExceptionPropagates` (2 tests): exception propagates alone and when mixed with a succeeding node |
| `ParallelNode` test documents the current behavior (shared-context mutation) with a "fixed in Project E" comment | MET | `TestResultsListBehavior` (2 tests): both carry prominent `# FIXED IN PROJECT E` comments; verify results list is returned by `execute_nodes_in_parallel` but discarded by `process()` |
| `uv run pytest` passes with zero failures and zero errors | MET | Fresh run: 97 passed in 0.65s |
| `customer_care` workflow files are untouched — no new tests reference them | MET | `git diff main --name-only` shows only `tests/core/test_nodes_parallel.py` and `reports/task10-implement.md` added; no app/ changes |

## Fresh Test Results

```
============================= test session starts ==============================
platform darwin -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
rootdir: ~/agentic-portfolio
configfile: pytest.ini
testpaths: tests
plugins: mock-3.15.1, anyio-4.9.0, env-1.6.0
collected 97 items

tests/api/test_endpoint.py ..                                            [  2%]
tests/core/test_nodes_parallel.py ..........                             [ 12%]
tests/core/test_schema.py ..................                             [ 30%]
tests/core/test_task.py .......................                          [ 54%]
tests/core/test_validate.py .......................                      [ 78%]
tests/core/test_workflow.py ..................                           [ 96%]
tests/database/test_repository.py ...                                    [100%]

============================== 97 passed in 0.65s
```

Task 10 contributes 10 tests in `tests/core/test_nodes_parallel.py`. All 10 pass.

**Lint note:** `uv run ruff check app/` reports 3 pre-existing errors (UP042, UP046, B904 in `app/core/nodes/agent.py`, `app/database/repository.py`, and `app/services/prompt_loader.py`). These are pre-existing from earlier tasks; `git diff main --name-only` confirms Task 10 touched no `app/` files.

## Verdict: PASS

Task 10 fully satisfies its scope: the `tests/core/test_nodes_parallel.py` file was created with 10 tests covering all four required areas — all-nodes-run (including edge cases), concurrency proof via `threading.Barrier`, exception propagation in mixed-success scenarios, and documented known-gap behavior (shared-context mutation) with explicit `# FIXED IN PROJECT E` markers. The full pytest suite passes clean (97/97) with no regressions. No app/ source files were modified, so no new lint errors were introduced.

## Issues Found

None. All acceptance criteria are met.

## Next Steps

- Proceed to the document phase for task 10.
- Note for the block as a whole: the 3 pre-existing ruff errors (UP042 in `agent.py`, UP046 in `repository.py`, B904 in `prompt_loader.py`) were introduced by earlier tasks and should be addressed before block close-out.
