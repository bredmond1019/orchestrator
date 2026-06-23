---
type: ImplementationReport
title: Implementation Report — phase1-projectC-task6
description: StorageNode — BrainDocument persistence and embedding for the proposal generator workflow.
---

# Implementation Report — phase1-projectC-task6

**Date:** 2026-06-22
**Plan:** planning/phase1-projectC/tasks.md
**Scope:** Task 6

## What Was Built or Changed

- Created `StorageNode` for the proposal generator workflow. Reads the final `AutomationRoadmap` from `ReviseNode` output (if the revise branch ran) or from `ProposalWriterNode` output (pass branch). Embeds a summary string via `EmbeddingService.embed_text()`, then persists a `BrainDocument(doc_type="proposal")` row through `GenericRepository` + the `db_session` factory seam. Artifact id is captured from `task_context.event.artifact_id` before the session commits, preventing `DetachedInstanceError`.
- Created test suite with 8 hermetic tests covering: persistence called once, embedding called with non-empty text, node output contains artifact_id, post-commit id regression guard (ORM id cleared, event id survives), revise-branch priority over writer branch, revise-only context, BrainDocument field correctness, and roadmap-as-dict validation.
- Created `tests/__init__.py` and `tests/workflows/__init__.py` to establish the test package structure.

## Files Created or Modified

| File | Action |
|---|---|
| `app/workflows/proposal_generator_workflow_nodes/storage_node.py` | created |
| `tests/__init__.py` | created |
| `tests/workflows/__init__.py` | created |
| `tests/workflows/test_proposal_storage_node.py` | created |

## Validation Output

**Commands run:**
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
```

**Result:** PASSED

## Decisions and Trade-offs

- **doc_type = "proposal"**: The notes §3 lists `"proposal"|"diagnostic"` as valid doc_type values for Project C output. `"proposal"` is the accurate semantic choice for the output of the proposal generator; `"diagnostic"` is reserved for the intake structured data persisted by Project B.
- **file_path pattern**: Used `proposals/{artifact_id}/roadmap.json` to mirror the brain's filesystem convention (`diagnostics/{client_slug}/intake.json` from notes §2), giving each proposal its own namespace under a predictable top-level prefix.
- **Revise-branch detection via `nodes.get("ReviseNode")`**: The StorageNode is the terminal node for both DAG branches. Rather than requiring the router to set a flag, the node checks whether `ReviseNode` output exists in the context — this is the same approach the content pipeline uses for its dual-fetch branches and avoids any extra coordination.
- **`_persist` as a monkeypatched seam**: Following the content pipeline `StorageNode` pattern, `_persist` is a method the tests patch rather than injecting the repository/session via constructor — consistent with the `node_class()` zero-args constraint in CLAUDE.md rule 4 (no constructor injection).

## Follow-up Work

- Task 7 will wire `StorageNode` into the full proposal DAG alongside the other nodes built in Tasks 2–5.

## git diff --stat

```
 app/workflows/proposal_generator_workflow_nodes/storage_node.py | 88 ++++++++++++++++++++
 tests/__init__.py                                                |  0
 tests/workflows/__init__.py                                      |  0
 tests/workflows/test_proposal_storage_node.py                    | 183 ++++++++++++++++++++++++++++++++++++++++++
 4 files changed, 271 insertions(+)
```
