---
type: Handoff
created: 2026-06-22
---

# Handoff — Project A live SDK run done; Project B is next

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why

Project A (`content_pipeline`) was already shipped and tested, but had never been
driven end-to-end against a **real LLM** through the newly-landed `CLAUDE_CODE_SDK`
provider (subscription-billed Claude via `claude-agent-sdk`). This session did that
full run-through on a real YouTube URL, using the recent per-node observability work
to watch every step, and captured the result in `planning/test-runs/`. The run
validated the SDK path **and** surfaced one real production bug, now fixed. Per
Brandon's decision, `CLAUDE_CODE_SDK` / `sonnet` is now the **default** for the
content_pipeline LLM nodes (revert to `ANTHROPIC` per-node when metered-API billing
is wanted). With this closed, the sequence advances to **Phase 1 Project B (Research
agent)** — thin cut first (~50 lines, raw tool loop).

## Completed this session

- **Live end-to-end run** of `content_pipeline`, digest-only (`make_blog=false`), on
  `https://www.youtube.com/watch?v=DzbqeO_diOQ` through `CLAUDE_CODE_SDK`/`sonnet`.
  Full trace + verdict in `planning/test-runs/phase1-projectA-test-run1.md`.
  Result: all nodes succeeded, real Sonnet structured `SummaryOutput`, Voyage
  embedding persisted (1024-dim), digest HTML written.
- **Switched 5 content_pipeline LLM nodes** (`summarizer`, `blog_writer`,
  `self_critic`, `revise`, `translate_ptbr`) `get_agent_config()` →
  `ModelProvider.CLAUDE_CODE_SDK` / `model_name="sonnet"` (was `ANTHROPIC` /
  `claude-opus-4-8`). Commit `105559f`.
- **Fixed a real bug** found by the run: `StorageNode` raised
  `DetachedInstanceError` — `_persist()` commits+closes its session
  (`expire_on_commit`), then `process()` read `artifact.id` afterward. Fix: capture
  `artifact_id` from the event before persisting (`app/workflows/content_pipeline_workflow_nodes/storage_node.py`).
  Commit `3a99083`; regression test in commit `a125d6a`.
- **Made SDK token usage meaningful**: `ClaudeAgentSdkBackend` now sums
  `input_tokens` + `cache_read_input_tokens` + `cache_creation_input_tokens` (the SDK
  reports most prompt tokens as cache, so `NodeRun.usage.input_tokens` had shown a
  misleading `4`). `app/services/claude_code/sdk_backend.py`, commit `7a5c93b`.
- **Test updates**: new StorageNode post-persist regression test, new cache-token
  test, and aligned the 3 stale node-config tests to the SDK/sonnet default.
- **`.gitignore`**: ignore `_digest/` (StorageNode runtime output).
- **Validation**: `360 passed`, ruff clean, pylint `10.00/10`.

## Remaining work

- **Start Phase 1 Project B (Research agent).** Not started. Thin cut first
  (~50 lines, raw tool loop) per `status.md` and the Projects plan. Use
  `createworkflow` to scaffold the new workflow directory; register it in
  `app/workflows/workflow_registry.py`; ship with tests (standing rule).
- **Optional, non-blocking cleanups noted in the run log** (do only if convenient):
  `nodes["SummarizerNode"]` carries the summary under both `output` and `result`
  keys (harmless duplication — but note `StorageNode` reads `["result"]`, so don't
  remove that key without updating the reader).

## Open questions / choices

- **`scripts/inspect_run.py`** (a machine-local run inspector) is **not committed** —
  `scripts/` is gitignored by design. It's still on disk for reuse. Leave as-is unless
  Brandon wants a tracked tooling home for it.
- Project A's earlier deferred follow-ups in `planning/phase1-projectA/follow-ups.md`
  remain open and non-blocking (unrelated to this session).

## Context the next agent needs

- **Local run recipe (no Docker):** Postgres + Redis are already running locally;
  `app/.env` holds DB/Redis/CLAUDE_CODE config but its `VOYAGE_API_KEY` is an empty
  placeholder. The real `VOYAGE_API_KEY` (and `ANTHROPIC_API_KEY`) live in the **root
  `.env.local`**, which nothing auto-loads (the app `load_dotenv()`s `app/.env` from
  `app/`). So launch the worker/API with `set -a; source ../.env.local; set +a` from
  `app/` first; `load_dotenv` is `override=False` so `app/.env` won't clobber the
  exported secret. `EmbeddingService` does `os.environ["VOYAGE_API_KEY"]`.
- **Observability read-back:** the worker persists `task_context` via `session.flush()`
  (not commit) until the run ends, so a *separate* process can't see mid-run state via
  the DB. Live source is the Celery worker INFO logs (`Starting node` / `Finished
  node`); the full committed per-node envelope is in `events.task_context` after the
  run. There is **no `GET /events/{id}`** yet (reserved in `docs/data-contract.md`).
- **`claude` CLI** must be authenticated (subscription) on the host for the SDK path;
  the backend blanks `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` for the child process.
- **POST route is `/events/`** with `workflow_type` = the uppercase enum name
  (`CONTENT_PIPELINE`), not lowercase.
- Recurring `VIRTUAL_ENV` warning points at a stale `agentic-portfolio/orchestration/.venv`
  path; harmless — `unset VIRTUAL_ENV` before `uv run` to silence it.

## First command after `/prime`

`/generate-tasks` for Phase 1 Project B (Research agent) — or read
`planning/status.md` + the Project B section of the Projects plan, then scaffold with
`uv run createworkflow`.
