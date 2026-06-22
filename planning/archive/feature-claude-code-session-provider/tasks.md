---
type: TaskSpec
title: Feature — Claude Code session LLM provider (CLAUDE_CODE_SESSION) via bastion
description: Add a CLAUDE_CODE_SESSION model provider that runs an AgentNode LLM step on the live interactive Claude Code session by shelling out to `bastion ask`, so the turn is subscription-billed AND observable in `bastion sessions`. Reuses the ClaudeCodeModel + backend protocol from the SDK-mode feature.
---

# Feature: Claude Code session LLM provider (`CLAUDE_CODE_SESSION`)

## Metadata
prompt: `Add Claude Code subscription as an LLM option driven through the live bastion tmux session (observable), via `bastion ask`.`
task_type: feature
complexity: medium

## Goal
A node can set `model_provider=ModelProvider.CLAUDE_CODE_SESSION` and have its LLM call execute on the
**live interactive Claude Code session** by shelling out to `bastion ask` — subscription-billed and
**observable/attachable in `bastion sessions`** — returning output through the unchanged `AgentNode` path.

## Problem Statement
The SDK mode (`feature-claude-code-sdk-provider`) is clean but its CLI subprocess is ephemeral and not
visible in the operator shell. For long/observed work we want the turn to run in the real tmux session
that `bastion` manages, so it shows up in `bastion sessions` and can be attached mid-run.

## Solution Approach
Reuse the shared `ClaudeCodeModel` + `ClaudeCodeBackend` protocol (already built in the SDK feature) and
add a second backend, `BastionSessionBackend`, that drives one turn via the `bastion ask` command. A
file-based protocol: write the prompt (and JSON-schema instruction when structured) to a prompt file, run
`bastion ask` (which sends the trigger into the session and waits for the answer file), then read/parse the
answer file. Add the `CLAUDE_CODE_SESSION` enum value + factory arm.

## Dependencies (BLOCKING — do not start until both are true)
1. **`feature-claude-code-sdk-provider` is merged** — this feature imports `ClaudeCodeModel`,
   `ClaudeCodeBackend`, and `ClaudeResult` from `app/services/claude_code/`, and **appends** a second arm
   to `app/core/nodes/agent.py` / a block to `app/.env.example` already created there.
2. **bastion Block G (`bastion ask`) is shipped** and the `bastion` binary is on the host PATH. The
   command surface is pinned at `agentic-portfolio/docs/integrations/claude-code-llm-provider.md` §2
   (`bastion ask` v0.1.0). This feature must call exactly those flags.

## Relevant Files
- `app/services/claude_code/backend.py` — `ClaudeCodeBackend` protocol + `ClaudeResult` (reuse; do not change).
- `app/services/claude_code/model.py` — `ClaudeCodeModel` (reuse unchanged — it already calls
  `backend.run(prompt, system, model, schema)` and emits `ToolCallPart`/`TextPart`).
- `app/services/claude_code/__init__.py` — **append** the new backend export.
- `app/core/nodes/agent.py` — **append** `CLAUDE_CODE_SESSION` enum value + factory arm (the SDK feature
  already added `CLAUDE_CODE_SDK`; keep edits additive to avoid clobbering it).
- `tests/core/test_nodes_usage.py` / `test_claude_code_provider_routing.py` — routing-test pattern.
- `agentic-portfolio/docs/integrations/claude-code-llm-provider.md` — the `bastion ask` contract + matrix.

### New Files
- `app/services/claude_code/bastion_backend.py` — `BastionSessionBackend`.
- `tests/services/test_claude_code_bastion_backend.py`.

## Standing rules to respect (CLAUDE.md)
Rule 5 (Python invokes the external `bastion` binary — fine; no Rust in this repo). Rule 7 (config-selected
mode; no deployment branch in nodes). Every change ships with tests. 3.10+ types, module docstring on
line 1, `raise ... from e`, no f-strings in logging, no param named `id`. Do not touch `customer_care*` or
the reference `content_pipeline` nodes.

## Step-by-Step Tasks

### 1. Config surface for session mode
- **Files owned:** `app/.env.example` (append), `docs/configuration.md` (append).
- Append a `# Claude Code — session mode (bastion)` block to `.env.example`:
  `BASTION_BIN=bastion` (resolved via `shutil.which` fallback),
  `CLAUDE_CODE_TMUX_SESSION=orchestrator-claude`,
  `CLAUDE_CODE_WORKDIR=` (a Claude-**trusted** scratch dir used to create the session),
  `CLAUDE_CODE_IO_DIR=` (dir for prompt/answer files; defaults to `CLAUDE_CODE_WORKDIR`; must be on the
  same host as the session),
  `CLAUDE_CODE_SESSION_TIMEOUT_SECONDS=180`.
- `configuration.md`: document these + prerequisites (bastion built & on PATH; the tmux host logged into
  the Claude Code subscription; the workdir pre-trusted) and the **limitations** (session mode does not
  surface token usage → `usage` tokens are `None`; per-turn `model` is advisory only — the session's model
  is fixed at launch, not switched per call in v0.1.0).

### 2. `BastionSessionBackend`
- **Files owned:** `app/services/claude_code/bastion_backend.py`, `app/services/claude_code/__init__.py`
  (append export), `tests/services/test_claude_code_bastion_backend.py`.
