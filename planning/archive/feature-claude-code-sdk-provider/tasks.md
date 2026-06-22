---
type: TaskSpec
title: Feature — Claude Code SDK LLM provider (CLAUDE_CODE_SDK)
description: Add a CLAUDE_CODE_SDK model provider so an AgentNode can run on Claude Code via the official claude-agent-sdk (subscription-billed), with native structured output and real token usage — plus the shared ClaudeCodeModel + backend protocol that the later CLAUDE_CODE_SESSION (bastion) mode reuses.
---

# Feature: Claude Code SDK LLM provider (`CLAUDE_CODE_SDK`)

## Metadata
prompt: `Add Claude Code (subscription) as an LLM option for AgentNode via the official claude-agent-sdk, headless mode.`
task_type: feature
complexity: complex

## Goal
A node can set `model_provider=ModelProvider.CLAUDE_CODE_SDK` and have its LLM call execute through the
official `claude-agent-sdk` (`query()`), billed to the Claude Code **subscription** (not API credits),
returning structured output and real token usage through the existing `AgentNode` / `run_agent_recorded`
machinery — no changes required to node-authoring ergonomics.

## Problem Statement
`AgentNode` LLM calls go through pydantic-ai providers that bill the metered Anthropic API. Brandon runs
Claude Code on a subscription. We want a provider that drives Claude Code so workflow LLM steps run on the
subscription, while keeping the uniform `ModelProvider` selection model (CLAUDE.md Rule 7 — model choice
is injected via config, never branched inside node logic).

## Solution Approach
Add `ModelProvider.CLAUDE_CODE_SDK` and a custom pydantic-ai `Model` (`ClaudeCodeModel`) that delegates to
a pluggable **backend** (`ClaudeCodeBackend` protocol). This feature ships the backend protocol, the shared
`ClaudeCodeModel`, and the SDK backend (`ClaudeAgentSdkBackend`, using `claude_agent_sdk.query()`). The
later `feature-claude-code-session-provider` reuses the protocol + model and only adds a second backend +
enum value. The cross-repo design + the contract for the sibling mode are tracked in the brain:
`agentic-portfolio/docs/integrations/claude-code-llm-provider.md`.

## CRITICAL — pinned pydantic-ai 0.1.5 API (verified by introspection 2026-06-21)
The custom `Model` must match the **installed** version, which is older than current docs:
- `Model.request(self, messages, model_settings, model_request_parameters) -> tuple[ModelResponse, Usage]`
  — it returns a **tuple** `(response, usage)`, not a bare `ModelResponse`.
- Also abstract: `request_stream`, `customize_request_parameters`, `_get_instructions`; abstract
  properties `base_url`, `model_name`, `system`.
- `ModelResponse(parts: list[ModelResponsePart], model_name=None, timestamp=<factory>, kind='response')`.
- `TextPart(content, part_kind)`. For **structured output** use `ToolCallPart` (introspect
  `pydantic_ai.messages` for its exact fields — expected `tool_name` + `args`).
- `Usage(requests=0, request_tokens=None, response_tokens=None, total_tokens=None, details=None)`
  — map tokens to `request_tokens` / `response_tokens`.
- `ModelRequestParameters` fields: `function_tools`, `allow_text_output`, `output_tools`. When the node
  has an `output_type`, pydantic-ai populates `output_tools` (each carries a JSON-schema for the output)
  and sets `allow_text_output=False`; the model is expected to return a `ToolCallPart` invoking that output
  tool. There is **no `pydantic_ai.profiles` module** — do **not** rely on a `ModelProfile` prompted-output
  mode. Handle structure in-Model (see Task 4).

## Relevant Files
- `app/core/nodes/agent.py` — `ModelProvider` enum, `AgentConfig`, `__get_model_instance` factory switch,
  `run_agent_recorded` (consumes the tuple from `agent.run_sync` → `result.usage()`); the integration point.
