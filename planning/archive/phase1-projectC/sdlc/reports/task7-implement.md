---
type: ImplementationReport
title: Implementation Report — phase1-projectC-task7
description: Wire the proposal_generator workflow DAG and integration test.
---

# Implementation Report — phase1-projectC-task7

**Date:** 2026-06-22
**Plan:** planning/phase1-projectC/tasks.md
**Scope:** Task 7

## What Was Built or Changed

- Wired the full `ProposalGeneratorWorkflow` DAG in `proposal_generator_workflow.py`, replacing the scaffold stub: `ProposalCompanyResearchNode → OpportunityIdentifierNode → ProposalWriterNode → ProposalReviewNode → ProposalReviewRouterNode → {StorageNode | ProposalReviseNode → StorageNode}`. Router marked `is_router=True`. `WorkflowValidator` passes (acyclic DAG).
- Deleted `app/workflows/proposal_generator_workflow_nodes/initial_node.py` — scaffold placeholder no longer importable, as required by the integration test.
- Fixed integration key mismatches discovered when connecting all nodes end-to-end:
  - `OpportunityIdentifierNode.process()` read from wrong context key (`"CompanyResearchNode"` → `"ProposalCompanyResearchNode"`) and wrote output as top-level kwargs; changed to write `result={"candidates": [...], "recommended": ...}` (standard framework convention, matching what `ProposalWriterNode` expects).
  - `ProposalReviewNode.process()` failed to serialize Pydantic `AutomationRoadmap` stored by writer; added explicit `model_dump()` extraction from `writer_output["result"]`.
  - `ProposalReviseNode.process()` failed to serialize nested Pydantic objects in the user prompt; added `_serialize()` helper that recursively calls `model_dump()`.
  - `StorageNode._read_final_roadmap()` used wrong node name (`"ReviseNode"` → `"ProposalReviseNode"`) and wrong key (`"roadmap"` → `"result"`); added `_roadmap_from_revise_output()` to reconstruct `AutomationRoadmap` from `ProposalReviseNode.OutputType` JSON-encoded fields.
- Updated tests to match the corrected key contract:
  - `tests/workflows/test_opportunity_identifier_node.py`: context key changed to `"ProposalCompanyResearchNode"`; output assertions changed to read from `stored["result"]["candidates"]` / `stored["result"]["recommended"]`.
  - `tests/workflows/test_proposal_storage_node.py`: rewrote to use `{"result": roadmap}` key and `"ProposalReviseNode"` node name; added revise-branch reconstruction test.
  - `tests/workflows/test_proposal_review_router.py`: fixed `test_review_reads_proposal_writer_output` to store roadmap under `{"result": roadmap}`.
- Created `tests/workflows/test_proposal_generator_workflow.py` — full integration test covering structure (registry, schema wiring, router flag, connection map, acyclic DAG, scaffold removal) and integration (both pass and revise routes end-to-end with all agents mocked), plus diagnostic-constraint tests (candidates sorted composite-desc, top_profiles ≤ 3, PT/EN language bodies, intake-style input produces valid `AutomationRoadmap`).

## Files Created or Modified

| File | Action |
|---|---|
| `app/workflows/proposal_generator_workflow.py` | modified (wired DAG, removed scaffold stub) |
| `app/workflows/proposal_generator_workflow_nodes/initial_node.py` | deleted |
| `app/workflows/proposal_generator_workflow_nodes/opportunity_identifier_node.py` | modified (fixed context key + output structure) |
| `app/workflows/proposal_generator_workflow_nodes/proposal_review_node.py` | modified (serialize roadmap from result key) |
| `app/workflows/proposal_generator_workflow_nodes/proposal_revise_node.py` | modified (serialize nested Pydantic objects) |
| `app/workflows/proposal_generator_workflow_nodes/storage_node.py` | modified (correct node/key names; reconstruct roadmap from revise OutputType) |
| `tests/workflows/test_proposal_generator_workflow.py` | created |
| `tests/workflows/test_opportunity_identifier_node.py` | modified (context key + output key updates) |
| `tests/workflows/test_proposal_storage_node.py` | modified (key contract update + revise branch tests) |
| `tests/workflows/test_proposal_review_router.py` | modified (one test fixture updated) |

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

- **Key contract standardisation**: All agent nodes were changed to store output under `"result"` (matching the framework convention used in content_pipeline). This required updating tests that pre-populated context with the old key structure. The integration was the forcing function; the per-task unit tests had been written with inconsistent assumptions.
- **StorageNode revise reconstruction**: `ProposalReviseNode.OutputType` deliberately uses JSON-encoded string fields (`candidates_json`, `top_profiles_json`) for its structured outputs (the agent returns JSON arrays as strings). `StorageNode._roadmap_from_revise_output()` reconstructs the `AutomationRoadmap` from these fields. This keeps the revise node's OutputType slim (avoids nested Pydantic-in-Pydantic serialization through pydantic-ai) while giving the storage node a fully validated roadmap.
- **`_serialize()` helper in ReviseNode**: A lightweight recursive helper serializes the revise prompt payload (which contains the original roadmap Pydantic model nested in the writer's output). Using `default=str` was insufficient because it would produce `str(AutomationRoadmap(...))` rather than a JSON-compatible dict.

## Follow-up Work

- The `ProposalReviseNode.OutputType` JSON-string approach works but is fragile. A future clean-up could store the revised roadmap directly as an `AutomationRoadmap` (breaking the pydantic-ai structured-output constraint that prevents nested Pydantic models), or use a separate post-processing step.

## git diff --stat

```
 app/workflows/proposal_generator_workflow.py       | 103 +++++++++++++++---
 .../initial_node.py                                |  18 ----
 .../opportunity_identifier_node.py                 |   8 +-
 .../proposal_review_node.py                        |  16 ++-
 .../proposal_revise_node.py                        |  12 ++-
 .../storage_node.py                                |  71 +++++++++++--
 .../workflows/test_opportunity_identifier_node.py  |  32 +++---
 tests/workflows/test_proposal_review_router.py     |   7 +-
 tests/workflows/test_proposal_storage_node.py      | 117 +++++++++++++++++----
 9 files changed, 293 insertions(+), 91 deletions(-)
```
