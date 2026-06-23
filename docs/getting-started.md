---
type: Guide
title: Getting Started
description: Set up and run the orchestration framework locally — Homebrew path and OrbStack/Docker path.
---

# Getting Started

Two paths to a running stack. Pick whichever fits your machine.

- **Path A (local)** — Postgres and Redis run natively via Homebrew. Fastest for day-to-day dev; no containers in your way.
- **Path B (Docker)** — everything runs in containers via OrbStack. Closer to production; easier to throw away and rebuild.

Both paths end at the same place: `http://localhost:8080` serving the API with a Celery worker consuming jobs.

---

## Prerequisites (both paths)

```bash
# Python package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Python deps from repo root
uv sync
```

You'll also need API keys for any workflow that calls an AI model:

| Key | Where to get it | Required for |
|---|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com | All LLM workflows |
| `VOYAGE_API_KEY` | dash.voyageai.com | Embedding + RAG workflows (C, D, brain-rag) |
| `TAVILY_API_KEY` | tavily.com | Search workflows (B, C) |
| `FIRECRAWL_API_KEY` | firecrawl.dev | Article extraction fallback (A) — optional |

---

## Path A — Local dev (Homebrew)

The `scripts/dev-setup.sh` script is a one-time setup. It installs Postgres 17 + Redis + pgvector, creates a `orchestration_dev` database, and writes `app/.env`. Re-running is safe — every step is idempotent.

```bash
# 1. Run one-time setup (installs deps, creates DB, writes app/.env)
./scripts/dev-setup.sh

# 2. Open app/.env and fill in your API keys
#    (ANTHROPIC_API_KEY at minimum)
open app/.env

# 3. Start the stack in a tmux split (FastAPI top, Celery bottom)
./scripts/dev.sh

# To stop:
./scripts/dev.sh stop
```

`dev.sh` opens a tmux session named `orchestration`. If tmux isn't installed: `brew install tmux`.

You can also run the two processes manually in separate terminals:

```bash
# Terminal 1 — API
cd app && uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# Terminal 2 — Worker
cd app && uv run celery -A worker.config.celery_app worker --loglevel=info
```

---

## Path B — Docker with OrbStack

[OrbStack](https://orbstack.dev) is a fast, lightweight Docker Desktop replacement for Mac. If you're already using Docker Desktop, the commands are identical — just skip the OrbStack install.

```bash
# 1. Install OrbStack (or use Docker Desktop)
brew install orbstack
# or: download from orbstack.dev

# 2. Copy and fill in the docker env
cp docker/.env.example docker/.env
```

Open `docker/.env` and fill in:
- `PROJECT_NAME` — anything you like; becomes the container name prefix (e.g. `orchestration`)
- `POSTGRES_PASSWORD` — a password for the DB container
- `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, etc. — same AI keys as above
- Leave `TELEGRAM_BOT_TOKEN` empty unless you're running the bot

```bash
# 3. Build images and start all services
cd docker && ./start.sh

# The first build takes a few minutes. After that, it's fast.
# Tail logs:
./logs.sh

# Stop everything:
./stop.sh
```

**What `start.sh` starts:**
- `api` — FastAPI on `127.0.0.1:8080`
- `celery_worker` — Celery consuming from Redis
- `redis` — broker + result backend
- `db` — Postgres with pgvector (Supabase image)
- `telegram_bot` — only if `TELEGRAM_BOT_TOKEN` is set

**Run migrations inside Docker:**

```bash
docker exec -it <PROJECT_NAME>_api alembic upgrade head
# or with OrbStack: orb exec <PROJECT_NAME>_api alembic upgrade head
```

---

## Verify the stack is running

```bash
curl http://localhost:8080/health
# → {"status": "ok"}
```

List registered workflow types:

```bash
curl http://localhost:8080/workflows
```

---

## Send your first event

The API requires an `X-API-Key` header. For local dev, set a key in `app/.env`:

```
ORCHESTRATION_API_KEY=dev-secret
```

Then restart the server (or just set it before the first start). If `ORCHESTRATION_API_KEY` is blank, every request will 401.

```bash
# Content pipeline — summarize a YouTube video
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "CONTENT_PIPELINE",
    "data": {
      "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
      "make_blog": false
    }
  }'
# → 202 {"task_id": "...", "message": "process_incoming_event started `...`"}
```

The 202 means the event was persisted and queued. The Celery worker picks it up and runs the workflow asynchronously. See `docs/workflows.md` for payloads for each workflow.

### Calling the API from another device

`ORCHESTRATION_API_KEY` is a shared secret — there's no token exchange or registration. Both sides just need to know the same string. Copy the value from `app/.env` and send it as the `X-API-Key` header from any client:

```bash
curl -X POST https://api.learn-agentic-ai.com/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your-secret-here' \
  -d '...'
```

Store it in a password manager (1Password, Bitwarden) so you can paste it when setting up a new client. For mobile access, the Telegram bot is the better path — it holds the key server-side and you never need to type it on your phone.

---

## Check a run result

After a run completes, inspect the most recent content pipeline result:

```bash
cd app && uv run python ../scripts/inspect_run.py
```

This prints the per-node execution envelope (status, timing, token usage) and the stored `LearningArtifact`. See `docs/scripts.md` for all scripts.

---

## Run tests

```bash
uv run python -m pytest
# 712 tests; all should pass
```

---

## Next steps

- `docs/workflows.md` — what each workflow does and how to trigger it
- `docs/scripts.md` — all developer scripts
- `docs/api-reference.md` — how to write a new workflow
- `docs/configuration.md` — every environment variable
