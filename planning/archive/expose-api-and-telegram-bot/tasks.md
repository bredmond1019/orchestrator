---
type: TaskSpec
title: Expose orchestration API publicly + fire-and-forget Telegram bot
description: Task spec decomposing planning/plans/expose-api-and-telegram-bot.md into parallel-merge-safe SDLC tasks — API key auth + CORS, the integrations/telegram long-poll bot, config/deploy, and docs.
---

# Task Spec — Expose API Publicly + Telegram Bot

## Goal
Expose the orchestration API at `api.learn-agentic-ai.com` behind in-app auth + CORS, and add a long-poll, fire-and-forget Telegram bot in `integrations/telegram/` that fires a `CONTENT_PIPELINE` run from a sent link and replies "Queued ✅".

## Context Pointers
- **Source plan:** `planning/plans/expose-api-and-telegram-bot.md` — work breakdown §1–§6, "settled decisions, do not relitigate", and the verified current-state facts. Read it first.
- **Settled (do NOT relitigate):** long-poll (not webhook) for v1; fire-and-forget (no result return, **no data-contract shape bump**); still expose the public API; defense-in-depth auth (CF Access edge + in-app `X-API-Key`); bot lives in `integrations/telegram/` outside `app/`; API stays bound to `127.0.0.1:8080` (never `0.0.0.0`).
- **Repo facts confirmed during task gen:**
  - `app/main.py` mounts one router, no CORS/auth/middleware today.
  - `POST /events/` (`app/api/endpoint.py`) returns `202 {task_id, message}` (Celery task_id, not event_id); uses `session.flush()` before `send_task` (ghost-row guard — preserve).
  - `pytest.ini`: `testpaths = tests`, `pythonpath = app`. **Bot tests must live under `tests/` to be collected**, and `integrations` must be added to `pythonpath` to be importable. `httpx` is already a dev dep.
  - Harness ruff/pylint (`planning/harness.json`) scan **only `app/`** — `integrations/` lint is not gated; run it manually (spec-specific check below).
- **CLAUDE.md rules in play:** API-layer auth does NOT violate D33 (no deployment logic in nodes) — nothing in `app/core` or `app/workflows` changes. Code-style rules (3.10+ types, module docstring line 1, `encoding="utf-8"`, `raise ... from e`, no f-strings in logging, no param named `id`). Every change ships with tests.
- **Cross-repo / manual (NOT in this spec):** the `cloudflared` ingress rule, DNS route, tunnel restart, Cloudflare Access app + service token, and @BotFather bot creation are manual ops on the Mac Mini (plan §4). `docs/infrastructure.md` lives in the **brain repo** (`agentic-portfolio/docs/`), not here — note, don't edit.

## Step-by-Step Tasks

### 1. API key auth + CORS (API hardening)
- **Owns:** `app/api/security.py` (new), `app/main.py` (edit), `app/api/endpoint.py` (edit), `tests/api/test_security.py` (new).
- Create `app/api/security.py` with `require_api_key(x_api_key: str = Header(...))`:
  - Read expected key from env `ORCHESTRATION_API_KEY`. If unset → raise `HTTPException(503)` (fail-closed). If mismatch/missing → `401`. Compare with `hmac.compare_digest`.
  - Mirror the fail-fast env pattern in `app/services/embedding_service.py`. Module docstring on line 1; `raise ... from e` where applicable.
- In `app/api/endpoint.py`, gate the **events** route with `dependencies=[Depends(require_api_key)]` (the `POST /events/` router only). Do not touch the flush-before-send_task ordering.
- In `app/main.py`, add `CORSMiddleware` with origins from env `ALLOWED_ORIGINS` (comma-split; default `https://learn-agentic-ai.com`).
- Leave `GET /health` and `GET /workflows*` open (document the choice in the docstring/comment).
- Tests (`tests/api/test_security.py`): env unset → 503; missing/wrong key → 401; correct key → pass; `POST /events/` rejected without key and accepted with it. Keep `TestSchemaRegistryCompleteness` green (no new workflow added).

