# Implementation Report — incremental-execution-observability-task7

**Date:** 2026-06-20
**Plan:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 7

## What Was Built or Changed
- Added two typed Pydantic response models, `WorkflowListResponse` and `WorkflowGraphResponse`, to `app/api/models.py`.
- Created `app/api/graph.py` with two read-only endpoints: `GET /workflows` (lists registered workflow types from `WorkflowRegistry`) and `GET /workflows/{workflow_type}/graph` (serializes nodes/edges from the workflow's `workflow_schema`; unknown type → 404).
- Wired the new graph router into `app/api/router.py` under the `workflows` tag.
- Added `tests/api/test_graph.py` covering the list endpoint, the `customer_care` graph node/edge set (read-only introspection of the frozen workflow), and the 404 path.

## Files Created or Modified
| File | Action |
|---|---|
| app/api/graph.py | created |
| app/api/models.py | modified |
| app/api/router.py | modified |
| tests/api/test_graph.py | created |

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

Notes: ruff clean; pylint 10.00/10; collection 213 tests (up from 210 prior to this task); full suite 213 passed. No "bastion" reference in `app/`.

## Decisions and Trade-offs
- Node identity uses the class `__name__`, matching `task_context.nodes` / `node_runs` keys so the static graph aligns with runtime state.
- The graph builder walks `start` + each `NodeConfig.node` + `connections` only; `parallel_nodes` are intentionally not treated as graph edges (consistent with the spec's expected node/edge set for `customer_care`).
- Unknown workflow type maps `KeyError` from `WorkflowRegistry[...]` to a 404 via `raise ... from e`.
- Graph tests use a bare `TestClient(app)` — these endpoints never touch the DB session, so the heavier `endpoint_context` fixture is unnecessary.

## Follow-up Work
None for Task 7. (`tests/` was restored into the sparse-checkout of this worktree to author and run the endpoint tests.)

## git diff --stat
```
 app/api/models.py | 9 +++++++++
 app/api/router.py | 3 ++-
 2 files changed, 11 insertions(+), 1 deletion(-)
```
(Note: `app/api/graph.py` and `tests/api/test_graph.py` are new untracked files not shown in the unstaged diff stat above.)
