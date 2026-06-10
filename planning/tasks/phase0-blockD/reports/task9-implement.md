# Implementation Report — phase0-blockD-task9

**Date:** 2026-06-10
**Plan:** planning/tasks/phase0-blockD/tasks.md
**Scope:** Task 9 — Scaffold Project A (`content_pipeline` workflow)

## What Was Built or Changed
- Scaffolded the `content_pipeline` (Project A) workflow using the `createworkflow` generator (run via `python -m app.core.commands.init_workflow` since the console script is not installed in this fresh venv). Generated stubs left as-is (no logic added):
  - `app/workflows/content_pipeline_workflow.py` — `ContentPipelineWorkflow` with a stub `WorkflowSchema`
  - `app/workflows/content_pipeline_workflow_nodes/__init__.py`
  - `app/workflows/content_pipeline_workflow_nodes/initial_node.py` — stub `InitialNode`
  - `app/schemas/content_pipeline_schema.py` — empty `ContentPipelineEventSchema(BaseModel)`
- Registered the new workflow in `app/workflows/workflow_registry.py` (added `CONTENT_PIPELINE = ContentPipelineWorkflow`).
- Added a scaffold smoke test `tests/workflows/test_content_pipeline_workflow.py` (CLAUDE.md Rule 1 — every new workflow ships with tests).

## Files Created or Modified
| File | Action |
|---|---|
| app/workflows/content_pipeline_workflow.py | created (generated stub) |
| app/workflows/content_pipeline_workflow_nodes/__init__.py | created (generated stub) |
| app/workflows/content_pipeline_workflow_nodes/initial_node.py | created (generated stub) |
| app/schemas/content_pipeline_schema.py | created (generated stub) |
| app/workflows/workflow_registry.py | modified (registered CONTENT_PIPELINE) |
| tests/workflows/__init__.py | created |
| tests/workflows/test_content_pipeline_workflow.py | created |

## Validation Output
**Commands run:**
```
uv run pytest
uv run ruff check app/workflows/content_pipeline_workflow.py app/workflows/content_pipeline_workflow_nodes/ app/schemas/content_pipeline_schema.py app/workflows/workflow_registry.py
uv run pylint <same new files>
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
cd app && uv run python -c "from workflows.workflow_registry import WorkflowRegistry; WorkflowRegistry.CONTENT_PIPELINE"
```
**Results:**
```
170 passed in 1.23s
ruff: 0 errors on new/modified files
pylint: rated at 10.00/10 on new/modified files
main OK
celery OK
registry OK  (prints WorkflowRegistry.CONTENT_PIPELINE)
```
Status: PASSED

## Decisions and Trade-offs
- The `createworkflow` console script is not installed in this fresh worktree venv (`uv run createworkflow` -> spawn error), so the generator was invoked as the module `python -m app.core.commands.init_workflow` with `content_pipeline` piped to its `input()` prompt. Output files are identical to what the script would produce.
- The generator emits trailing whitespace / missing final newlines. "Do not add any logic" governs workflow logic, not lint hygiene; CLAUDE.md mandates `ruff --fix` before commit, so `ruff --fix` was applied to the generated files. No code logic was added — stubs remain functionally identical.
- Added a minimal registration/schema-wiring smoke test rather than behavioral node tests, because Task 9 deliberately scaffolds stubs with no node logic. The test guards registration, schema wiring, the start node, and that the workflow validates and builds its node map.

## Follow-up Work
- The two remaining `uv run ruff check app/` errors are pre-existing in `app/database/repository.py` (UP046 `Generic[T]`), unrelated to Task 9 and out of scope.
- Schema fields, real nodes, and connections for `content_pipeline` are intentionally deferred (later Project A work).

## git diff --stat
```
 app/schemas/content_pipeline_schema.py             |  5 ++++
 app/workflows/content_pipeline_workflow.py         | 21 +++++++++++++
 .../content_pipeline_workflow_nodes/__init__.py    |  0
 .../initial_node.py                                |  7 +++++
 app/workflows/workflow_registry.py                 |  2 ++
 tests/workflows/__init__.py                        |  0
 tests/workflows/test_content_pipeline_workflow.py  | 35 ++++++++++++++++++++++
 7 files changed, 70 insertions(+)
```
