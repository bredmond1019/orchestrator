---
type: ImplementationReport
title: Implementation Report — phase1-projectC-task5
description: Review + router + revise branch for the proposal_generator workflow.
---

# Implementation Report — phase1-projectC-task5

**Date:** 2026-06-22
**Plan:** planning/phase1-projectC/tasks.md
**Scope:** Task 5 — Review + router + revise branch

## What Was Built or Changed

- `ProposalReviewNode` (AgentNode): validates an `AutomationRoadmap` against five explicit Diagnostic delivery criteria (client named ≥3 times, one testable deliverable, 4–8 wk timeline, no vague language, investment matches complexity); emits per-criterion PASS/FAIL with notes and an overall `pass`/`revise` verdict.
- `ProposalReviewRouterNode` (BaseRouter + RouterNode): routes `pass` → `StorageNode`, `revise` → `ProposalReviseNode`. No fallback; missing/null result returns `None`.
- `ProposalReviseNode` (AgentNode): reads original roadmap from `ProposalWriterNode` and review result from `ProposalReviewNode`, produces a corrected roadmap JSON payload. Flows linearly to `StorageNode` with no loop-back (DAG stays acyclic).
- `StorageNode` stub: minimal pass-through so the router can import the class. Task 6 replaces this with the real persistence implementation.
- `app/prompts/proposal_review.j2`: system prompt embedding all five review criteria with explicit guidance for each PASS/FAIL evaluation.
- `app/prompts/proposal_revise.j2`: system prompt guiding targeted revision of only the failing criteria, with price-range anchors by scope.
- `tests/workflows/test_proposal_review_router.py`: 14 unit tests covering review verdict emission, router branching (both pass and revise, model and dict payloads), revise node context forwarding, and structural DAG assertion.

## Files Created or Modified

| File | Action |
|---|---|
| `app/workflows/proposal_generator_workflow_nodes/proposal_review_node.py` | created |
| `app/workflows/proposal_generator_workflow_nodes/proposal_review_router_node.py` | created |
| `app/workflows/proposal_generator_workflow_nodes/proposal_revise_node.py` | created |
| `app/workflows/proposal_generator_workflow_nodes/storage_node.py` | created (stub for Task 6) |
| `app/prompts/proposal_review.j2` | created |
| `app/prompts/proposal_revise.j2` | created |
| `tests/workflows/test_proposal_review_router.py` | created |

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

- **StorageNode stub**: Task 5's router must import `StorageNode` to instantiate it on the `pass` branch. Task 6 owns the real implementation. A minimal pass-through stub was added here so the router and its tests work now; Task 6 replaces the file body without changing the class name or import path.
- **Top-level imports in router**: Initially used deferred (inside-function) imports to guard against potential circular imports; those don't actually exist here, so imports were moved to module level (pylint 10.00/10 confirmed).
- **Revise OutputType as structured fields**: The revise node returns `candidates_json` and `top_profiles_json` as JSON strings rather than typed lists, because the LLM output type cannot embed nested Pydantic lists directly in this framework version. Task 7 (DAG wiring) can reconstruct the full `AutomationRoadmap` from these fields when wiring storage.
- **`CriterionResult` as AgentNode.OutputType subclass**: Allows `ProposalReviewNode.OutputType.criteria_results` to be a typed list without losing Pydantic validation; the subclass adds no extra framework behavior.

## Follow-up Work

- Task 6 must replace `storage_node.py` stub with real `BrainDocument` + `EmbeddingService` + `GenericRepository` persistence.
- Task 7 wires the full DAG in `proposal_generator_workflow.py`, connecting these nodes in order: `CompanyResearchNode → OpportunityIdentifierNode → ProposalWriterNode → ProposalReviewNode → ProposalReviewRouterNode → {StorageNode | ProposalReviseNode → StorageNode}`.

## git diff --stat

```
 app/prompts/proposal_review.j2                                                             | 49 ++++++++++++++++++++++
 app/prompts/proposal_revise.j2                                                             | 65 +++++++++++++++++++++++++++++
 app/workflows/proposal_generator_workflow_nodes/proposal_review_node.py                    | 62 +++++++++++++++++++++++++++
 app/workflows/proposal_generator_workflow_nodes/proposal_review_router_node.py             | 48 +++++++++++++++++++++
 app/workflows/proposal_generator_workflow_nodes/proposal_revise_node.py                    | 73 +++++++++++++++++++++++++++++++
 app/workflows/proposal_generator_workflow_nodes/storage_node.py                            | 17 ++++++++
 planning/phase1-projectC/sdlc/reports/task5-implement.md                                   | (this file)
 tests/workflows/test_proposal_review_router.py                                             | 275 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
```
