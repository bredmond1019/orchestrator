---
type: ImplementReport
title: Implementation Report — phase1-projectC-task2
description: CompanyResearchNode reuse for proposal_generator pipeline (Task 2).
---

# Implementation Report — phase1-projectC-task2

**Date:** 2026-06-22
**Plan:** planning/phase1-projectC/tasks.md
**Scope:** Task 2

## What Was Built or Changed

- `app/workflows/proposal_generator_workflow_nodes/company_research_node.py` — `ProposalCompanyResearchNode` subclasses Project B's `CompanyResearchNode` without modifying that file. Overrides `_build_initial_messages` to consume `ProposalGeneratorEventSchema` fields (`company_name`, `industry`, `description`, `intake_notes`) and load `proposal_research_brief.j2` via `PromptManager`. All tool definitions, the tool-use loop, and `ResearchBriefOutput` validation are inherited unchanged.
- `app/prompts/proposal_research_brief.j2` — Dedicated Jinja2 prompt for the proposal pipeline's research phase. Includes industry-specific research guidance and optional intake_notes injection. No prompt text is hardcoded in Python.
- `tests/workflows/test_proposal_company_research_node.py` — 17 hermetic unit tests covering: subclass identity, correct prompt template loaded, industry/description/intake_notes forwarded to PromptManager, initial message content, Pydantic event path, loop termination, evidence written to TaskContext under `ProposalCompanyResearchNode` key, and web_search dispatch.

## Files Created or Modified

| File | Action |
|---|---|
| app/workflows/proposal_generator_workflow_nodes/company_research_node.py | created |
| app/prompts/proposal_research_brief.j2 | created |
| tests/workflows/test_proposal_company_research_node.py | created |

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

- **Subclass, not wrapper:** Subclassing `CompanyResearchNode` reuses the tool definitions, loop, and `ResearchBriefOutput` validation verbatim. Only `_build_initial_messages` is overridden to supply the richer proposal context and load a different prompt template. This keeps the delta minimal and the reuse explicit.
- **Class name `ProposalCompanyResearchNode`:** Named to distinguish it from the base `CompanyResearchNode` in the proposal workflow, since `node_name` returns the class name (used as the `TaskContext.nodes` key). This avoids key collisions if both nodes ever appear in the same context.
- **`proposal_research_brief.j2` is a separate template:** Not a modified copy of `research_agent_brief.j2`. The proposal pipeline needs industry and intake_notes context the base prompt does not include. Keeping templates separate preserves the base template unchanged.
- **Sparse checkout:** The worktree uses git sparse-checkout; `tests/` was missing initially. Added via `git sparse-checkout add tests` to restore the existing test suite.

## Follow-up Work

- Task 7 will wire `ProposalCompanyResearchNode` as the `start` node in `ProposalGeneratorWorkflow.workflow_schema`, replacing the `InitialNode` stub.

## git diff --stat

```
 app/prompts/proposal_research_brief.j2                                              | 37 +++++++++++++++++++
 app/workflows/proposal_generator_workflow_nodes/company_research_node.py            | 68 +++++++++++++++++++++++++++++++++
 planning/phase1-projectC/sdlc/reports/task2-implement.md                           | (this file)
 tests/workflows/test_proposal_company_research_node.py                             | 274 +++++++++++++++++++++++++++
 4 files changed, 379 insertions(+)
```
