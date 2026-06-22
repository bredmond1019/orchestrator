---
type: ImplementationReport
title: Implementation Report — phase1-projectB
description: Thin-cut research agent — CompanyResearchNode, ResearchAgentWorkflow, schemas, prompt, and tests.
---

# Implementation Report — phase1-projectB

**Date:** 2026-06-22
**Plan:** planning/phase1-projectB/tasks.md
**Scope:** Full spec

## What Was Built or Changed

- `app/schemas/research_agent_schema.py` — `ResearchAgentEventSchema` (inbound event: `company_name`, `artifact_id`, `timestamp`) and `ResearchBriefOutput` (brief output: `company_name`, `what_they_do`, `likely_time_sinks`, `automation_hypothesis`). Shaped toward `DiagnosticIntakeOutput` per notes.md §2; deferred hardened fields noted in docstring.
- `app/prompts/research_agent_brief.j2` — System prompt for the tool-use loop. Instructs the model to use `web_search` to gather info, then call `submit_research_brief` exactly once with all fields. Loaded via `PromptManager`; no prompt text in Python.
- `app/workflows/research_agent_workflow_nodes/company_research_node.py` — `CompanyResearchNode(ToolUseNode)` subclass. Exposes two Anthropic tool definitions (`web_search` + `submit_research_brief`), builds initial messages from the `.j2` prompt, dispatches `web_search` to `SearchService` (Tavily), validates `submit_research_brief` input into `ResearchBriefOutput` and stores under `brief` key, relies on inherited `max_iterations` guard. No edits to base class.
- `app/workflows/research_agent_workflow_nodes/__init__.py` — Scaffold empty `__init__` (generated, no changes needed).
- `app/workflows/research_agent_workflow.py` — `ResearchAgentWorkflow(Workflow)` with single-node `WorkflowSchema`, module docstring on line 1, `initial_node.py` stub deleted.
- `app/workflows/workflow_registry.py` — Added `RESEARCH_AGENT = ResearchAgentWorkflow` to `WorkflowRegistry`.
- `tests/workflows/test_company_research_node.py` — Unit tests: system prompt sourced from `.j2`, loop terminates on `end_turn`, tool result injection, `web_search` dispatch to `SearchService`, search result formatting, `submit_research_brief` stores valid `ResearchBriefOutput`, ack string returned, `max_iterations` bounds the loop without raising.
- `tests/workflows/test_research_agent_workflow.py` — Workflow tests: registration, schema wiring, event schema validation, `WorkflowValidator` passes, `initial_node.py` gone, single terminal node, workflow description filled, diagnostic-alignment test (mocked `submit_research_brief` yields populated `ResearchBriefOutput` with non-empty `likely_time_sinks`).

## Files Created or Modified

| File | Action |
|---|---|
| `app/schemas/research_agent_schema.py` | created |
| `app/prompts/research_agent_brief.j2` | created |
| `app/workflows/research_agent_workflow_nodes/company_research_node.py` | created |
| `app/workflows/research_agent_workflow_nodes/__init__.py` | created (scaffold) |
| `app/workflows/research_agent_workflow.py` | created (replaced scaffold) |
| `app/workflows/workflow_registry.py` | modified |
| `tests/workflows/test_company_research_node.py` | created |
| `tests/workflows/test_research_agent_workflow.py` | created |

## Validation Output

**Commands run:**
```
uv run python -m ruff check app/
uv run python -m pylint app/
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
uv run python -m pytest
```

**Results:**
```
ruff: All checks passed!

pylint: Your code has been rated at 9.99/10
(one pre-existing line-length violation in app/database/brain_document.py; no new violations)

main import: OK
worker.config import: OK

pytest: 417 passed, 7 skipped, 7 warnings in 1.82s
(19 new tests added; no collection-count drop; all green)
```

Status: PASSED

## Decisions and Trade-offs

- **`brief` key vs `output` key for structured result storage:** The base `ToolUseNode.process` unconditionally calls `task_context.update_node(self.node_name, output=self._extract_text(last_response))` after the loop, which would overwrite an `output` key set during `handle_tool_call`. The structured brief is stored under `brief` so the parent's text-extraction write (which goes to `output`) does not clobber it. Both keys coexist in the node's stored dict. This is clean and avoids any modification to the base class (a standing rule: do not edit `tool_use.py`).
- **Event field access (`getattr` vs `.get()`):** When a workflow runs normally, `Workflow.run()` parses the raw dict event into the Pydantic model, so `task_context.event` is a `ResearchAgentEventSchema` instance accessed via attributes. In unit tests that construct `TaskContext(event={...})` directly, it is a dict. `_build_initial_messages` handles both with `isinstance(event, dict)`.
- **No Celery, no storage, no embedding:** Spec is explicit that this is the thin cut. All hardened-version features (Planner/Research/Critic/Revise/Storage nodes, `EmbeddingService`, `BrainDocument`) are deferred until a real prospect demands more depth.
- **`PromptManager.get_prompt` in `_build_initial_messages`:** The spec says `_build_initial_messages` is the only place the prompt text is sourced. The system prompt is embedded as context in the user message (the Anthropic API's tool-use loop does not take a separate `system` argument in the same call structure used here) — the `.j2` is still the canonical source, loaded at call time.

## Follow-up Work

- Hardened Project B: Planner → Research → Critic → Revise → Storage chain, once a real prospect demands it. Adds `EmbeddingService` + `BrainDocument(doc_type="diagnostic")` write and widens schema to full `DiagnosticIntakeOutput` / `WorkflowCandidate` (notes.md §2).
- Storage/embedding deferred by spec — intentionally not in scope here.

## git diff --stat

```
 app/prompts/research_agent_brief.j2                                     | 26 +++++++++++
 app/schemas/research_agent_schema.py                                     | 51 +++++++++++++++++++++
 app/workflows/research_agent_workflow.py                                 | 43 +++++++++++++++++
 app/workflows/research_agent_workflow_nodes/__init__.py                  |  1 +
 app/workflows/research_agent_workflow_nodes/company_research_node.py    | 121 +++++++++++++++++++++++++++++++++++++++++++++++++++
 app/workflows/workflow_registry.py                                       |  4 +-
 tests/workflows/test_company_research_node.py                           | 270 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 tests/workflows/test_research_agent_workflow.py                         | 148 +++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++
 8 files changed, 663 insertions(+), 1 deletion(-)
```
