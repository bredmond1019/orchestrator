---
type: Plan
title: Expose orchestration API publicly + fire-and-forget Telegram bot
description: Plan to expose the orchestration API at api.learn-agentic-ai.com via the existing Cloudflare Tunnel (gated by an in-app API key + Cloudflare Access), and add a long-poll, fire-and-forget Telegram bot in integrations/telegram/ as the first client — send a link, it fires a CONTENT_PIPELINE run and acks "Queued".
---

# Expose orchestration API publicly + fire-and-forget Telegram bot

**Status:** Ready to build. Run `/generate-tasks` against this plan to produce a `tasks.md`.

**Scope note:** Two loosely-coupled deliverables that can be sequenced independently —
(1) public API exposure + auth, (2) the Telegram bot. The bot works against `localhost`
regardless of (1); (1) is worth doing on its own merits (portfolio surface, future clients,
`bastion` remote-trigger). Suggested order: API hardening (§1) → bot (§2) → config/deploy (§3)
→ ops (§4, manual) → tests (§5) → docs (§6).

---

## Context

The orchestration system runs only on the Mac Mini at `127.0.0.1:8080`, reachable by nobody
outside the host. The frontend (`learn-ai`) is already public at `learn-agentic-ai.com` via a
Cloudflare Tunnel (`cloudflared` launchd service → `localhost:3003`). We want to:

1. **Expose the orchestration API** at `api.learn-agentic-ai.com` through the *same* tunnel
   (a second ingress rule), gated by auth so it isn't an open LLM-token faucet.
2. **Build a Telegram bot** as the first client: send a YouTube/article link from your phone →
   it fires a `CONTENT_PIPELINE` run → replies **"Queued ✅"** and stops.

**Fire-and-forget, by design.** The bot does **not** wait for, fetch, or return the result.
The digest is read later from the static HTML digest site Project A already produces on the
Mac Mini. This removes all result-polling: **no `GET /events/{id}`, no result rendering, no
change to the `POST /events/` response shape**, and therefore **no data-contract shape bump.**

**Bot transport: long-poll now, webhook later.** For a personal, low-volume bot, long-polling is
the least infrastructure — one persistent outbound process, no public inbound surface, no secret
token, clean restart behavior. Leave clear notes (code comment + bot README + a status deviation
line) that **webhook is the intended migration when this scales** (event-driven, no babysat loop,
leans on the public endpoint). Swapping later is a localized change to the bot run loop + one
tunnel route; it does not touch the API design here.

### Current state (verified during planning)

- `app/main.py` mounts a single router; **no CORS, no auth, no middleware**.
- `POST /events/` (`app/api/endpoint.py`) validates `{workflow_type, data}` against `SCHEMA_MAP`
  (`app/api/schema_registry.py`), persists an `Event`, enqueues a Celery task, returns
  `202 {task_id, message}`. It returns the **Celery `task_id`, not the `event_id`** (the DB PK).
- Other endpoints: `GET /health`, `GET /workflows`, `GET /workflows/{type}/graph`.
- Workflow output is persisted to `events.task_context` (JSON) progressively by the worker
  (`app/worker/tasks.py`). **No webhook/callback** exists; result reads are poll-based by design.
- `GET /events/{id}` is **reserved but not implemented** (`docs/data-contract.md` §7).
- The `cloudflared` tunnel config lives on the Mac Mini, **outside the repos** (e.g.
  `~/.cloudflared/config.yml` or the launchd plist path). Frontend → `localhost:3003`.
- `CONTENT_PIPELINE` event schema (`app/schemas/`): `{url: str, make_blog: bool = false, ...}`.
  The digest summary lands in the `SummarizerNode` output within `task_context.nodes`.

### Target topology

```
                          Cloudflare edge (TLS + Access policy)
  Telegram  <—long-poll—  [telegram bot]  ──X-API-Key──>  orchestrator API
                          (integrations/telegram/)        (localhost:8080, internal —
                           co-located on the Mini          skips the edge)
                                                                 │ Celery → worker → Postgres → digest HTML
                                                                 ▼  (read digests later, out of band)

  External callers ──CF Access token + X-API-Key──> api.learn-agentic-ai.com ──tunnel──> 127.0.0.1:8080
  learn-agentic-ai.com ──tunnel──> :3003 (frontend, unchanged)
```

The bot is co-located, so it calls the API internally (`http://api:8080` in Docker /
`localhost:8080`) with just the in-app `X-API-Key`, bypassing the edge. Cloudflare Access gates
only *external* callers of the public hostname.

---

## Work breakdown

### 1. API hardening (`app/api/`) — make the public surface safe (auth + CORS only)

**1a. In-app API key auth.** New `app/api/security.py`:
- `require_api_key(x_api_key: str = Header(...))` compares against env `ORCHESTRATION_API_KEY`
  with `hmac.compare_digest`; `401` on mismatch, `503` if the env var is unset (fail-closed).
