---
type: ReviewReport
title: Review Report — phase1-projectB
description: SDLC review verdict for the thin-cut research agent (Phase 1, Project B).
---

# Review Report — phase1-projectB

**Date:** 2026-06-22
**Spec:** planning/phase1-projectB/tasks.md
**Scope:** Full spec
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `uv run createworkflow`-style layout exists: `research_agent_workflow.py`, `research_agent_workflow_nodes/company_research_node.py`, `schemas/research_agent_schema.py`; the generated `initial_node.py` stub is removed. | MET | All three files present; `__init__.py` only in workflow_nodes dir — no `initial_node.py`. |
| `CompanyResearchNode` is a `ToolUseNode` subclass driving a raw `anthropic` loop with the inherited `max_iterations` guard; no edits to `app/core/nodes/tool_use.py`. | MET | `company_research_node.py:14` — `class CompanyResearchNode(ToolUseNode):`; base class untouched; `max_iterations` guard inherited. |
| The loop's system prompt lives in `app/prompts/research_agent_brief.j2` and is loaded via `PromptManager` — no prompt string literal in Python. | MET | `research_agent_brief.j2` exists with full system prompt; `company_research_node.py:95` — `PromptManager.get_prompt("research_agent_brief", ...)`. No prompt text hardcoded in Python. |
| Output validates to `ResearchBriefOutput` with non-empty `likely_time_sinks` and a populated `automation_hypothesis`; schema is shaped toward `DiagnosticIntakeOutput` per `notes.md` §2. | MET | `research_agent_schema.py:47` — `likely_time_sinks: list[str]` with `min_length=1`; `automation_hypothesis: str`; docstring notes deferred hardened fields. |
| `WorkflowRegistry.RESEARCH_AGENT` resolves and the workflow passes `WorkflowValidator`. | MET | `workflow_registry.py:11` — `RESEARCH_AGENT = ResearchAgentWorkflow`; `test_research_agent_workflow.py` — WorkflowValidator test passes. |
| Tests cover: tool-result injection, `web_search` dispatch, structured-brief capture, termination on `end_turn`, termination on `max_iterations`, and the diagnostic-alignment output check. | MET | `test_company_research_node.py` — TestToolResultInjection, TestWebSearchDispatch, TestSubmitResearchBrief, TestLoopTerminatesOnEndTurn, TestMaxIterationsGuard; `test_research_agent_workflow.py:123` — `test_diagnostic_alignment_brief_valid_and_non_empty`. |
| No Celery wiring, no critic/revise loop, no storage/embedding/`BrainDocument` (those are the deferred hardened version). | MET | No Celery imports, no storage calls, no BrainDocument references in any new file. |
| All gated checks in `planning/harness.json` pass; net-new ruff violations = 0; pytest collection count does not drop. | MET | Ruff: all checks passed. Pylint: 9.99/10 (sole C0301 in pre-existing `brain_document.py`, no new violations). Pytest: 417 passed, 7 skipped. |

## Fresh Test Results

**standing-rules (GATING):** PASS — no f-string-in-logging, no open-without-encoding, no param-named-id violations in new files.

**db-session-import (GATING):**
```
cd app && uv run python -c 'import database.session'
```
PASS — clean import, no errors.

**db-repository-import (GATING):**
```
cd app && uv run python -c 'import database.repository'
```
PASS — clean import, no errors.

**net-new-lint (GATING):**
```
uv run python -m ruff check app/
All checks passed!
```
PASS — zero ruff violations.

**pylint (GATING):**
```
uv run python -m pylint app/
************* Module database.brain_document
app/database/brain_document.py:77:0: C0301: Line too long (102/100) (line-too-long)

Your code has been rated at 9.99/10
```
PASS — sole violation is the pre-existing `C0301` in `brain_document.py` (predates this task). No new violations introduced.

**pytest-count (GATING):** PASS — 424 tests collected (up from 398 baseline; 19 new tests added by this task).

**pytest (GATING):**
```
417 passed, 7 skipped, 7 warnings in 2.06s
```
PASS — full suite green; all 9 `test_company_research_node` tests and all 10 `test_research_agent_workflow` tests pass.

## Verdict: PASS

All 8 acceptance criteria are fully met and every gating check in `planning/harness.json` passes cleanly. The thin-cut research agent is correctly structured: `CompanyResearchNode` subclasses `ToolUseNode` without modifying the base class, the system prompt is exclusively sourced from `research_agent_brief.j2` via `PromptManager`, `ResearchBriefOutput` enforces non-empty `likely_time_sinks`, `WorkflowRegistry.RESEARCH_AGENT` resolves and the workflow passes `WorkflowValidator`, and the test suite covers all required scenarios including the diagnostic-alignment output check. No Celery, storage, or embedding concerns were introduced. Net-new ruff violations = 0; pylint score unchanged at 9.99/10 with the lone pre-existing convention violation.

## Issues Found

None.

## Next Steps

Implementation is complete and ready. When a real prospect demands deeper research capability, proceed with the hardened version: Planner → Research → Critic → Revise → Storage chain, adding `EmbeddingService` + `BrainDocument(doc_type="diagnostic")` write and widening the schema to full `DiagnosticIntakeOutput` / `WorkflowCandidate` as described in `planning/diagnostic-alignment/notes.md` §2.
