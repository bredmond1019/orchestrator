# Implementation Report — phase1-projectA-task7

**Date:** 2026-06-20
**Plan:** planning/phase1-projectA/tasks.md
**Scope:** Task 7

## What Was Built or Changed
- Rewrote `app/workflows/content_pipeline_workflow.py`: `start=SourceRouterNode`; full graph wired SourceRouterNode (router) -> FetchTranscriptNode | FetchArticleNode -> SummarizerNode -> StorageNode -> BlogDecisionRouterNode (router) -> BlogWriterNode -> SelfCriticNode -> ReviseNode. Both routers marked `is_router=True`; every NodeConfig given a description; ReviseNode is terminal.
- Deleted the scaffold no-op `app/workflows/content_pipeline_workflow_nodes/initial_node.py` and removed its import/reference.
- Fixed a latent framework bug in `app/core/nodes/router.py` `BaseRouter.process()`: a router that legitimately ends a branch (`route()` returns `None`, e.g. the digest-only path where `make_blog=False`) crashed on `None.node_name`. Now records `{"next_node": None}`. This is required for the digest-only acceptance criterion and is generically correct (a terminal router must not crash). Existing match behavior is unchanged.
- Rewrote `tests/workflows/test_content_pipeline_workflow.py`: kept the registration test; replaced the InitialNode structural assertions with the new graph (start node, router flags, full connection map, `WorkflowValidator` passes, scaffold node removed); added two integration tests running the full chain with all agents/services mocked — `make_blog=false` (digest-only: fetch->summarize->store, blog nodes do NOT run, 1024-dim embedding persisted, HTML index written) and `make_blog=true` (linear blog branch also runs). Net test count up from 4 to 12 in this file.
- Added one unit test in `tests/core/test_nodes_router.py` directly covering the terminal-router `process()` guard.

## Files Created or Modified
| File | Action |
|---|---|
| app/workflows/content_pipeline_workflow.py | modified |
| app/core/nodes/router.py | modified |
| app/workflows/content_pipeline_workflow_nodes/initial_node.py | deleted |
| tests/workflows/test_content_pipeline_workflow.py | modified (rewritten) |
| tests/core/test_nodes_router.py | modified |

## Validation Output
**Commands run:**
```
uv run python -m ruff check app/
uv run python -m pylint app/
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run python -m pytest --collect-only -q   (295 tests collected)
uv run python -m pytest                      (295 passed)
cd app && uv run alembic heads / history     (single head, learning_artifacts -> pgvector chain valid)
```
**Result:** PASSED

Note: `cd app && uv run alembic upgrade head` cannot run in this sandbox — no local Postgres server is listening on 5432 (connection refused). It is not a gating check in `planning/harness.json`, and Task 7 does not touch the migration; the migration graph validates offline (`alembic heads`/`history`). Task 2 verified `upgrade head` against a live DB.

## Decisions and Trade-offs
- The digest-only termination path (router returns `None`) exposed a real crash in `BaseRouter.process()` that no prior test exercised (Task 6 only tested `route()` directly). The minimal, generically-correct fix is the one-line guard in core rather than any wiring workaround — the workflow loop always executes a router node's `process()`, so the router itself must tolerate a `None` route. Covered by a new core unit test and both integration tests.
- Integration tests mock at the seams Tasks 3/4/5/6 established: `AgentNode.__init__` is no-op'd (no real pydantic-ai Agent/API key), `run_agent_recorded` returns the proper OutputType per node, fetch services are patched, `EmbeddingService` + `StorageNode._persist` are captured, and the digest dir is a `tmp_path` via `CONTENT_DIGEST_DIR`. Node execution is asserted via `node_runs` status (SUCCESS vs PENDING) — the framework seeds every node PENDING, so blog nodes staying PENDING proves they did not run on the digest-only path.

## Follow-up Work
- None for Task 7. `alembic upgrade head` should be confirmed against the Postgres service in an environment where it is running (already validated under Task 2).

## git diff --stat
```
 app/core/nodes/router.py                           |   4 +-
 app/workflows/content_pipeline_workflow.py         |  95 +++++++-
 .../initial_node.py                                |   7 -
 tests/core/test_nodes_router.py                    |  12 +
 tests/workflows/test_content_pipeline_workflow.py  | 244 ++++++++++++++++++++-
 5 files changed, 337 insertions(+), 25 deletions(-)
```
