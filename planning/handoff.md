---
type: Handoff
created: 2026-06-21
---

# Handoff — CLAUDE_CODE_SDK shipped; session-provider is next but blocked on bastion

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why
We just shipped **`feature-claude-code-sdk-provider`** — a new `ModelProvider.CLAUDE_CODE_SDK`
that drives an `AgentNode`'s LLM call through the official `claude-agent-sdk` (`query()`) so
workflow steps bill to Brandon's Claude Code **subscription** instead of metered API credits,
while keeping the uniform config-injected model-selection model (CLAUDE.md Rule 7). It deliberately
ships a reusable seam — a `ClaudeCodeBackend` protocol + a shared `ClaudeCodeModel` (pydantic-ai
0.1.5 `Model`) — that the **sibling** feature `feature-claude-code-session-provider`
(`CLAUDE_CODE_SESSION`, routes through the `bastion ask` CLI) will reuse without modification. The
cross-repo contract for both modes lives in the brain at
`agentic-portfolio/docs/integrations/claude-code-llm-provider.md`. This session ran the whole spec
through `/sdlc-block` to a clean PASS; the next unit of work is the session-provider sibling, but it
is **blocked** (see Open questions).

## Completed this session
- **Ran `/sdlc-block feature-claude-code-sdk-provider` to a full PASS** — all 7 tasks merged across
  5 dependency waves, each on the first attempt, zero escalations/skips (block report:
  `planning/feature-claude-code-sdk-provider/sdlc/reports/block-workflow.md`).
- **Shipped the feature:** new package `app/services/claude_code/` (`backend.py` =
  `ClaudeCodeBackend` protocol + `ClaudeResult`; `sdk_backend.py` = `ClaudeAgentSdkBackend`;
  `model.py` = `ClaudeCodeModel`); `ModelProvider.CLAUDE_CODE_SDK` + `__get_claude_code_sdk_model`
  arm wired into `app/core/nodes/agent.py`; `claude-agent-sdk` added to `pyproject.toml`; four
  `CLAUDE_CODE_*` vars added to `app/.env.example`; docs updated (`docs/configuration.md` §3,
  `docs/api-reference.md`).
- **Verified independently of the workflow's self-report:** ruff clean, pylint **10.00/10** on the
  new code, **335 tests pass** (was 295 → +40, of which 33 are `claude_code`-specific), tree clean,
  all `trees/` worktrees torn down.
- **Pre-flight fix before the run:** `.env.local` (held a real `ANTHROPIC_API_KEY`) was untracked
  and not ignored — added `.env.local` + `.env.*.local` to `.gitignore` and committed the two spec
  dirs + vendored `docs/claude-agent-sdk.md` (commit `0f7396b`). The key is now out of the tree.
- Per-task `/log-work` + `/commit` already updated `log.md` and `planning/status.md` during the run
  (status `Last updated` line now reads the feature is DONE).

## Remaining work
- **Operator-run gates on `feature-claude-code-sdk-provider` (the only loose ends on this feature) —
  must be done on a host with the `claude` CLI logged into the subscription:**
  1. Confirm the env-scrub actually forces subscription auth. `sdk_backend.py:59` sets
     `env = {"ANTHROPIC_API_KEY": "", "ANTHROPIC_AUTH_TOKEN": ""}` per spec, but whether blanking
     them yields subscription billing (vs. erroring/falling back) was never verified — the headless
     pipeline can't.
  2. Run Task 7's manual e2e: an `AgentNode` with `CLAUDE_CODE_SDK` + an `OutputType` returns
     validated structured output, `NodeRun.usage` carries real tokens, and the Anthropic console
     shows **no** key-billed spend. Record both findings in the spec's `## Notes` (still placeholder).
- **Then: `feature-claude-code-session-provider`** (the next planned feature) — but it is BLOCKED
  (see below). Its spec is `planning/feature-claude-code-session-provider/tasks.md` (complexity:
  medium). When unblocked, run it the same way: `/sdlc-block feature-claude-code-session-provider`.
- **Non-blocking, anytime:** Project A follow-ups in `planning/phase1-projectA/follow-ups.md`.

## Open questions / choices
- **`feature-claude-code-session-provider` is BLOCKED on its dependency #2.** Its spec lists two
  blocking deps:
  - #1 — *`feature-claude-code-sdk-provider` merged* → **now TRUE** (shipped this session).
  - #2 — *bastion Block G (`bastion ask` v0.1.0) shipped and the `bastion` binary on the host PATH*,
    calling exactly the flags pinned in the brain doc §2 → **status unknown / likely not yet**.
    Verify this before starting the session feature; do **not** kick off `/sdlc-block` on it until
    dep #2 is confirmed true, or the implement tasks will fail against a missing CLI.
- Otherwise clear: the SDK feature itself passed all automated gates; only the subscription-host
  verification (above) is outstanding, and that's an operator step, not an agent task.

## Context the next agent needs
- **The reusable seam is the whole point:** `ClaudeCodeModel` + `ClaudeCodeBackend` + `ClaudeResult`
  in `app/services/claude_code/` are imported unchanged by the session feature, which only *appends*
  a second backend + a second `ModelProvider` enum value + a second factory arm in
  `app/core/nodes/agent.py`. Don't refactor that package without checking the session spec.
- **Pinned API gotcha:** the repo runs **pydantic-ai 0.1.5** (verified). `Model.request()` returns a
  2-tuple `(ModelResponse, Usage)`, structured output goes via `ToolCallPart` (not a profile mode),
  and there is no `pydantic_ai.profiles` module. The session feature's `Model` work inherits this.
- **venv gotcha:** a stale `VIRTUAL_ENV=.../orchestration/.venv` is exported in this shell and does
  not match the project venv. Run `uv run python -m <tool>` **without** `--active` so uv selects the
  project `.venv` (per CLAUDE.md). With `--active` it picks the wrong env.
- The cross-repo contract (command surface for `bastion ask`, the env-scrub billing note) is owned by
  the brain: `agentic-portfolio/docs/integrations/claude-code-llm-provider.md`.

## First command after `/prime`
`git -C ../bastion log --oneline -5 && which bastion` — confirm whether bastion Block G
(`bastion ask`) is shipped and on PATH (session-provider dep #2). If yes →
`/sdlc-block feature-claude-code-session-provider`. If no → that feature stays blocked; instead do
the operator-run subscription-host gates on the SDK feature, or pick up Project A follow-ups.
