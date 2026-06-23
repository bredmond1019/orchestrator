---
type: ImplementationReport
title: Implementation Report — phase1-projectC-task3
description: OpportunityIdentifierNode, rubric prompt, and tests for Project C proposal generator
---

# Implementation Report — phase1-projectC-task3

**Date:** 2026-06-22
**Plan:** planning/phase1-projectC/tasks.md
**Scope:** Task 3

## What Was Built or Changed

- `app/prompts/proposal_opportunity_identifier.j2` — System prompt for `OpportunityIdentifierNode` with the complete Diagnostic rubric axis definitions and anchor descriptions (frequency, time_cost, buildability, each scored 1–5). The binding composite formula and output requirements are embedded in the prompt so scoring is model-version-stable without Python changes.
- `app/workflows/proposal_generator_workflow_nodes/opportunity_identifier_node.py` — `OpportunityIdentifierNode` (AgentNode subclass). Reads `company_name`, `industry`, `description`, and `intake_notes` from the event; reads the structured research brief from `CompanyResearchNode` output in `TaskContext`; serializes all context into a JSON user prompt; runs the agent; validates the `ScoredCandidate` composite formula via the Pydantic model; writes `candidates` (list of dicts) and `recommended` (str) to context under the node's name.
- `tests/workflows/test_opportunity_identifier_node.py` — 21 unit tests covering: structured output stored in context, composite formula math and validation error on wrong composite, recommendation is a single string matching the top candidate, research brief consumed from context (including missing-node KeyError path), prompt sourced from `.j2` via `PromptManager`, model provider convention (CLAUDE_CODE_SDK / sonnet), and dict-event fallback path.

## Files Created or Modified

| File | Action |
|---|---|
| `app/prompts/proposal_opportunity_identifier.j2` | created |
| `app/workflows/proposal_generator_workflow_nodes/opportunity_identifier_node.py` | created |
| `tests/workflows/test_opportunity_identifier_node.py` | created |
| `planning/phase1-projectC/sdlc/reports/task3-implement.md` | created |

## Validation Output

**Commands run:**
```
cd app && uv run python -c 'import main'
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
```
**Result:** PASSED

## Decisions and Trade-offs

- **OutputType uses `ScoredCandidate` directly** — the node's `OutputType.candidates` field is typed as `list[ScoredCandidate]`. The Pydantic `model_validator` on `ScoredCandidate` enforces the composite formula at parse time, so any model output with a wrong composite is rejected before it reaches `process()`. This is the tightest possible validation seam.
- **Candidates stored as `list[dict]`** — `update_node` writes `[c.model_dump() for c in output.candidates]` rather than the raw `ScoredCandidate` objects, which mirrors the `to_jsonable` pattern used by `run_agent_recorded` and ensures the context is always JSON-serializable.
- **Prompt embeds rubric anchors in full** — per the spec constraint ("embed the rubric axis definitions"), all five anchor levels for each of the three axes are spelled out in the `.j2` file. This makes the prompt longer but removes any dependence on external rubric files at inference time.
- **No sorting enforcement in the node** — the spec says "Sort `candidates` composite-desc" but the `AutomationRoadmap` model_validator already enforces this in the downstream schema. The node delegates sorting to the model (via the prompt instruction) and the downstream schema validates it. This matches the pattern for `ScoredCandidate.composite` — the constraint is in the schema, not duplicated in node logic.

## Follow-up Work

- Task 4: `ProposalWriterNode` — reads `OpportunityIdentifierNode` output and produces the full `AutomationRoadmap`.
- Task 7: Wire the DAG in `ProposalGeneratorWorkflow.workflow_schema` to connect `OpportunityIdentifierNode` between `CompanyResearchNode` and `ProposalWriterNode`.

## git diff --stat

```
(new untracked files — no diff until staged)
app/prompts/proposal_opportunity_identifier.j2            | 82 +
app/workflows/proposal_generator_workflow_nodes/
  opportunity_identifier_node.py                          | 78 +
tests/workflows/test_opportunity_identifier_node.py       | 233 +
planning/phase1-projectC/sdlc/reports/task3-implement.md  | (this file)
```