- Apply via `dependencies=[Depends(require_api_key)]` on the **events** router (`POST /events/`).
- Leave `GET /health` open (uptime checks). `GET /workflows*` introspection can stay open
  (harmless metadata; CF Access fronts the whole hostname anyway) — document the choice.
- This is an **API-layer** concern — it does **not** violate D33 ("no deployment logic in
  nodes"); nothing in `app/core` or `app/workflows` changes.

**1b. CORS.** Add `CORSMiddleware` in `app/main.py`, origins from env `ALLOWED_ORIGINS`
(comma-split; default `https://learn-agentic-ai.com`). Not needed by the server-side bot, but
cheap and unblocks a future browser client.

**Explicitly deferred** (write a one-line note in `docs/data-contract.md` pointing here):
returning `event_id` from `POST /events/` and implementing the reserved `GET /events/{id}` —
only needed once a *result-reading* client exists (the webhook migration, or `bastion` moving
off direct DB reads). Not built now.

**Reuse:** `db_session` (`app/database/session.py`); the env fail-fast pattern from
`app/services/embedding_service.py`.

### 2. Telegram bot service — `integrations/telegram/` (long-poll, fire-and-forget)

New top-level dir (alongside `requests/`, `scripts/`, `docker/`), clearly outside `app/` (the
deployment-agnostic brain — the bot is a *consumer/shell*, like `bastion`):

```
integrations/telegram/
├── __init__.py
├── bot.py            # long-polling entrypoint + command handlers (+ TODO(webhook) notes)
├── client.py         # thin orchestration-API client (httpx): submit_event only
├── config.py         # env-driven settings (fail-fast on required keys)
├── README.md         # run/deploy/extend + the webhook-migration note
└── tests/            # handler + client tests (mocked Telegram + mocked API)
```

- **Library:** `python-telegram-bot` (async) under an **optional dependency group**
  `[project.optional-dependencies] telegram = [...]` in `pyproject.toml`, so the brain's core
  deps stay lean (`uv sync --extra telegram` on the Mini). `httpx` is already present.
- **`config.py`** reads env, fail-fast on required: `TELEGRAM_BOT_TOKEN`,
  `ORCHESTRATION_API_BASE_URL` (default `http://localhost:8080`), `ORCHESTRATION_API_KEY`,
  optional `CF_ACCESS_CLIENT_ID`/`CF_ACCESS_CLIENT_SECRET` (sent only when set, for the
  external-URL case), and `TELEGRAM_ALLOWED_CHAT_IDS` (allowlist — bot ignores everyone else,
  so a stranger can't burn tokens).
- **`client.py`** — `submit_event(workflow_type, data) -> dict` (`POST /events/` with `X-API-Key`
  + optional CF headers; returns the 202 body). No polling, no result fetch.
- **`bot.py`** — long-polling. MVP command **`/digest <url>`** (and accept a bare URL message as
  shorthand): validate it's a URL, submit
  `{workflow_type: "CONTENT_PIPELINE", data: {"url": <url>, "make_blog": false}}`, reply
  **"Queued ✅"** (optionally echo the returned `task_id` for traceability). Allowlist enforced
  in a pre-handler. Structure so adding `/research`, `/proposal`, etc. later is a new function +
  registration. Add a clear `# TODO(scale): switch to webhook transport` block at the run-loop.

### 3. Configuration & deployment

**Env (`app/.env.example`, `docker/.env.example`, `docs/configuration.md`):** add
`ORCHESTRATION_API_KEY`, `ALLOWED_ORIGINS`, and the Telegram/bot vars from §2, documented
(required vs optional) per the existing configuration.md sections.

**Run the bot as a service.** Add a `telegram_bot` service to
`docker/docker-compose.ai-event-system.yml` (same image/uv env, runs `bot.py`,
`depends_on: api`, `restart: unless-stopped`, base URL `http://api:8080` over the compose
network) — folds it into the existing `start.sh`/`stop.sh` lifecycle. *(Alternative: a launchd
service mirroring `com.brandon.learn-ai`, documented as an option.)*

**Keep the API bound to `127.0.0.1:8080`** — do **not** switch to `0.0.0.0`. `cloudflared` runs
on the host and reaches `localhost:8080` directly; localhost-only binding is strictly more secure.

### 4. Infrastructure / ops steps (manual, on the Mac Mini — documented, not code)

The tunnel config lives on the Mini, outside the repos. Capture these in `docs/infrastructure.md`
(brain repo, `agentic-portfolio/docs/`) and the bot `README.md`:

1. **Add the ingress rule** to the `cloudflared` config (`~/.cloudflared/config.yml` or the path
   in the launchd plist):
   ```yaml
   ingress:
     - hostname: learn-agentic-ai.com
       service: http://localhost:3003
     - hostname: api.learn-agentic-ai.com   # NEW
       service: http://localhost:8080
     - service: http_status:404
   ```
2. **Route DNS:** `cloudflared tunnel route dns <tunnel> api.learn-agentic-ai.com` (or add the
   CNAME in the Cloudflare dashboard).
3. **Restart the tunnel:** `sudo launchctl kickstart -k system/com.cloudflare.cloudflared`.
4. **Cloudflare Access (defense-in-depth, chosen):** Zero Trust → create an Access application for
   `api.learn-agentic-ai.com` + a service token + a policy requiring it. External callers send
   `CF-Access-Client-Id`/`CF-Access-Client-Secret`. (Optionally bypass `/health` for uptime checks.)
5. **Get the bot token:** create the bot via Telegram **@BotFather**, put the token in env, and
   note your chat id for the allowlist.
6. **Verify:** `curl https://api.learn-agentic-ai.com/health` → `200`; `POST /events/` without
   `X-API-Key` → `401`; with it → `202`.

### 5. Tests (standing rule: changes ship with tests)

- `tests/api/` — `require_api_key` (unset env → 503; wrong/missing key → 401; correct → pass);
  `POST /events/` rejects without the key and accepts with it. `TestSchemaRegistryCompleteness`
  stays green (no new workflow).
- `integrations/telegram/tests/` — `client.submit_event` against a mocked API (`respx`/httpx
  mock) asserting the `CONTENT_PIPELINE` payload + auth headers; `/digest` handler against a
  mocked `python-telegram-bot` update asserting allowlist enforcement, URL validation, the
  submitted payload, and the "Queued ✅" reply.

### 6. Docs

- `docs/configuration.md` — new env vars + the bot service.
- `docs/api-reference.md` — `require_api_key` + CORS.
- `docs/data-contract.md` — **patch-level clarification only** (no shape change): note that
  `POST /events/` now requires `X-API-Key`, and that `event_id`/`GET /events/{id}` remain
  deferred. (No `bastion` re-pin needed — `bastion` is a read-only Postgres observer and does not
  POST; mention this in the note.)
- `docs/infrastructure.md` (brain repo) — the ingress rule + Cloudflare Access setup (§4).
- `integrations/telegram/README.md` — run/deploy/extend + the webhook-migration note.
- Add a deviation line to `planning/status.md` recording the public-API exposure + bot, and the
  long-poll→webhook migration plan.

---

## Critical files

| File | Change |
|---|---|
| `app/api/security.py` *(new)* | `require_api_key` dependency |
| `app/main.py` | mount `CORSMiddleware` |
| `app/api/endpoint.py` | gate `POST /events/` router with `require_api_key` |
| `integrations/telegram/{bot,client,config}.py` *(new)* | long-poll bot + API client |
| `pyproject.toml` | `[telegram]` optional-deps group |
| `docker/docker-compose.ai-event-system.yml` | `telegram_bot` service |
| `app/.env.example`, `docker/.env.example` | new env vars |
| `docs/{configuration,api-reference,data-contract}.md`, `docs/infrastructure.md` (brain), `planning/status.md` | docs/status |

**Reuse (don't reinvent):** `db_session`, the fail-fast env pattern in
`app/services/embedding_service.py`, the existing `httpx` dependency, and the existing
`docker/start.sh`/`stop.sh` lifecycle.

---

## Verification (end-to-end)

1. **Unit/integration:** `uv run python -m pytest` (API auth + bot tests green);
   `uv run python -m ruff check app/ integrations/` and `uv run python -m pylint app/` clean.
2. **Local API smoke (no tunnel):** `cd docker && ./start.sh`; `curl localhost:8080/health` → `200`;
   `POST /events/` without key → `401`, with `X-API-Key` → `202`; confirm a `CONTENT_PIPELINE` run
   shows up in the worker logs and produces a digest.
3. **Bot smoke (local):** run the bot pointed at `localhost:8080`; from Telegram send a YouTube
   link; confirm it replies "Queued ✅" and the run starts. Confirm a non-allowlisted chat is
   ignored. Later, confirm the digest appears on the static digest site.
4. **Public path:** after the tunnel + Access steps, `curl https://api.learn-agentic-ai.com/health`
   → `200`; a `POST /events/` from outside without the CF Access token → blocked at the edge; with
   both the CF token and `X-API-Key` → `202`.

---

## Open decisions already settled (do not relitigate)

- **Long-poll, not webhook, for v1** — webhook is the documented scale-up path, not the starting point.
- **Fire-and-forget** — no result return to Telegram; digests read out of band from the static site.
- **Still expose `api.learn-agentic-ai.com`** even though the bot uses localhost (portfolio / future / `bastion`).
- **Defense-in-depth auth** — Cloudflare Access (edge) **and** in-app `X-API-Key`.
- **Bot lives in `integrations/telegram/`** in this repo, outside `app/`.
