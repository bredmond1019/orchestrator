# Fix Pass 2 — phase0-blockD-task9

**Date:** 2026-06-10
**Plan:** planning/tasks/phase0-blockD/tasks.md
**Fix pass:** 2

## Failures Addressed

| Criterion | Failure | Fix Applied |
|---|---|---|
| `uv run ruff check app/` reports zero errors | UP042 in `app/core/nodes/agent.py:29` — `ModelProvider(str, Enum)` should use `StrEnum` | Changed `from enum import Enum` → `from enum import StrEnum`; changed `class ModelProvider(str, Enum):` → `class ModelProvider(StrEnum):` |
| `uv run ruff check app/` reports zero errors | UP046 in `app/database/repository.py:16` — `GenericRepository(Generic[T])` should use PEP 695 type params | Removed `Generic`, `TypeVar` imports and `T = TypeVar("T")`; changed `class GenericRepository(Generic[T]):` → `class GenericRepository[T]:` |

## Changes Made

- `app/core/nodes/agent.py` — replaced `from enum import Enum` with `from enum import StrEnum`; changed `class ModelProvider(str, Enum):` to `class ModelProvider(StrEnum):` (resolves UP042)
- `app/database/repository.py` — removed `Generic` and `TypeVar` imports, removed `T = TypeVar("T")` binding, changed class declaration to PEP 695 syntax `class GenericRepository[T]:` (resolves UP046)

## Files Created or Modified

| File | Action |
|---|---|
| app/workflows/content_pipeline_workflow.py | created (generated stub — pass 1) |
| app/workflows/content_pipeline_workflow_nodes/__init__.py | created (generated stub — pass 1) |
| app/workflows/content_pipeline_workflow_nodes/initial_node.py | created (generated stub — pass 1) |
| app/schemas/content_pipeline_schema.py | created (generated stub — pass 1) |
| app/workflows/workflow_registry.py | modified (registered CONTENT_PIPELINE — pass 1) |
| tests/workflows/__init__.py | created (pass 1) |
| tests/workflows/test_content_pipeline_workflow.py | created (pass 1) |
| app/core/nodes/agent.py | modified (UP042 fix — pass 2) |
| app/database/repository.py | modified (UP046 fix — pass 2) |

## Validation Output

```
$ uv run ruff check app/
All checks passed!

$ uv run pytest
============================= test session starts ==============================
platform darwin -- Python 3.12.4, pytest-9.0.3, pluggy-1.6.0
collected 170 items

tests/api/test_endpoint.py ..
tests/core/test_nodes_parallel.py ..........
tests/core/test_nodes_router.py .......................
tests/core/test_schema.py ..................
tests/core/test_task.py .......................
tests/core/test_validate.py .......................
tests/core/test_workflow.py ..................
tests/database/test_repository.py .............................
tests/services/test_prompt_loader.py ....................
tests/workflows/test_content_pipeline_workflow.py ....

============================= 170 passed in 0.93s ==============================

$ uv run pylint app/
--------------------------------------------------------------------
Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)

$ cd app && uv run python -c "from main import app"
(exit 0)

$ cd app && uv run python -c "from worker.config import celery_app"
(exit 0)

$ cd app && uv run python -c "from workflows.workflow_registry import WorkflowRegistry; WorkflowRegistry.CONTENT_PIPELINE"
WorkflowRegistry.CONTENT_PIPELINE
```

Status: PASSED

## git diff --stat

```
 app/core/nodes/agent.py    | 4 ++--
 app/database/repository.py | 6 +-----
 2 files changed, 3 insertions(+), 7 deletions(-))
```