### 2. Telegram bot package (`integrations/telegram/`, long-poll, fire-and-forget)
- **Owns:** `integrations/telegram/{__init__,config,client,bot}.py` + `integrations/telegram/README.md` (new); `tests/integrations/__init__.py`, `tests/integrations/telegram/__init__.py`, `tests/integrations/telegram/test_client.py`, `tests/integrations/telegram/test_bot.py` (new); `pyproject.toml` (edit — optional-deps group); `pytest.ini` (edit — `pythonpath`).
- `pyproject.toml`: add `[project.optional-dependencies] telegram = ["python-telegram-bot>=21"]` (httpx already present). Run `uv sync --extra telegram` locally so collection sees the dep.
- `pytest.ini`: change `pythonpath = app` → `pythonpath = app .` so `integrations.telegram.*` is importable in tests. Keep `testpaths = tests`.
- `config.py`: env-driven, fail-fast on required — `TELEGRAM_BOT_TOKEN`, `ORCHESTRATION_API_KEY`; `ORCHESTRATION_API_BASE_URL` (default `http://localhost:8080`); optional `CF_ACCESS_CLIENT_ID`/`CF_ACCESS_CLIENT_SECRET` (sent only when set); `TELEGRAM_ALLOWED_CHAT_IDS` (comma-split allowlist).
- `client.py`: `submit_event(workflow_type, data) -> dict` — `POST /events/` via `httpx` with `X-API-Key` (+ CF headers when set); returns the 202 body. No polling, no result fetch.
- `bot.py`: long-polling entrypoint. Command `/digest <url>` and a bare-URL message shorthand: validate URL, submit `{"workflow_type": "CONTENT_PIPELINE", "data": {"url": <url>, "make_blog": false}}`, reply "Queued ✅" (optionally echo `task_id`). Enforce the chat-id allowlist in a pre-handler. Add a `# TODO(scale): switch to webhook transport` block at the run loop. Structure so adding `/research`, `/proposal` later is a new function + registration.
- `README.md`: run/deploy/extend instructions + the long-poll→webhook migration note.
- Tests: guard handler tests with `pytest.importorskip("telegram")` so the gated suite stays green when the extra isn't installed. `test_client.py` (httpx-only, always runs) asserts the `CONTENT_PIPELINE` payload + `X-API-Key`/CF headers against a mocked transport. `test_bot.py` asserts allowlist enforcement, URL validation, submitted payload, and the "Queued ✅" reply against a mocked update.

### 3. Configuration & deployment (env + docker service)
- **Owns:** `app/.env.example` (edit), `docker/.env.example` (edit), `docker/docker-compose.ai-event-system.yml` (edit).
- Add to both `.env.example` files (documented required vs optional): `ORCHESTRATION_API_KEY`, `ALLOWED_ORIGINS`, `TELEGRAM_BOT_TOKEN`, `ORCHESTRATION_API_BASE_URL`, `TELEGRAM_ALLOWED_CHAT_IDS`, `CF_ACCESS_CLIENT_ID`, `CF_ACCESS_CLIENT_SECRET`. Use the exact names from tasks 1 & 2 (shared contract — no renames).
- `docker/docker-compose.ai-event-system.yml`: add a `telegram_bot` service — same image/uv env, command runs `integrations/telegram/bot.py`, `depends_on: api`, `restart: unless-stopped`, base URL `http://api:8080` over the compose network. Document the launchd alternative (mirroring `com.brandon.learn-ai`) as a comment. Do **not** change the API port binding (`127.0.0.1:8080`).

### 4. Docs + status deviation
- **Owns:** `docs/configuration.md` (edit), `docs/api-reference.md` (edit), `docs/data-contract.md` (edit), `planning/status.md` (edit).
- `docs/configuration.md`: new env vars (§3) + the `telegram_bot` service.
- `docs/api-reference.md`: `require_api_key` dependency + the CORS middleware.
- `docs/data-contract.md`: **patch-level clarification only, no shape change** — note `POST /events/` now requires `X-API-Key`, that `event_id`/`GET /events/{id}` remain deferred, and that `bastion` needs no re-pin (read-only Postgres observer, never POSTs).
- `planning/status.md`: add a deviation line recording the public-API exposure + bot, and the long-poll→webhook migration plan.
- Note (do not edit here): `docs/infrastructure.md` (brain repo) ingress + CF Access steps are a manual cross-repo follow-up.
- **Depends on tasks 1, 2, 3** (documents what they built).

### 5. Validate
- Run the Validation Commands below and confirm all pass.

## Acceptance Criteria
- `POST /events/` returns `401` without `X-API-Key`, `503` when `ORCHESTRATION_API_KEY` is unset, and `202` with the correct key. `GET /health` stays open.
- `CORSMiddleware` is mounted with env-driven origins; default `https://learn-agentic-ai.com`.
- API remains bound to `127.0.0.1:8080`; no `app/core` or `app/workflows` files changed (D33 preserved).
- `integrations/telegram/` bot submits a `CONTENT_PIPELINE` `{url, make_blog:false}` event with auth headers, replies "Queued ✅", enforces the chat-id allowlist, and never polls for a result.
- `python-telegram-bot` is an **optional** dep (`telegram` extra); core `uv sync` stays lean; the gated `pytest` collection passes whether or not the extra is installed (handler tests `importorskip`).
- New env vars are documented in both `.env.example` files and `docs/configuration.md`; the `telegram_bot` compose service exists.
- `docs/data-contract.md` carries a patch-level clarification only — no response-shape or version bump.
- All gated harness checks pass; `integrations/` lints clean.

## Validation Commands
```
uv run python -m ruff check app/ integrations/
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
```

## Notes
- The first command (`ruff check app/ integrations/`) is spec-specific (the harness gates `app/` only); keep `integrations/` lint-clean anyway.
- Disjoint file ownership: Tasks 1, 2, 3 own non-overlapping files and run in parallel (wave 1); Task 4 (docs) depends on 1–3 (wave 2); Task 5 validates (wave 3). Env-var names are a shared contract — use the exact names across tasks, never rename.
