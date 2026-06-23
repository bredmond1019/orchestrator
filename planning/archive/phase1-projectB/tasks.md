---
type: TaskSpec
title: Task Spec — Phase 1, Project B (Research Agent, thin cut)
description: Thin-cut research agent — a single raw-SDK ToolUseNode that turns a company name into a structured, diagnostic-aligned research brief. No Celery, no critic, no storage.
---

# Task Spec — Phase 1, Project B (Research Agent — thin cut)

## Goal
A single `ToolUseNode` (raw `anthropic.Anthropic()` tool loop, written by hand) that takes a company name and outputs a structured brief — what they do, where they likely bleed time, one automation hypothesis — and stop there until a real prospect needs more.

## Context Pointers
- **Plan:** `planning/master-plan.md` → *Project B — Research Agent (thin first, then hardened)*. Build **only the thin cut** ("No Celery, no critic, no storage. ~50 lines"). The hardened version (Planner/Research/Critic/Revise/Storage nodes) is explicitly deferred until a prospect demands it — do not build it now.
- **Output-schema constraint:** `planning/diagnostic-alignment/notes.md` §2. Project B's eventual target is `DiagnosticIntakeOutput`/`WorkflowCandidate`, and storage calls `EmbeddingService` + writes a `BrainDocument`. The master plan defers storage/embedding to the hardened version, so the thin cut ships the **brief** only; its output schema is shaped toward the diagnostic (time-sinks + automation hypothesis) so the hardened version extends rather than replaces it. The embedding/`BrainDocument` write is **out of scope** here — note it as the hardened follow-up.
- **Existing seams to reuse (do not rebuild):**
  - `app/core/nodes/tool_use.py` `ToolUseNode` — abstract raw-SDK loop. Already has the `while iterations < max_iterations` guard, `end_turn`/`tool_use` handling, token capture, and `NodeRun` stamping. Subclass it; do **not** edit the base class.
  - `app/services/search_service.py` `SearchService` (Tavily) — the `web_search` tool backend. Returns typed `SearchResult`s.
  - `app/services/prompt_manager` `PromptManager` — load the loop's system prompt from a `.j2` template (D34 — never hardcode a prompt in Python).
- **Conventions to mirror:** `app/schemas/content_pipeline_schema.py` (event schema shape), `app/workflows/content_pipeline_workflow.py` (`WorkflowSchema` wiring), `app/workflows/workflow_registry.py` (registration), `tests/core/test_nodes_tool_use.py` (mocked-client loop tests).
- **Standing rules (CLAUDE.md):** every workflow ships with tests; no hardcoded prompts (`.j2` only); no deployment logic in nodes (model is already injected via `TOOL_USE_MODEL`); register the workflow; `customer_care` is frozen; raw SDK here — do **not** use `AgentNode`.

## Scaffold first
Run `uv run createworkflow` and name it `research_agent`. This creates `app/workflows/research_agent_workflow.py`, `app/workflows/research_agent_workflow_nodes/{__init__.py,initial_node.py}`, and `app/schemas/research_agent_schema.py` stubs. The tasks below fill these in; delete the generated `initial_node.py` stub once `CompanyResearchNode` exists.

## Step-by-Step Tasks

### 1. Event schema, brief output schema, and brief prompt
- **Owns:** `app/schemas/research_agent_schema.py`, `app/prompts/research_agent_brief.j2`.
- In `research_agent_schema.py`:
  - `ResearchAgentEventSchema(BaseModel)` — inbound event: `company_name: str` (required), plus `artifact_id: UUID` (default `uuid4`) and `timestamp: datetime` (default `now(UTC)`) mirroring `ContentPipelineEventSchema`.
  - `ResearchBriefOutput(BaseModel)` — the structured brief, shaped toward the diagnostic intake schema: `company_name: str`, `what_they_do: str`, `likely_time_sinks: list[str]` (where they bleed time — non-empty), `automation_hypothesis: str` (one concrete hypothesis). Add field descriptions. Keep it lean; this is the thin-cut deliverable, and the hardened version will widen it toward `WorkflowCandidate`.
- In `research_agent_brief.j2`: the system prompt for the loop — instruct the model to research the named company with the `web_search` tool, then emit the brief by calling the `submit_research_brief` tool exactly once with all fields populated. Use 3.10+ type syntax in the Python; module docstring on line 1.

