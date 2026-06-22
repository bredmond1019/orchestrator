# Implementation Report — incremental-execution-observability-task6

**Date:** 2026-06-20
**Plan:** planning/incremental-execution-observability/tasks.md
**Scope:** Task 6 — Per-node token + cost capture (Phase 2)

## What Was Built or Changed
- Added `AgentNode.run_agent_recorded(task_context, user_prompt)` to `app/core/nodes/agent.py`: runs the agent via `self.agent.run_sync` and stamps `{input_tokens, output_tokens, model}` onto the node's `NodeRun.usage` when a NodeRun exists. Uses a `getattr` fallback covering both newer pydantic-ai (`input_tokens`/`output_tokens`) and the pinned `>=0.1.5` line (`request_tokens`/`response_tokens`). The existing `__init__`/abstract signatures are untouched; subclasses calling `run_sync` directly simply record no usage.
- Updated `ToolUseNode.process` in `app/core/nodes/tool_use.py`: accumulates `input_tokens`/`output_tokens` across loop iterations from each Anthropic `response.usage`, then records `{input_tokens, output_tokens, model}` onto the node's `NodeRun.usage` before returning (only when a NodeRun is seeded).
- The `NodeRun.usage: dict | None` field already existed in `app/core/task.py` (landed by Task 1), so no edit was needed there per the breakdown.
- Added `tests/core/test_nodes_usage.py` covering both node bases plus the non-LLM case.
- No `customer_care` node was touched (Rule 3); no DB/session code added (Rule 7).

## Files Created or Modified
| File | Action |
|---|---|
| app/core/nodes/agent.py | modified |
| app/core/nodes/tool_use.py | modified |
| tests/core/test_nodes_usage.py | created |

## Validation Output
**Commands run:**
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run ruff check app/
uv run pylint app/
uv run pytest --collect-only -q   (220 collected)
uv run pytest                     (220 passed)
```
**Result:** PASSED

## Decisions and Trade-offs
- Kept the dual-name `getattr` fallback for token fields rather than hardcoding `request_tokens`/`response_tokens`. The installed pydantic-ai is 0.1.5 (uses `request_tokens`/`response_tokens`), but the dependency pin is `>=0.1.5`, so a future upgrade that renames to `input_tokens`/`output_tokens` stays covered. A dedicated test (`test_run_agent_recorded_old_token_names`) pins the older-name path via a `spec`-limited mock.
- `run_agent_recorded` is provided as an opt-in helper because the base class cannot intercept direct `self.agent.run_sync` calls subclasses make; this keeps `customer_care` frozen while giving new nodes a single recording path.
- Both recorders no-op when no `NodeRun` is seeded for the node, so usage capture never breaks callers that run a node outside the framework's envelope (verified by `test_no_node_run_seeded_does_not_raise`).

## Follow-up Work
None for Task 6. Wiring `run_agent_recorded` into actual new workflow nodes happens when such nodes are authored; the framework hook is in place.

## git diff --stat
```
 app/core/nodes/agent.py    | 28 ++++++++++++++++++++++++++++
 app/core/nodes/tool_use.py | 15 +++++++++++++++
 2 files changed, 43 insertions(+)
```
(plus new file tests/core/test_nodes_usage.py, untracked at diff-stat time)
