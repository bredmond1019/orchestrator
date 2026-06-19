# Implementation Report — phase0-blockC-task8

**Date:** 2026-06-08
**Plan:** planning/tasks/phase0-blockC/tasks.md
**Scope:** Task 8

## What Was Built or Changed
- Created `tests/core/test_workflow.py` with 18 unit tests covering all required scenarios for `Workflow.run()`.
  - Six test classes: `TestLinearPipeline`, `TestRouterWorkflow`, `TestEventSchemaParsing`, `TestNodeContextLogging`, `TestNodeExceptionPropagates`, `TestMetadataCleanup`.
  - Stub classes defined at module level: `LinearNodeA/B/C`, `LinearWorkflow`, `RouterSourceNode`, `BranchNodeB/C`, `BranchBCondition`, `StubBranchRouter`, `RouterWorkflow`, `FailingNode`, `FailingWorkflow`.

## Files Created or Modified
| File | Action |
|---|---|
| tests/core/test_workflow.py | created |
| planning/tasks/phase0-blockC/reports/task8-implement.md | created |

## Validation Output
**Commands run:**
```
uv run pytest --collect-only
uv run pytest -v
uv run pylint app/
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
cd app && uv run python -c "from database.session import Base, db_session"
cd app && uv run python -c "from database.repository import GenericRepository"
```
**Results:**
```
============================= test session starts ==============================
platform darwin -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
collected 87 items (18 new from test_workflow.py)

tests/core/test_workflow.py::TestLinearPipeline::test_all_nodes_ran PASSED
tests/core/test_workflow.py::TestLinearPipeline::test_node_outputs_are_correct PASSED
tests/core/test_workflow.py::TestLinearPipeline::test_node_execution_order_is_preserved PASSED
tests/core/test_workflow.py::TestRouterWorkflow::test_correct_branch_ran PASSED
tests/core/test_workflow.py::TestRouterWorkflow::test_wrong_branch_did_not_run PASSED
tests/core/test_workflow.py::TestRouterWorkflow::test_router_output_records_routing_decision PASSED
tests/core/test_workflow.py::TestRouterWorkflow::test_source_node_ran_before_router PASSED
tests/core/test_workflow.py::TestEventSchemaParsing::test_event_is_pydantic_model_after_run PASSED
tests/core/test_workflow.py::TestEventSchemaParsing::test_event_field_value_is_correct PASSED
tests/core/test_workflow.py::TestEventSchemaParsing::test_event_default_field_applies_when_omitted PASSED
tests/core/test_workflow.py::TestNodeContextLogging::test_start_log_emitted_for_each_node PASSED
tests/core/test_workflow.py::TestNodeContextLogging::test_finish_log_emitted_for_each_node PASSED
tests/core/test_workflow.py::TestNodeContextLogging::test_error_log_emitted_on_node_failure PASSED
tests/core/test_workflow.py::TestNodeContextLogging::test_finish_log_emitted_even_after_node_failure PASSED
tests/core/test_workflow.py::TestNodeExceptionPropagates::test_runtime_error_propagates_from_run PASSED
tests/core/test_workflow.py::TestNodeExceptionPropagates::test_exception_type_is_not_wrapped PASSED
tests/core/test_workflow.py::TestMetadataCleanup::test_nodes_key_absent_from_metadata_after_run PASSED
tests/core/test_workflow.py::TestMetadataCleanup::test_metadata_is_empty_after_stub_workflow PASSED

============================== 87 passed in 0.57s ==============================

pylint app/ → 9.29/10 (same as previous run, +0.00 — no regression)
All module imports clean (main, celery_app, Base/db_session, GenericRepository)
```
Status: PASSED

## Decisions and Trade-offs
- **`StubBranchRouter` naming**: The router stub was initially named `TestBranchRouter`, which triggered a `PytestCollectionWarning` (pytest tries to collect classes starting with "Test"). Renamed to `StubBranchRouter` to avoid confusion without any functional change.
- **Router is called twice per step**: `Workflow.run()` calls `process()` (which internally calls `route()`) and then `_get_next_node_class()` calls `route()` again on a fresh instance to determine the next class. This double-call is the current implementation behavior — the tests document it implicitly (the router must be stateless / deterministic across instantiations).
- **No modifications to `app/` source**: Task 8 is purely a test-writing task. No production code was changed. The pylint score is unchanged (9.29/10) confirming no regressions.
- **`load_dotenv()` in `Workflow.__init__`**: This is called when workflows are instantiated in tests. It is harmless since no `.env` file is required in the test environment — the call silently no-ops when no file is found.

## Follow-up Work
- `workflow.py` uses f-strings in logging calls (`logging.info(f"Starting node: {node_name}")`) which violates CLAUDE.md style rules. These pre-existing lint warnings (W1203) are not new — the pylint score was already 9.29/10 before this task. Fixing them is deferred to avoid scope creep; they should be addressed when `workflow.py` is next touched for a substantive change.

## git diff --stat
```
 tests/core/test_workflow.py | 229 +++++++++++++++++++++++++++++++++++++++++++
 1 file changed, 229 insertions(+)
```