### 2. `CompanyResearchNode` — the raw tool loop (+ unit tests)
- **Owns:** `app/workflows/research_agent_workflow_nodes/__init__.py`, `app/workflows/research_agent_workflow_nodes/company_research_node.py`, `tests/workflows/test_company_research_node.py`. **Depends on task 1.**
- Subclass `ToolUseNode` as `CompanyResearchNode`:
  - `tools` property exposes two Anthropic tool definitions: `web_search` (`{query}`) and `submit_research_brief` (`input_schema` = the `ResearchBriefOutput` fields).
  - `_build_initial_messages(...)` — load the system prompt via `PromptManager` from `research_agent_brief.j2` and seed the user message with the event's `company_name` (read from `task_context`). This is the only place the prompt text is sourced — no string literals.
  - `handle_tool_call(tool_name, tool_input, task_context)` — dispatch: `web_search` → `SearchService().search(query)` formatted to a compact string of titles+urls+snippets; `submit_research_brief` → validate `tool_input` into `ResearchBriefOutput`, store it on `task_context` (e.g. `update_node(..., output=brief.model_dump())`), return a short ack. Keep the inherited `max_iterations` guard intact.
  - The node must stay deployment-agnostic — no `if running_locally:`, model already injected via `TOOL_USE_MODEL`.
- Tests (mirror `tests/core/test_nodes_tool_use.py`; patch `anthropic.Anthropic` and `SearchService`): tool-results are injected back into `messages` and the loop continues; `web_search` dispatches to `SearchService`; a `submit_research_brief` call produces a valid `ResearchBriefOutput`; loop terminates on `end_turn` (exactly one create call); loop terminates at `max_iterations` on runaway `tool_use` responses (bounded call count + warning); the system prompt is sourced from the `.j2` (assert no inline prompt literal / PromptManager invoked).

### 3. `ResearchAgentWorkflow` + registry + workflow & diagnostic-alignment tests
- **Owns:** `app/workflows/research_agent_workflow.py`, `app/workflows/workflow_registry.py` (registry is edited **only** by this task — no other task touches it), `tests/workflows/test_research_agent_workflow.py`. **Depends on task 2.**
- `ResearchAgentWorkflow(Workflow)` — a single-node `WorkflowSchema`: `event_schema=ResearchAgentEventSchema`, `start=CompanyResearchNode`, one `NodeConfig(node=CompanyResearchNode, connections=[])`. Module docstring on line 1; delete the leftover `initial_node.py` stub.
- Register in `workflow_registry.py`: add `RESEARCH_AGENT = ResearchAgentWorkflow` to `WorkflowRegistry`.
- Tests: `WorkflowValidator` passes for the schema; `WorkflowRegistry.RESEARCH_AGENT` resolves to the class; **diagnostic-alignment test** — driving the node with a mocked client that returns a `submit_research_brief` tool call yields a valid `ResearchBriefOutput` whose `likely_time_sinks` is non-empty and all fields are populated (satisfies `notes.md` §2 test constraint, scaled to the thin-cut schema).

### 4. Validate
- Run the Validation Commands below and confirm all pass (ruff net-new clean, pylint 10.00/10, pytest green with no collection-count drop, imports clean).

## Acceptance Criteria
- `uv run createworkflow`-style layout exists: `research_agent_workflow.py`, `research_agent_workflow_nodes/company_research_node.py`, `schemas/research_agent_schema.py`; the generated `initial_node.py` stub is removed.
- `CompanyResearchNode` is a `ToolUseNode` subclass driving a raw `anthropic` loop with the inherited `max_iterations` guard; no edits to `app/core/nodes/tool_use.py`.
- The loop's system prompt lives in `app/prompts/research_agent_brief.j2` and is loaded via `PromptManager` — no prompt string literal in Python.
- Output validates to `ResearchBriefOutput` with non-empty `likely_time_sinks` and a populated `automation_hypothesis`; schema is shaped toward `DiagnosticIntakeOutput` per `notes.md` §2.
- `WorkflowRegistry.RESEARCH_AGENT` resolves and the workflow passes `WorkflowValidator`.
- Tests cover: tool-result injection, `web_search` dispatch, structured-brief capture, termination on `end_turn`, termination on `max_iterations`, and the diagnostic-alignment output check.
- No Celery wiring, no critic/revise loop, no storage/embedding/`BrainDocument` (those are the deferred hardened version).
- All gated checks in `planning/harness.json` pass; net-new ruff violations = 0; pytest collection count does not drop.

## Validation Commands
```
uv run python -m ruff check app/
uv run python -m pylint app/
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
uv run python -m pytest
```

## Notes
- Thin cut only — when a real prospect makes you want the Planner→Research→Critic→Revise→Storage chain, that's the hardened version; it also adds the `EmbeddingService` + `BrainDocument(doc_type="diagnostic", ...)` write from `notes.md` §2 and widens the schema to full `DiagnosticIntakeOutput`/`WorkflowCandidate`.
- Tool backend is Tavily via `SearchService` (built for agents). Tests mock it — no live `TAVILY_API_KEY`/`ANTHROPIC_API_KEY` needed for the suite.
