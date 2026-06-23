---
type: ReviewReport
title: Review Report — expose-api-and-telegram-bot
description: SDLC review verdict for the full expose-api-and-telegram-bot spec.
---

# Review Report — expose-api-and-telegram-bot

**Date:** 2026-06-23
**Spec:** planning/expose-api-and-telegram-bot/tasks.md
**Scope:** Full spec
**Verdict:** PASS

## Acceptance Criteria Check

| Criterion | Status | Evidence |
|---|---|---|
| `POST /events/` returns `401` without `X-API-Key`, `503` when `ORCHESTRATION_API_KEY` is unset, and `202` with the correct key. `GET /health` stays open. | MET | `app/api/security.py` lines 37-47; `tests/api/test_security.py` lines 95-154 |
| `CORSMiddleware` is mounted with env-driven origins; default `https://learn-agentic-ai.com`. | MET | `app/main.py` lines 20-44 |
| API remains bound to `127.0.0.1:8080`; no `app/core` or `app/workflows` files changed (D33 preserved). | MET | `docker/docker-compose.ai-event-system.yml` line 11; `git diff main..HEAD --name-only` shows no core/workflows changes |
| `integrations/telegram/` bot submits a `CONTENT_PIPELINE` `{url, make_blog:false}` event with auth headers, replies "Queued ✅", enforces the chat-id allowlist, and never polls for a result. | MET | `integrations/telegram/bot.py` lines 95-108; `integrations/telegram/client.py` lines 46-68 |
| `python-telegram-bot` is an optional dep (`telegram` extra); core `uv sync` stays lean; the gated `pytest` collection passes whether or not the extra is installed (handler tests `importorskip`). | MET | `pyproject.toml` line 31; `tests/integrations/telegram/test_bot.py` line 12 |
| New env vars are documented in both `.env.example` files and `docs/configuration.md`; the `telegram_bot` compose service exists. | MET | `app/.env.example` lines 48-63; `docker/.env.example` lines 9-24; `docker/docker-compose.ai-event-system.yml` line 76 |
| `docs/data-contract.md` carries a patch-level clarification only — no response-shape or version bump. | MET | `docs/data-contract.md` line 177: v1.0.1 patch note; no shape change |
| All gated harness checks pass; `integrations/` lints clean. | MET | All 7 gating checks pass (see Fresh Test Results below); `ruff check integrations/` clean |

## Fresh Test Results

All gating checks from `planning/harness.json` re-run fresh:

**standing-rules** — PASS
- f-string-in-logging: no matches in `app/`
- open-without-encoding: no matches in `app/`
- param-named-id: no matches in `app/`

**db-session-import** — PASS
```
cd app && uv run python -c 'import database.session'
(exit 0)
```

**db-repository-import** — PASS
```
cd app && uv run python -c 'import database.repository'
(exit 0)
```

**net-new-lint (ruff)** — PASS
```
uv run python -m ruff check app/
All checks passed!
```

**pylint** — PASS
```
uv run python -m pylint app/
Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)
```

**pytest-count** — PASS
```
uv run python -m pytest --collect-only -q
712 tests collected
```

**pytest** — PASS
```
uv run python -m pytest
705 passed, 8 skipped, 7 warnings in 2.13s
```

**integrations/ lint (spec-specific, non-gating)** — PASS
```
uv run python -m ruff check integrations/
All checks passed!
```

Note on the test report's "emoji-prohibition" failure: the test report listed this as a "universal harness gate" but it does not exist in `planning/harness.json`. The emoji ("Queued ✅") is a functional requirement explicitly called out in the spec (`tasks.md` line 41). It is present in `bot.py` as the required reply string and in `README.md` as documentation of that behavior. No harness gate was failed.

## Verdict: PASS

All 8 acceptance criteria are fully met and all 7 gating harness checks pass with exit 0. The implementation correctly adds `require_api_key` to `POST /events/` with fail-closed 503 behavior and 401 for bad keys, mounts `CORSMiddleware` with env-driven origins, keeps the API bound to `127.0.0.1:8080` without touching `app/core` or `app/workflows` (D33 preserved), delivers the `integrations/telegram/` bot with the required `CONTENT_PIPELINE` submission + allowlist + fire-and-forget pattern, gates `python-telegram-bot` as an optional dep with `importorskip` in handler tests, documents all new env vars in both `.env.example` files and `docs/configuration.md`, adds the `telegram_bot` compose service, and records only a patch-level clarification in `docs/data-contract.md`.

## Issues Found

None.

## Next Steps

The spec is complete. The following manual ops on the Mac Mini remain as noted in the spec (cross-repo, not in scope here):
- `cloudflared` ingress rule, DNS route, tunnel restart
- Cloudflare Access app + service token creation
- `@BotFather` bot token creation
- Update `docs/infrastructure.md` in the brain repo (agentic-portfolio)