- `app/core/nodes/base.py` / `app/core/task.py` — `Node`, `TaskContext`, `NodeRun.usage` shape (reference).
- `app/workflows/content_pipeline_workflow_nodes/blog_writer_node.py` — example `AgentNode` subclass /
  `get_agent_config()` pattern (reference; do not modify).
- `tests/core/test_nodes_usage.py`, `tests/core/test_nodes_tool_use.py` — mocking patterns to follow.
- `docs/configuration.md`, `docs/api-reference.md`, `app/.env.example` — config surface to extend.
- `docs/claude-agent-sdk.md` — the vendored SDK reference (`ResultMessage` at line ~1511: `result`,
  `structured_output`, `usage`, `total_cost_usd`, `session_id`, `subtype`, `is_error`).
- `agentic-portfolio/docs/integrations/claude-code-llm-provider.md` — cross-repo coordination + contract.

### New Files
- `app/services/claude_code/__init__.py` — package exports.
- `app/services/claude_code/backend.py` — `ClaudeCodeBackend` protocol + `ClaudeResult` dataclass.
- `app/services/claude_code/sdk_backend.py` — `ClaudeAgentSdkBackend`.
- `app/services/claude_code/model.py` — `ClaudeCodeModel(pydantic_ai.models.Model)`.
- `tests/services/test_claude_code_sdk_backend.py`, `tests/core/test_claude_code_model.py`,
  `tests/core/test_claude_code_provider_routing.py`.

## Standing rules to respect (CLAUDE.md)
- Rule 5 — Python stays Python (the SDK is a Python package; fine). Rule 7 — no deployment logic in nodes
  (mode is config-selected; all specifics live in this service + the Model). Rule 2 — prompts stay in `.j2`
  (unchanged). Every change ships with tests. 3.10+ type syntax, module docstring on line 1,
  `raise ... from e`, no f-strings in logging, no param named `id`. Do not touch `customer_care*` or the
  reference `content_pipeline` nodes.

## Step-by-Step Tasks

### 1. Add the dependency + config surface
- **Files owned:** `pyproject.toml`, `app/.env.example`.
- Add `claude-agent-sdk` to `[project].dependencies`; run `uv sync`. (The SDK shells out to the `claude`
  CLI, which must be present and logged into the subscription on the host.)
- `app/.env.example`: add a `# Claude Code — SDK mode (subscription)` block:
  `CLAUDE_CODE_BIN=` (optional explicit `claude` path → SDK `cli_path`),
  `CLAUDE_CODE_CWD=` (optional working dir → SDK `cwd`),
  `CLAUDE_CODE_PERMISSION_MODE=bypassPermissions`,
  `CLAUDE_CODE_SDK_TIMEOUT_SECONDS=180`.
- Verify: `cd app && uv run python -c "import claude_agent_sdk"` succeeds.

### 2. Backend protocol + result type
- **Files owned:** `app/services/claude_code/__init__.py`, `app/services/claude_code/backend.py`.
- `backend.py`: define `ClaudeResult` (dataclass): `text: str | None`, `structured: Any | None`,
  `input_tokens: int | None`, `output_tokens: int | None`, `cost_usd: float | None`, `model: str`,
  `session_id: str | None`. Define `ClaudeCodeBackend` (typing.Protocol) with one async method:
  `async def run(self, prompt: str, *, system: str | None, model: str, schema: dict | None) -> ClaudeResult`.
  (`schema` is a JSON schema for structured output, or `None` for free text.)
- `__init__.py`: re-export `ClaudeCodeBackend`, `ClaudeResult` (and, after later tasks land,
  `ClaudeAgentSdkBackend`, `ClaudeCodeModel`).
- Tests: a tiny `tests/services/test_claude_code_backend.py` asserting `ClaudeResult` construction/defaults
  (keeps the contract pinned).