- **dependsOn:** Task 1.
- Implement `BastionSessionBackend(ClaudeCodeBackend)` with the protocol's async `run`:
  - Resolve config from env (Task 1). Resolve `bastion` via `BASTION_BIN` → `shutil.which("bastion")`.
  - Generate a `uuid4` id. Build the **prompt file** `CLAUDE_CODE_IO_DIR/prompt-<id>.md` containing:
    the `system` text (if any) + the `prompt`, and — when `schema` is not `None` — an explicit instruction
    to "write ONLY a JSON object conforming to this schema: <json.dumps(schema)>" (so the answer file is
    parseable). Pick `out = CLAUDE_CODE_IO_DIR/out-<id>.json` when `schema` else `out-<id>.md`.
  - Run `bastion ask` via `subprocess.run([bastion, "ask", "--session", <session>, "--prompt-file", <p>,
    "--out", <o>, "--dir", <workdir>, "--timeout", str(<timeout>)], capture_output=True, text=True,
    timeout=<timeout + buffer>)`. Because the protocol method is `async`, run the blocking call in a thread
    executor (`asyncio.get_running_loop().run_in_executor`) so it doesn't block the loop.
  - On non-zero exit / missing `out` / `subprocess.TimeoutExpired`: raise a descriptive `RuntimeError`
    including the captured **stderr** (the `bastion ask` diagnostics) — `raise ... from e`.
  - On success: read `out`; if `schema`, `json.loads` → `structured` (leave `text` = raw string);
    else `text` = file contents, `structured=None`. Return `ClaudeResult(text=..., structured=...,
    input_tokens=None, output_tokens=None, cost_usd=None, model=model, session_id=None)`.
  - **Always** clean up the prompt/answer temp files (`finally`).
- `__init__.py`: append `BastionSessionBackend` to the exports.
- Tests (patch `subprocess.run` + use a tmp dir): assert the prompt file is written (and contains the
  schema instruction when `schema` is set); assert `bastion ask` is invoked with the exact contract flags;
  fake an answer file and assert JSON (structured) vs markdown (text) parsing; assert tokens/cost are
  `None`; assert non-zero exit, missing-out, and timeout each raise with stderr included; assert temp files
  are cleaned up.

### 3. Wire `CLAUDE_CODE_SESSION` into the provider factory
- **Files owned:** `app/core/nodes/agent.py` (append), `tests/core/test_claude_code_provider_routing.py`
  (extend).
- **dependsOn:** Task 2.
- `agent.py`: add `CLAUDE_CODE_SESSION = "claude_code_session"` to `ModelProvider`; add a
  `case provider.CLAUDE_CODE_SESSION.value:` arm → `self.__get_claude_code_session_model(model_name)`;
  add `__get_claude_code_session_model(self, model_name)` returning
  `ClaudeCodeModel(backend=BastionSessionBackend(), model_name=model_name)`. Keep these edits **additive**
  to the existing `CLAUDE_CODE_SDK` wiring.
- Tests: extend the routing test — a stub node with `model_provider=ModelProvider.CLAUDE_CODE_SESSION`
  builds a `ClaudeCodeModel` over a faked `BastionSessionBackend`; `run_agent_recorded` stores output and
  stamps `NodeRun.usage` with `model` set and token fields `None` (no network/CLI).

### 4. Docs
- **Files owned:** `docs/api-reference.md` (append).
- Add `ModelProvider.CLAUDE_CODE_SESSION` + `BastionSessionBackend` to the reference; note it depends on
  the external `bastion ask` (v0.1.0) and cross-link the brain coordination doc + the SDK-mode feature.

### 5. Validate
- Run the Validation Commands below and confirm all pass.
- **Manual e2e (host with bastion built + Claude Code logged into the subscription):** pre-trust the
  scratch dir; run a tiny workflow node with `CLAUDE_CODE_SESSION` (and an `OutputType`) → output is
  populated, `bastion sessions` shows the session as *running (claude)*, `NodeRun.usage` model set with
  `None` tokens, and the Anthropic API console shows **no** key-billed spend. Record in `## Notes`.

## Acceptance Criteria
- A node with `model_provider=ModelProvider.CLAUDE_CODE_SESSION` runs its LLM call by shelling out to
  `bastion ask` using the pinned v0.1.0 flags, returning text or validated structured output through the
  unchanged `AgentNode` / `ClaudeCodeModel` path.
- Structured requests write a JSON-schema instruction into the prompt file and parse the JSON answer file
  into `ClaudeResult.structured`; free-text requests return the markdown answer as `text`.
- `usage` token fields are `None` (documented limitation); `NodeRun.usage.model` is still recorded.
- Errors (non-zero exit / missing answer / timeout) raise descriptive errors carrying `bastion ask`'s
  stderr; temp files are always cleaned up.
- Reuses the SDK feature's `ClaudeCodeModel` + protocol unchanged; `agent.py` edits are additive to the
  existing `CLAUDE_CODE_SDK` wiring.
- New tests cover the backend (flags, prompt-file contents, parsing, error paths, cleanup) and routing;
  all gated checks pass and the pytest count increases.

## Validation Commands
```
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest
```

## Notes
<filled in as work happens — record the manual e2e result + the observed bastion session here>
