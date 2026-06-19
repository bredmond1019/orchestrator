# Implementation Report — phase0-blockC-task10

**Date:** 2026-06-08
**Plan:** planning/tasks/phase0-blockC/tasks.md
**Scope:** Task 10

## What Was Built or Changed

- Created `tests/core/test_nodes_parallel.py` with 10 unit tests covering the `ParallelNode` abstract class and its `execute_nodes_in_parallel()` method.
- Test groups:
  - `TestAllNodesRun` (4 tests): Verifies that all parallel sub-nodes execute and write their outputs into `task_context.nodes` — including single-node and empty-list edge cases.
  - `TestConcurrentExecution` (2 tests): Proves actual concurrent overlap using `threading.Barrier(2)` (deadlocks if nodes run serially); also verifies all futures are awaited before `execute_nodes_in_parallel` returns.
  - `TestExceptionPropagates` (2 tests): Confirms that a `RuntimeError` inside a parallel node propagates out of `process()`, even when other parallel nodes succeed.
  - `TestResultsListBehavior` (2 tests): Documents the known gap — `process()` discards the results list returned by `execute_nodes_in_parallel()`; parallel nodes must write to the shared `TaskContext` directly. Both tests carry explicit "FIXED IN PROJECT E" comments so the regression is caught when Project E lands.

## Files Created or Modified

| File | Action |
|---|---|
| `tests/core/test_nodes_parallel.py` | created |
| `planning/tasks/phase0-blockC/reports/task10-implement.md` | created |

## Validation Output

**Commands run:**
```
uv run pytest tests/core/test_nodes_parallel.py -v
uv run pytest --collect-only
uv run pytest -v
uv run ruff check app/
```

**Results:**
```
============================= test session starts ==============================
platform darwin -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
...
tests/core/test_nodes_parallel.py::TestAllNodesRun::test_all_three_nodes_write_their_keys PASSED
tests/core/test_nodes_parallel.py::TestAllNodesRun::test_each_node_writes_correct_value PASSED
tests/core/test_nodes_parallel.py::TestAllNodesRun::test_single_parallel_node_runs PASSED
tests/core/test_nodes_parallel.py::TestAllNodesRun::test_empty_parallel_nodes_list_runs_cleanly PASSED
tests/core/test_nodes_parallel.py::TestConcurrentExecution::test_nodes_overlap_in_time PASSED
tests/core/test_nodes_parallel.py::TestConcurrentExecution::test_all_nodes_complete_before_execute_returns PASSED
tests/core/test_nodes_parallel.py::TestExceptionPropagates::test_raising_node_propagates_runtime_error PASSED
tests/core/test_nodes_parallel.py::TestExceptionPropagates::test_exception_propagates_even_when_other_node_succeeds PASSED
tests/core/test_nodes_parallel.py::TestResultsListBehavior::test_execute_nodes_in_parallel_returns_results_list PASSED
tests/core/test_nodes_parallel.py::TestResultsListBehavior::test_shared_context_mutation_is_the_only_output_channel PASSED
10 passed in 0.12s

Full suite: 97 passed in 0.76s
```

Ruff: 3 pre-existing errors in `app/database/repository.py` and `app/services/prompt_loader.py` — none introduced by this task.

Status: PASSED

## Decisions and Trade-offs

- **`threading.Barrier(2)` for concurrency proof:** The barrier approach gives a hard guarantee — if execution is serial, the second node never reaches the barrier while the first is blocked, and `barrier.wait(timeout=5)` raises `BrokenBarrierError`. This avoids the flakiness of timing-based approaches.
- **Distinct `ParallelNode` subclasses per test group:** `execute_nodes_in_parallel` looks up the calling node's class in `task_context.metadata["nodes"]`, so each test group needs its own concrete class to avoid metadata key collisions.
- **Results-list behavior documented, not fixed:** The spec explicitly defers the shared-context mutation fix to Project E. The two `TestResultsListBehavior` tests carry prominent "FIXED IN PROJECT E" comments so the gap surfaces as a regression when E is implemented.
- **No changes to `app/`:** Task 10 is test-only. The `_SlowBarrierNode` class defined in the test file is unused by any test (the barrier nodes are built via a factory function instead) — it was left as a readable reference but all tests use the factory approach for clean subclass naming.

## Follow-up Work

- Remove the unused `_SlowBarrierNode` class from the test file (minor cleanup, no functional impact).
- Project E: fix the shared-context mutation gap — parallel nodes should return values aggregated by the orchestrator rather than writing to shared `TaskContext` directly.

## git diff --stat

```
 planning/tasks/phase0-blockC/reports/task10-implement.md | (new file)
 tests/core/test_nodes_parallel.py                        | (new file)
```