### 3. SDK backend (`ClaudeAgentSdkBackend`)
- **Files owned:** `app/services/claude_code/sdk_backend.py`, `tests/services/test_claude_code_sdk_backend.py`.
- **dependsOn:** Task 2.
- Implement `ClaudeAgentSdkBackend(ClaudeCodeBackend)`:
  - Read config from env (Task 1 vars). Build `ClaudeAgentOptions(model=model, system_prompt=system,
    cwd=<CLAUDE_CODE_CWD or None>, permission_mode=<CLAUDE_CODE_PERMISSION_MODE>, cli_path=<CLAUDE_CODE_BIN
    or None>, output_format={"type": "json_schema", "schema": schema} if schema else None, env=<see below>)`.
  - **Subscription billing:** pass `env={"ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": ""}` so the
    spawned CLI uses subscription auth, not an inherited key. (Risk: confirm an empty value disables key
    auth on the installed SDK/CLI; if it does not, document that the SDK-mode host must not export the key
    — note the finding in `## Notes` and the brain contract doc §3.)
  - `async for msg in query(prompt=prompt, options=options)`: capture the terminal `ResultMessage`. On
    `subtype != "success"` or `is_error`, raise a descriptive `RuntimeError` (include `errors` /
    `api_error_status`) — `raise ... from` any caught exception. Map success → `ClaudeResult`:
    `result`→`text`, `structured_output`→`structured`, `usage["input_tokens"]`/`["output_tokens"]`→tokens,
    `total_cost_usd`→`cost_usd`, `session_id`→`session_id`, `model`=the requested model.
  - Apply `CLAUDE_CODE_SDK_TIMEOUT_SECONDS` (e.g. `asyncio.wait_for` around the drain).
- Tests (`monkeypatch` `claude_agent_sdk.query` with a fake **async generator** yielding a
  `ResultMessage`-shaped object): assert `ClaudeAgentOptions` is built with the right `model` /
  `system_prompt` / `output_format`; assert the passed `env` blanks `ANTHROPIC_API_KEY`; assert
  `result`/`structured_output`/`usage` map into `ClaudeResult`; assert a non-`success` subtype raises.

### 4. Shared `ClaudeCodeModel` (pydantic-ai Model, 0.1.5)
- **Files owned:** `app/services/claude_code/model.py`, `tests/core/test_claude_code_model.py`.
- **dependsOn:** Task 2.
- `ClaudeCodeModel(Model)` constructed with `backend: ClaudeCodeBackend` + `model_name: str`. Implement the
  full 0.1.5 abstract surface:
  - properties `model_name` (return the configured name), `system` (e.g. `"claude-code"`), `base_url`
    (return `None`).
  - `customize_request_parameters` → return the params unchanged; `_get_instructions` → may return `None`.
  - `request(self, messages, model_settings, model_request_parameters) -> tuple[ModelResponse, Usage]`:
    1. Flatten `messages` into a single user `prompt` string and extract any system text (read the parts of
       `ModelRequest`/`ModelResponse` messages — introspect `pydantic_ai.messages` for the part classes;
       follow how the request messages carry `SystemPromptPart` / `UserPromptPart`).
    2. Structured vs text: if `model_request_parameters.output_tools` is non-empty, take the first output
       tool, read its JSON schema (introspect the attribute — expected `parameters_json_schema`), call
       `await backend.run(prompt, system=..., model=self.model_name, schema=<that schema>)`, and return a
       `ModelResponse(parts=[ToolCallPart(tool_name=<output_tool.name>, args=<result.structured or json.loads(result.text)>)])`
       so pydantic-ai validates it into the node's `OutputType`. Otherwise call with `schema=None` and
       return `ModelResponse(parts=[TextPart(content=result.text or "")])`.
    3. Build `Usage(requests=1, request_tokens=result.input_tokens, response_tokens=result.output_tokens)`
       and return `(response, usage)`.
  - `request_stream`: out of scope — raise `NotImplementedError` with a clear message (streaming is a
    documented future item).
