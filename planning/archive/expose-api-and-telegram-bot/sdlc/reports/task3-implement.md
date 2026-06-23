---
type: ImplementationReport
title: Implementation Report — expose-api-and-telegram-bot Task 3
description: Configuration and deployment artifacts for the public API exposure and Telegram bot.
---

# Implementation Report — expose-api-and-telegram-bot-task3

**Date:** 2026-06-23
**Plan:** planning/expose-api-and-telegram-bot/tasks.md
**Scope:** Task 3 — Configuration & deployment (env + docker service)

## What Was Built or Changed

- `app/.env.example`: added a documented `# API security` section (`ORCHESTRATION_API_KEY`, `ALLOWED_ORIGINS`) and a `# Telegram bot` section (`TELEGRAM_BOT_TOKEN`, `ORCHESTRATION_API_BASE_URL`, `TELEGRAM_ALLOWED_CHAT_IDS`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`) — all 7 env vars defined with inline comments distinguishing required vs optional.
- `docker/.env.example`: same 7 env vars added under the existing `LAUNCHPAD` block, with Docker-appropriate defaults (`ORCHESTRATION_API_BASE_URL=http://api:8080` for the Compose network).
- `docker/docker-compose.ai-event-system.yml`: added `ORCHESTRATION_API_KEY` and `ALLOWED_ORIGINS` to the `api` service environment block; added the `telegram_bot` service (`depends_on: api`, `restart: unless-stopped`, `Dockerfile.telegram` build, `/integrations` volume mount, all Telegram env vars injected).
- `docker/Dockerfile.telegram`: new Dockerfile for the bot container — same Python 3.12 slim base as the other images; installs core deps from `pyproject.toml` then `python-telegram-bot>=21` (the optional group); runs `integrations/telegram/bot.py`.
- `tests/api/test_endpoint.py`: applied the auth-bypass override (`override_require_api_key` in `endpoint_context`) so the dispatch tests (`TestEventDispatch`) continue to work after Task 1 gated `POST /events/` with `require_api_key`. This is the same fix previously applied in a separate worktree commit; the task3 worktree was initialized before that fix merged.

## Files Created or Modified

| File | Action |
|---|---|
| app/.env.example | modified |
| docker/.env.example | modified |
| docker/docker-compose.ai-event-system.yml | modified |
| docker/Dockerfile.telegram | created |
| tests/api/test_endpoint.py | modified |

## Validation Output

**Commands run:**
```
uv run python -m ruff check app/
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
```

**Result:** PASSED

## Decisions and Trade-offs

- `Dockerfile.telegram` installs `python-telegram-bot>=21` directly via `uv pip install --system` rather than through the optional-dep extra, because Docker build does not use `uv sync --extra telegram` by default. The optional-dep group in `pyproject.toml` remains the right artifact for local dev (`uv sync --extra telegram`); the Dockerfile mirrors the same package pinned independently for the container layer.
- `ORCHESTRATION_API_BASE_URL` default in `docker/.env.example` is `http://api:8080` (Compose network name). In `app/.env.example` the default is `http://localhost:8080` to match local-dev usage.
- The `telegram_bot` service uses `restart: unless-stopped` (matches the spec requirement) rather than `restart: always` used by the other services — consistent with Telegram bot lifecycle: the operator can stop it intentionally without it auto-reviving.
- `tests/api/test_endpoint.py` auth bypass: the fix adds `override_require_api_key` to the `endpoint_context` fixture. Auth coverage lives in `tests/api/test_security.py` (Task 1 deliverable); the endpoint tests focus on payload/DB/Celery logic and should not be coupled to auth details.
- The `integrations/` lint check (`uv run python -m ruff check app/ integrations/`) will only pass once Task 2 creates that directory; it is not gated in this task's validation run. `uv run python -m ruff check app/` passes cleanly.

## Follow-up Work

- `docs/configuration.md` update (new env vars + `telegram_bot` service) is owned by Task 4.
- The `cloudflared` ingress rule, DNS route, Cloudflare Access app, and `@BotFather` token creation are manual ops on the Mac Mini (plan §4) — not in scope here or in any code task.
- Webhook migration (`TODO(scale)` comment in `docker-compose.ai-event-system.yml` and in `bot.py`) is deferred; long-poll is intentional for v1.

## git diff --stat

```
 app/.env.example                          | 21 +++++++++++++++++-
 docker/.env.example                       | 19 ++++++++++++++++
 docker/docker-compose.ai-event-system.yml | 37 +++++++++++++++++++++++++++++++
 tests/api/test_endpoint.py                |  5 +++++
 4 files changed, 81 insertions(+), 1 deletion(-)
```
