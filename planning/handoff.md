---
type: Handoff
created: 2026-06-22
---

# Handoff — CLAUDE_CODE_SESSION shipped; both Claude-Code provider modes now done

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why
This session shipped **`feature-claude-code-session-provider`** — `ModelProvider.CLAUDE_CODE_SESSION`,
the second of two ways to run an `AgentNode`'s LLM call on Brandon's Claude Code **subscription**
instead of metered API credits. Unlike the SDK mode shipped last session (`CLAUDE_CODE_SDK`, an
ephemeral headless `claude-agent-sdk` subprocess), session mode drives the **live interactive tmux
session that bastion manages** by shelling out to `bastion ask` — so the turn is subscription-billed
*and* observable/attachable in `bastion sessions`. It reuses the SDK feature's seam unchanged
(`ClaudeCodeModel` + `ClaudeCodeBackend` protocol + `ClaudeResult` in `app/services/claude_code/`) and
only *appends* a second backend, a second enum value, and a second factory arm. With this, **both
provider modes are complete** — the Claude-Code-as-LLM-provider pair is done. The cross-repo command
contract is owned by the brain at `agentic-portfolio/docs/integrations/claude-code-llm-provider.md` §2
(`bastion ask` v0.1.0); the orchestrator is the consumer pinned to that version.

## Completed this session
- **Ran `/sdlc-block feature-claude-code-session-provider` to a full PASS** — all 5 tasks merged in
  dependency order, auto-merge, zero escalations/skips (commits `9cda6d1`, `79c66ea`, `b850e6e`,
  `1494bc0`, `3cce087`; block report `planning/feature-claude-code-session-provider/sdlc/reports/block-workflow.md`).
- **Shipped the feature:** new `app/services/claude_code/bastion_backend.py` (`BastionSessionBackend`:
  resolves `BASTION_BIN` then `shutil.which("bastion")`, writes prompt file, invokes
  `bastion ask --session --prompt-file --out --dir --timeout` — the exact pinned v0.1.0 flags — parses
  the JSON/markdown answer file into `ClaudeResult`, cleans temp files in all paths, raises descriptive
  errors carrying bastion's stderr on non-zero exit / missing answer / timeout);
  `ModelProvider.CLAUDE_CODE_SESSION` enum + factory arm in `app/core/nodes/agent.py:42,142`; config
  block in `app/.env.example`; docs in `docs/configuration.md` + `docs/api-reference.md`.
- **Verified independently of the workflow's self-report:** ruff clean, pylint **10.00/10** on
  `bastion_backend.py` + `agent.py`, **353 tests pass** (335 → +18, of which 22 are session-mode), tree
  clean, all `trees/` worktrees torn down.
- **Checked bastion-side alignment:** bastion **Phase 5 Block G (`bastion ask` v0.1.0) is DONE** and the
  shipped CLI surface matches the brain contract §2 *verbatim*; our backend calls exactly those flags.
  bastion's whole Phase 5 session track + Phase 1 monitor are complete (265 tests); its next unit is
  unrelated (`phase2-blockA` — `bastion inspect`).
- **Two infra fixes to unblock the run (committed):**
  1. `~/.local/bin/bastion` symlink → `../bastion/target/release/bastion` (v0.1.0) puts `bastion` on
     PATH so session mode is runnable on this host (dep #2 of the spec).
  2. Added `/scripts/` to `.gitignore` (commit `chore: gitignore /scripts/`) — a task agent repeatedly
     regenerates machine-specific local dev helpers (`scripts/dev.sh`, `scripts/dev-setup.sh`:
     Homebrew/Postgres/Redis paths, local creds) in the repo root, which kept tripping the pre-flight
     and merge guards. They now stay on disk but never block a run.
- Per-task `/log-work` + `/commit` already updated `log.md` (detailed per-task entries, 2026-06-22) and
  `planning/status.md` during the run; status focus already advanced to **Phase 1 Project B**.

## Remaining work
- **Operator-run subscription-host e2e gates — the ONLY loose ends, on BOTH modes. Must run on a host
  with the `claude` CLI logged into the subscription (the headless pipeline cannot verify billing):**
  1. **SDK mode** (carried from last session, still placeholder in that spec's `## Notes`): confirm the
     env-scrub (`sdk_backend.py:59` blanks `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN`) actually forces
     subscription billing; run an `AgentNode` with `CLAUDE_CODE_SDK` + an `OutputType`, confirm validated
     structured output, real tokens in `NodeRun.usage`, and **no** key-billed spend in the Anthropic console.
  2. **Session mode** (this feature): run an `AgentNode` with `CLAUDE_CODE_SESSION` end-to-end against a
     real `bastion ask` tmux session; confirm structured output parses, the turn shows in
     `bastion sessions`, and billing is subscription-side. Record findings in this spec's `## Notes`.
- **Then: the next planned product unit is Phase 1 Project B (Research agent)** — thin cut first
  (~50 lines, raw tool loop), per status.md current focus. No blocker; start with `/feature` or
  `/generate-tasks` for it when ready.
- **Non-blocking, anytime:** Project A follow-ups in `planning/phase1-projectA/follow-ups.md`.

## Open questions / choices
- **None blocking.** Both provider modes pass all *automated* gates; only the subscription-host e2e
  verification remains, and that is an operator step, not an agent task.
- Minor housekeeping decisions for Brandon (not blockers): keep vs. discard the gitignored
  `scripts/dev.sh` + `dev-setup.sh` (also backed up at `/tmp/orchestration-stray-scripts/`); and whether
  to `cargo install --path ../bastion` for a PATH copy that survives `cargo clean` instead of the symlink.

## Context the next agent needs
- **Don't refactor `app/services/claude_code/` lightly** — `ClaudeCodeModel` + `ClaudeCodeBackend` +
  `ClaudeResult` are now shared by *two* backends (`sdk_backend.py`, `bastion_backend.py`). Changing the
  protocol breaks both modes.
- **The `bastion ask` flag set is a pinned cross-repo contract (v0.1.0).** If billing/observability
  behavior needs a flag change, it's owned by bastion: bump the version + changelog in the brain doc §2,
  then update our consumer side in the same change (same discipline as the data contract).
- **bastion cold-start gotcha (their D9):** readiness keys off `classify_state() == Running`, not an
  exact `"claude"` process-name match — Claude Code v2.1.185 renames its process to its version string.
  Invisible to our backend, but relevant when you run the live e2e.
- **venv gotcha:** a stale `VIRTUAL_ENV=.../orchestration/.venv` is exported in this shell. Run
  `uv run python -m <tool>` **without** `--active` so uv picks the project `.venv` (per CLAUDE.md). ruff
  prints a harmless warning about this; it still runs against the right env.

## First command after `/prime`
`uv run python -m pytest -q` — confirm the 353-test green baseline, then either pick up Project B
(`/feature` for the research agent) or, on a subscription-logged-in host, run the operator e2e gates above.