- Tests: drive `request` with a **fake backend** returning a known `ClaudeResult` for both paths —
  assert the text path yields a `TextPart` with the text and `Usage` tokens; assert the structured path
  (params with a synthetic `output_tools` entry) yields a `ToolCallPart` whose `args` match the structured
  payload; assert `request` returns a 2-tuple `(ModelResponse, Usage)`.

### 5. Wire `CLAUDE_CODE_SDK` into the provider factory
- **Files owned:** `app/core/nodes/agent.py`, `tests/core/test_claude_code_provider_routing.py`.
- **dependsOn:** Tasks 3, 4.
- `agent.py`: add `CLAUDE_CODE_SDK = "claude_code_sdk"` to `ModelProvider`; add a
  `case provider.CLAUDE_CODE_SDK.value:` arm in `__get_model_instance` → `self.__get_claude_code_sdk_model(model_name)`.
  Add `__get_claude_code_sdk_model(self, model_name)` that constructs `ClaudeAgentSdkBackend()` and returns
  `ClaudeCodeModel(backend=..., model_name=model_name)`. Keep `AgentConfig.model_name` typing permissive
  for Claude model aliases (e.g. `"opus"`, `"claude-opus-4-8"`).
- Tests (follow `tests/core/test_nodes_usage.py` `StubAgentNode` pattern): a stub node with
  `model_provider=ModelProvider.CLAUDE_CODE_SDK` builds a `ClaudeCodeModel` (backend monkeypatched/faked),
  and `run_agent_recorded` stamps `NodeRun.usage` `{input_tokens, output_tokens, model}` and stores
  `to_jsonable` output. Do not hit the network/CLI.

### 6. Docs
- **Files owned:** `docs/configuration.md`, `docs/api-reference.md`.
- `configuration.md`: document the `CLAUDE_CODE_*` SDK vars, prerequisites (`claude-agent-sdk` installed +
  `claude` CLI present + logged into the subscription), the `ANTHROPIC_API_KEY` scrub note, and that SDK
  mode reports real token usage + `total_cost_usd`.
- `api-reference.md`: add `ModelProvider.CLAUDE_CODE_SDK` and the `app/services/claude_code` package
  (`ClaudeCodeBackend`, `ClaudeResult`, `ClaudeAgentSdkBackend`, `ClaudeCodeModel`). Cross-link the brain
  coordination doc.

### 7. Validate
- Run the Validation Commands below and confirm all pass.
- **Manual e2e (host with Claude Code logged into the subscription):** a small script that builds an
  `AgentNode` (or calls the backend directly) with `CLAUDE_CODE_SDK` and an `OutputType` returns validated
  structured output; `NodeRun.usage` carries real tokens; the Anthropic API console shows **no** key-billed
  spend. Record the result in `## Notes`.

## Acceptance Criteria
- A node with `model_provider=ModelProvider.CLAUDE_CODE_SDK` runs its LLM call via `claude-agent-sdk`,
  returning text or validated structured output through the unchanged `AgentNode` path.
- `ClaudeCodeModel.request` matches pinned pydantic-ai 0.1.5: returns `(ModelResponse, Usage)`, emits a
  `ToolCallPart` for structured output (non-empty `output_tools`) and a `TextPart` otherwise.
- The SDK backend forces subscription auth by blanking `ANTHROPIC_API_KEY` in the spawned CLI env, and
  raises a descriptive error on a non-`success` `ResultMessage`.
- `run_agent_recorded` records real `{input_tokens, output_tokens, model}` for SDK mode.
- The backend protocol + `ClaudeCodeModel` are reusable by the later session-mode feature without change.
- New tests cover the backend (mapping + env scrub + error), the model (both output paths + tuple return),
  and provider routing; all gated checks pass and the pytest count increases.

## Validation Commands
```
cd app && uv run python -c "import claude_agent_sdk"
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest
```

## Notes
<filled in as work happens — record the env-scrub billing finding and the manual e2e result here>
