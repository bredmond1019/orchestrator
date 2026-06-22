---
type: ImplementReport
title: Implementation Report — phase1-projectC-task1
description: Schemas, scaffold, and registry registration for the proposal_generator workflow (Project C).
---

# Implementation Report — phase1-projectC-task1

**Date:** 2026-06-22
**Plan:** planning/phase1-projectC/tasks.md
**Scope:** Task 1

## What Was Built or Changed

- Created `app/schemas/proposal_generator_schema.py` with `ProposalGeneratorEventSchema`, `ScoredCandidate` (and `Opportunity` alias), `WorkflowProfile`, and `AutomationRoadmap`. The schema enforces the binding composite formula `(frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)` via a Pydantic `model_validator`, candidates-sorted-descending invariant, and `top_profiles` max-3 limit.
- Created `app/workflows/proposal_generator_workflow.py` — minimal stub `ProposalGeneratorWorkflow` with `event_schema=ProposalGeneratorEventSchema` and a placeholder `InitialNode` start node (replaced in Task 7 when the DAG is wired).
- Created `app/workflows/proposal_generator_workflow_nodes/__init__.py` — workflow node package.
- Created `app/workflows/proposal_generator_workflow_nodes/initial_node.py` — scaffold placeholder node (pass-through) to satisfy `WorkflowSchema.start` type requirement; removed by Task 7.
- Registered `PROPOSAL_GENERATOR = ProposalGeneratorWorkflow` in `app/workflows/workflow_registry.py`.
- Added `WorkflowRegistry.PROPOSAL_GENERATOR.name → ProposalGeneratorEventSchema` to `app/api/schema_registry.py`.
- Created `tests/schemas/test_proposal_generator_schema.py` with 26 tests covering: field validation and defaults, composite formula correctness, wrong-composite rejection, sort invariant, `top_profiles` limit, and dual-registry presence regression guard.
- Fixed pre-existing ruff import ordering in `app/workflows/research_agent_workflow_nodes/company_research_node.py` (I001, auto-fixed; worktree inherited the issue from main repo).

## Files Created or Modified

| File | Action |
|---|---|
| app/schemas/proposal_generator_schema.py | created |
| app/workflows/proposal_generator_workflow.py | created |
| app/workflows/proposal_generator_workflow_nodes/__init__.py | created |
| app/workflows/proposal_generator_workflow_nodes/initial_node.py | created |
| app/workflows/workflow_registry.py | modified |
| app/api/schema_registry.py | modified |
| app/workflows/research_agent_workflow_nodes/company_research_node.py | modified (ruff I001 fix) |
| tests/__init__.py | created |
| tests/api/__init__.py | created |
| tests/workflows/__init__.py | created |
| tests/schemas/test_proposal_generator_schema.py | created |

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

- **InitialNode placeholder:** `WorkflowSchema.start` is typed `type[Node]` (not Optional), so a stub placeholder is required until Task 7 wires the real DAG. Pattern mirrors the scaffolding done by `createworkflow` and is consistent with how the research_agent_workflow was initially built.
- **tests/schemas/ without __init__.py:** Creating `tests/schemas/__init__.py` caused a namespace collision with `app/schemas` because pytest adds `tests/` to sys.path. Removing the `__init__.py` resolves the collision and matches the pattern used for other test subdirectories that share names with app packages.
- **Ruff fix in company_research_node.py:** The I001 import ordering error pre-existed in both main and the worktree. Fixing it is a mechanical ruff auto-fix (import sort) that does not alter behavior and brings the worktree to a clean lint state.
- **Composite validator on model:** The composite formula is enforced at the Pydantic model level (not just in the prompt) to create a testable, code-level guarantee. The rubric axis anchors and scoring formula text belong in the `.j2` prompt (Task 3); the formula math is enforced here.

## Follow-up Work

- Task 2: Reuse `CompanyResearchNode` from Project B in the proposal pipeline.
- Task 3: `OpportunityIdentifierNode` with rubric-anchored `.j2` prompt.
- Task 4: `ProposalWriterNode` producing PT + EN `AutomationRoadmap`.
- Task 5: Review + router + revise branch.
- Task 6: `StorageNode` with `GenericRepository` and `EmbeddingService`.
- Task 7: Wire the full DAG and remove `InitialNode` placeholder.

## git diff --stat

```
 app/api/schema_registry.py                                           | 2 ++
 app/workflows/research_agent_workflow_nodes/company_research_node.py | 3 +--
 app/workflows/workflow_registry.py                                   | 2 ++
 3 files changed, 5 insertions(+), 2 deletions(-)
```
