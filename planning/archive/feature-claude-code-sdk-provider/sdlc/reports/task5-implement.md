# Implementation Report — feature-claude-code-sdk-provider-task5

**Date:** 2026-06-21
**Plan:** planning/feature-claude-code-sdk-provider/tasks.md
**Scope:** Task 5 — Wire `CLAUDE_CODE_SDK` into the provider factory

## What Was Built or Changed
- `app/core/nodes/agent.py`:
  - Added `CLAUDE_CODE_SDK = "claude_code_sdk"` to the `ModelProvider` enum.
  - Added a `case provider.CLAUDE_CODE_SDK.value:` arm in `__get_model_instance`
    dispatching to a new `__get_claude_code_sdk_model`.
  - Added `__get_claude_code_sdk_model(self, model_name)` constructing
    `ClaudeCodeModel(backend=ClaudeAgentSdkBackend(), model_name=model_name)`.
  - Widened `AgentConfig.model_name` typing with `| str` so Claude aliases
    (`"opus"`, `"claude-opus-4-8"`) are permitted.
  - Imported `ClaudeAgentSdkBackend`, `ClaudeCodeModel` from `services.claude_code`.
- `app/services/claude_code/__init__.py`: re-export `ClaudeAgentSdkBackend`
  (the package now exports the full SDK surface, per Step 2's "after later tasks land").
- `tests/core/test_claude_code_provider_routing.py` (new): provider-routing tests
  following the `StubAgentNode` pattern from `tests/core/test_nodes_usage.py`.

## Files Created or Modified
| File | Action |
|---|---|
| app/core/nodes/agent.py | modified |
| app/services/claude_code/__init__.py | modified |
| tests/core/test_claude_code_provider_routing.py | created |

## Validation Output
**Commands run:**
```
cd app && uv run python -c "import claude_agent_sdk"   # IMPORT_OK
uv run python -m ruff check app/                        # All checks passed
uv run python -m pylint app/                            # 10.00/10
uv run python -m pytest                                 # 335 passed
```
**Result:** PASSED

## Decisions and Trade-offs
- The end-to-end routing test (`test_run_agent_recorded_stamps_real_usage_via_fake_backend`)
  drives the *real* pydantic-ai `Agent` (not a `MagicMock`), swapping only the SDK
  backend for a fake so no `claude` CLI is spawned. pydantic-ai 0.1.5 wraps even a
  default `str` output through an output tool, so the node is given a concrete
  `output_type` (a small `BaseModel`) and the fake backend returns `structured=...`;
  this exercises the structured `ToolCallPart` path through to a validated `OutputType`
  and confirms `run_agent_recorded` stamps real `{input_tokens, output_tokens, model}`.
- Kept `__get_claude_code_sdk_model` parameterless on construction — `ClaudeAgentSdkBackend`
  reads `CLAUDE_CODE_*` env at call time (Task 3 design), so the factory stays config-free
  per CLAUDE.md Rule 7.

## Follow-up Work
- None for Task 5. Docs (Task 6) and the manual subscription-billed e2e (Task 7) remain
  in their own tasks.

## git diff --stat
```
 app/core/nodes/agent.py              | 17 ++++++++++++++++-
 app/services/claude_code/__init__.py | 13 ++++++++++---
 2 files changed, 26 insertions(+), 4 deletions(-)
```
(plus the new untracked test `tests/core/test_claude_code_provider_routing.py`)
