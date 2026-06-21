# Implementation Report — feature-claude-code-sdk-provider-task4

**Date:** 2026-06-21
**Plan:** planning/feature-claude-code-sdk-provider/tasks.md
**Scope:** Task 4

## What Was Built or Changed
- `app/services/claude_code/model.py` — new `ClaudeCodeModel(pydantic_ai.models.Model)` implementing the
  pinned pydantic-ai 0.1.5 abstract surface. Constructed with a `ClaudeCodeBackend` + `model_name`.
  - Properties `model_name` (configured name), `system` (`"claude-code"`), `base_url` (`None`).
  - `customize_request_parameters` returns params unchanged; `_get_instructions` returns `None`.
  - `request(...)` returns the 0.1.5 **2-tuple** `(ModelResponse, Usage)`. It flattens messages into a
    single user prompt + system text (reads `SystemPromptPart` / `UserPromptPart`), then: when
    `model_request_parameters.output_tools` is non-empty it reads the first output tool's
    `parameters_json_schema`, calls `backend.run(..., schema=<that schema>)`, and returns a
    `ToolCallPart(tool_name=output_tool.name, args=<result.structured or json.loads(result.text)>)`;
    otherwise it calls with `schema=None` and returns a `TextPart(content=result.text or "")`. Builds
    `Usage(requests=1, request_tokens=..., response_tokens=...)` from the backend result.
  - `request_stream` raises `NotImplementedError` (streaming is documented future work).
- `app/services/claude_code/__init__.py` — re-exports `ClaudeCodeModel` (added to `__all__`).
- `tests/core/test_claude_code_model.py` — new hermetic unit tests driving `request` with a fake backend
  for both output paths.

## Files Created or Modified
| File | Action |
|---|---|
| app/services/claude_code/model.py | created |
| app/services/claude_code/__init__.py | modified |
| tests/core/test_claude_code_model.py | created |

## Validation Output
**Commands run:**
```
cd app && uv run python -c "import claude_agent_sdk"
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest
```
**Result:** PASSED

(claude_agent_sdk imports cleanly; ruff "All checks passed!"; pylint 10.00/10; pytest 320 passed —
includes the 10 new `test_claude_code_model.py` cases.)

## Decisions and Trade-offs
- The installed pydantic-ai 0.1.5 marks only `model_name`, `request`, and `system` as abstract, but the
  spec asks for the full surface — `base_url`, `customize_request_parameters`, `_get_instructions`, and
  `request_stream` are all implemented as the spec directs so the model is forward-compatible and the
  session-mode feature can reuse it unchanged.
- `request_stream` is an async generator (a trailing unreachable `yield` keeps it an async generator for
  the ABC) that raises immediately on iteration. The unreachable `yield` carries an inline
  `# pylint: disable=unreachable` so the deep-lint stays at 10.00/10.
- No `pytest-asyncio` / `anyio` pytest plugin is configured in this repo, so the async `request` path is
  exercised via `asyncio.run(...)` inside sync test functions rather than async test markers.
- Worktree note: this is a 58%-sparse checkout. `app/services/claude_code/` (Task 2's backend) was already
  materialized; I added `tests/` to the sparse-checkout set so the suite (and the new test) run against
  the real test infrastructure. No test files were modified beyond the new one.
- `__init__.py` is nominally Task 2's file, but its own docstring states `ClaudeCodeModel` is added "as
  later tasks land" — exporting it here is the intended seam and is required for the Task 5 provider
  factory to import `from services.claude_code import ClaudeCodeModel`.

## Follow-up Work
- Streaming (`request_stream`) is intentionally unimplemented — a documented future item.
- Task 5 wires `ModelProvider.CLAUDE_CODE_SDK` into the `AgentNode` provider factory using this model.

## git diff --stat
```
 app/services/claude_code/__init__.py | 3 ++-
 1 file changed, 2 insertions(+), 1 deletion(-)
```
(new files `app/services/claude_code/model.py` and `tests/core/test_claude_code_model.py` are untracked
until staged, so they do not appear in `git diff --stat`.)
