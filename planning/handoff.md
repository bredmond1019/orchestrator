---
type: Handoff
created: 2026-07-02
---

# Handoff — SDLCFlowWorkflow node-tier refactor (shipped)

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why
We reviewed every node in `SDLCFlowWorkflow` against `planning/archive/sdlc-workflow-architecture/nodes-design.md` to find nodes that were using an LLM but didn't need one, and to close a design gap (no task-generation fallback). Brandon's four calls drove the work: (1) all AI nodes ride the `CLAUDE_CODE_SDK` seam; (2) `WrapUpNode` becomes deterministic; (3) `TriageTaskNode` defaults to deterministic with an opt-in LLM path (good future home for an OSS model); (4) add a `GenerateTasksNode` on Opus. All four are implemented, tested, and committed at `1fc5768`.

## Completed this session
- **Uniform provider:** `consolidated_review_node.py` + `patch_docs_node.py` moved from `ANTHROPIC`/`claude-sonnet-5` → `CLAUDE_CODE_SDK`/`sonnet`. Every LLM node now uses the SDK seam.
- **`WrapUpNode` → deterministic `Node`:** renders `log_entry`/`report`/`status_suggestion` from three new Jinja templates (`app/prompts/sdlc_wrap_up_{log,report,status}.j2`) over run telemetry; deleted the old `sdlc_wrap_up.j2` system prompt.
- **`TriageTaskNode` deterministic-default:** new `llm_triage: bool = False` on `SDLCFlowEventSchema` (`app/schemas/sdlc_schema.py`); failing-under-budget → `RETRYABLE` with no model call unless `llm_triage=True`.
- **New `GenerateTasksNode` (Opus) + `SpecExistsRouterNode`:** `app/workflows/sdlc_flow_workflow_nodes/generate_tasks_node.py` + `spec_exists_router_node.py` + prompt `sdlc_generate_tasks.j2`. Router sits after `SetupWorktreeNode`: routes to `LoadTaskStateNode` when `tasks.json`/state exists, else to `GenerateTasksNode`, which writes `tasks.md` + `tasks.json` then hands off. Wired in `sdlc_flow_workflow.py` (now 16 nodes).
- **Tests:** deterministic-triage, template WrapUp, GenerateTasks + SpecExistsRouter units, and a **full-DAG integration test for the generate-spec path** (`test_sdlc_flow_workflow.py::TestSDLCFlowWorkflowGeneratesSpec`). Gate: **917 passed / 8 skipped**, `ruff check app/` clean, `pylint app/` 10.00/10.

## Remaining work
- **Optional:** update `planning/archive/sdlc-workflow-architecture/nodes-design.md` to record the as-built decisions (it still shows the old ANTHROPIC tiering, no `GenerateTasksNode`/`SpecExistsRouterNode`, and the LLM-always triage). It was the source of the discrepancy that kicked off this session.
- **`SDLCBlockWorkflow`** (wave fan-out via `ParallelNode`) remains the standing OR.Z follow-on spec whenever prioritized.
- **Wave 0 `OR.H`** (Ollama local-embedding swap + `--rebuild`) is still the demand-first next block, gated on an at-home Mini session.

## Durable State Updates
- Added `carryover[]` entry `mev-emit-state-bug` (kind `env`) to `planning/state.json`: do not run `mev emit-state --write` until mev's emit-state bug is fixed; state.json edits are hand-made and will need a manual emit-state sync afterward.

## Open questions / choices
None — clear to proceed. The four refactor decisions are settled and shipped.

## Context the next agent needs
- **`mev emit-state` is intentionally NOT run this session** (its bug is being fixed) — see the `mev-emit-state-bug` carryover slug. Keep skipping the emit-state step in `/log-work` / `/handoff` until told otherwise.
- The prior `handoff.md` (Project E ParallelNode) was stale; this replaces it.

## First command after `/prime`
`/document planning/archive/sdlc-workflow-architecture/nodes-design.md` (or just resume with `OR.H` if docs aren't a priority)
