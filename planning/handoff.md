---
type: Handoff
created: 2026-06-23
---

# Handoff — expose-api done; projectE and harness P0 fix next

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why

The `expose-api-and-telegram-bot` workstream is fully shipped and merged to `main`. This session completed the post-merge work: D23/D24 harness validation analysis (bug report at `planning/expose-api-and-telegram-bot/harness-update-review.md`), `/update-docs --patch` sweep (README test count, architecture overview, Telegram README expanded with full Mac Mini deployment guide), and a merge of `expose-api-telegram-bot` → `main`. Everything is committed and the working tree is clean. Two things are in front of the next agent: (1) fix the P0 harness bug in `.claude/workflows/sdlc-block.js` before the next `/sdlc-block` run to avoid another restart — Brandon is already working on this, so check first; (2) start `phase1-projectE` — the Specialization refactor — which is the next standing item on the roadmap.

## Completed this session

- **Ran `/sdlc-block expose-api-and-telegram-bot`** — first run PARTIAL (untracked baseline file blocked merges), committed fix, second run PASS. All 5 tasks merged, 705 tests pass, pylint 10.00/10.
- **Merged `expose-api-telegram-bot` → `main`** (`207ccdf`) — 53 files, 3508 insertions. Includes `app/api/security.py`, `integrations/telegram/`, `docker/Dockerfile.telegram`, `tests/api/test_security.py`, `tests/integrations/telegram/`.
- **Harness validation report** — `planning/expose-api-and-telegram-bot/harness-update-review.md` — 3 bugs documented (P0: baseline not committed; P1: emoji false gate; P2: no cross-invocation resume). Committed `f5ee424`.
- **`/update-docs --patch`** — patched `README.md` (test count 549→712, `integrations/` in dir map, five workflows listed) and `docs/app-architecture-overview.md` (added `api/security.py` to Generic API row, new Telegram bot row). Committed `13c9992`.
- **Expanded `integrations/telegram/README.md`** — added: topology primer (long-poll means no inbound port, phone→Telegram→bot→localhost), Docker Compose deployment, launchd plist template, @BotFather/chat-ID first-time setup, and network topology section covering Cloudflare Tunnel (public), Tailscale private access (with the `127.0.0.1` → `0.0.0.0` binding change required), and same-machine scenario. Committed `1626b70`.
- **SDLC commands updated** by Brandon in a separate commit (`1a51561 Updated SDLC Slash Commands and Workflows`) — harness tooling changes, likely including P0 fix or related updates.

## Remaining work

- **Verify P0 fix status** — Brandon said he was fixing P0 (`baseline-snapshot` writing untracked file) separately. Check `1a51561` diff before touching `.claude/workflows/sdlc-block.js`. If it's already fixed, skip.
- **Start `phase1-projectE`** — Specialization refactor. Task spec ready at `planning/phase1-projectE/tasks.md`. 5 tasks: (1) fix `ParallelNode` merge gap in `app/core/nodes/parallel.py`, (2) `ConceptExtractorNode`, (3) `StructureAnalystNode`, (4) `BlogDraftNode` + `VoiceMatchNode`, (5) register + validate. The `ParallelNode` fix is the prerequisite for all others.
- **Cross-repo manual ops** (Mac Mini, not in this repo): `cloudflared` ingress rule for `api.learn-agentic-ai.com`, DNS record, Cloudflare Access app + service token, @BotFather bot creation. Tracked in brain repo `docs/infrastructure.md`.
- **`docs/app-architecture-overview.md` ASCII diagram** — security/CORS layer and `integrations/` block not represented. Left as NEEDS_REVIEW (editorial judgment call, not a doc-sync task).

## Open questions / choices

- **Is P0 already fixed?** Check `git show 1a51561 -- .claude/workflows/sdlc-block.js` to see if the baseline-commit fix landed. If yes, the next `/sdlc-block` run should be clean.
- **`docs/README.md` curl example** — the "Sending a test event" curl in `README.md` sends no `X-API-Key` header and will now 401. Flagged NEEDS_REVIEW during the doc sweep — a one-liner fix but may warrant a broader quick-start update.

## Context the next agent needs

- **Current branch:** `main`. Working tree clean, up to date with origin.
- **Test count:** 712 collected, 705 pass, 8 skip. Baseline for projectE is 705 passing.
- **API binding:** `app/api/endpoint.py` gates `POST /events/` via `require_api_key` (`app/api/security.py:37`). `GET /health` and `GET /workflows*` are intentionally open. The API Docker port is `127.0.0.1:8080:8080` — Tailscale direct access requires changing this to `0.0.0.0:8080:8080` (documented in `integrations/telegram/README.md`).
- **ParallelNode gap (`app/core/nodes/parallel.py`):** `execute_nodes_in_parallel()` submits sub-nodes against a shared `TaskContext` from worker threads (race on `task_context.nodes`) and collected results are never merged back. `NodeConfig.parallel_nodes` (`app/core/schema.py:42`) already carries the parallel set. Existing tests in `tests/core/test_nodes_parallel.py`. This is task 1 of projectE and must land before tasks 2–4.
- **Telegram bot is a thin integration** (`integrations/telegram/`), not a workflow. It lives outside `app/` deliberately (D33: no deployment logic in nodes). The bot's `ORCHESTRATION_API_BASE_URL` defaults to `http://localhost:8080`; in Docker Compose it's `http://api:8080` over the internal network.

## First command after `/prime`

`git show 1a51561 --stat`
