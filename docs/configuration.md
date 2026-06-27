---
type: Reference
title: Configuration Reference
description: Reference for every environment variable, connection-string assembly, and Docker service topology needed to configure the stack for local or Docker deployment.
doc_id: configuration
layer: [engine]
project: orchestrator
status: active
keywords: [environment variables, connection string, Docker, PostgreSQL, Redis, Celery]
related: [getting-started, scripts]
---

# Configuration Reference

Complete reference for environment variables, connection string assembly, and Docker service
topology. Covers both local development and full Docker deployment.

---

## 1. Two env file contexts

There are two distinct `.env` files in this project, each serving a different consumer.

| File | Consumer | Loaded by |
|---|---|---|
| `app/.env` | Python application (FastAPI, Celery, `database_utils.py`, `worker/config.py`) | `python-dotenv` `load_dotenv()` at runtime |
| `docker/.env` | Docker Compose variable substitution | Docker Compose engine before container startup |

**`app/.env`** is never read by Docker Compose. It is loaded at Python process startup via
`dotenv.load_dotenv()` calls at the top of `app/database/database_utils.py` and
`app/worker/config.py`. Outside Docker (local dev), this is the only file you need to populate.

**`docker/.env`** is read exclusively by the Docker Compose engine. It provides the values that
Compose substitutes into `${VAR}` placeholders in `docker-compose.ai-event-system.yml` and
`docker-compose.supabase.yml`. After substitution, Compose writes the resolved values into each
container's environment block. The containers themselves never load `docker/.env` — they receive
the expanded values as ordinary environment variables, which Python's `os.getenv()` then reads.

### How `docker-compose.ai-event-system.yml` maps `docker/.env` onto container environment

The `api` and `celery_worker` services each contain an explicit `environment:` block that
translates `docker/.env` names into the application-side names that Python expects:

```yaml
environment:
  - PROJECT_NAME=${PROJECT_NAME}
  - DATABASE_HOST=${POSTGRES_HOST}      # docker/.env POSTGRES_HOST → app DATABASE_HOST
  - DATABASE_NAME=${POSTGRES_DB}        # docker/.env POSTGRES_DB   → app DATABASE_NAME
  - DATABASE_USER=postgres              # hard-coded; no docker/.env variable
  - DATABASE_PASSWORD=${POSTGRES_PASSWORD}
  - DATABASE_PORT=${POSTGRES_PORT}
  - OPENAI_API_KEY=${OPENAI_API_KEY}
  - AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}
  - AZURE_OPENAI_API_KEY=${AZURE_OPENAI_API_KEY}
  - OPENAI_API_VERSION=${OPENAI_API_VERSION}
  - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
  - GEMINI_API_KEY=${GEMINI_API_KEY}
  - OLLAMA_BASE_URL=${OLLAMA_BASE_URL}
  - BEDROCK_AWS_ACCESS_KEY_ID=${BEDROCK_AWS_ACCESS_KEY_ID}
  - BEDROCK_AWS_SECRET_ACCESS_KEY=${BEDROCK_AWS_SECRET_ACCESS_KEY}
  - BEDROCK_AWS_REGION=${BEDROCK_AWS_REGION}
```

Key translation points:

- `POSTGRES_HOST` (docker) becomes `DATABASE_HOST` (app)
- `POSTGRES_DB` (docker) becomes `DATABASE_NAME` (app)
- `DATABASE_USER` is always injected as the literal string `postgres` — there is no Compose
  variable for it. The docker database user is the default `postgres` superuser.
- `REDIS_URL` is **not** passed from `docker/.env` to containers. Inside Docker, `worker/config.py`
  derives the Redis hostname from `PROJECT_NAME` (see section 5).

The root `docker/docker-compose.yml` uses `include:` to pull in both compose files and declares
the shared network:

```yaml
include:
  - path: ./docker-compose.ai-event-system.yml
  - path: ./docker-compose.supabase.yml

networks:
  default:
    driver: bridge
    external: true
    name: "${PROJECT_NAME}_network"
```

---

## 2. Application environment variables

Copy `app/.env.example` to `app/.env` and fill in the required values before running locally.

| Variable | Type | Default in code | Required | Component |
|---|---|---|---|---|
| `PROJECT_NAME` | string | — | Yes | `worker/config.py` (Redis hostname derivation), container naming |
| `DATABASE_HOST` | string | `localhost` | Yes | `DatabaseUtils.get_connection_string()` |
| `DATABASE_PORT` | string | `5432` | No | `DatabaseUtils.get_connection_string()` |
| `DATABASE_NAME` | string | `postgres` | No | `DatabaseUtils.get_connection_string()` |
| `DATABASE_USER` | string | `postgres` | No | `DatabaseUtils.get_connection_string()` — note: `app/.env.example` defaults to `postgres.launchpad` (Supabase pooler format); Docker hard-codes `postgres` |
| `DATABASE_PASSWORD` | string | `postgres` | Yes | `DatabaseUtils.get_connection_string()` |
| `REDIS_URL` | string | derived | No | `worker/config.py` `get_redis_url()` |
| `OPENAI_API_KEY` | string | — | Conditional | `AgentNode` / `ModelProvider.OPENAI` |
| `AZURE_OPENAI_ENDPOINT` | string | — | Conditional | `AgentNode` / `ModelProvider.AZURE_OPENAI` |
| `AZURE_OPENAI_API_KEY` | string | — | Conditional | `AgentNode` / `ModelProvider.AZURE_OPENAI` |
| `OPENAI_API_VERSION` | string | `2024-07-01-preview` | Conditional | `AgentNode` / `ModelProvider.AZURE_OPENAI` |
| `ANTHROPIC_API_KEY` | string | — | Conditional | `AgentNode` / `ModelProvider.ANTHROPIC` |
| `VOYAGE_API_KEY` | string | — | Conditional | `EmbeddingService` |
| `ANTHROPIC_API_KEY` | string | — | Conditional | `AgentNode` / `ModelProvider.ANTHROPIC`, `ToolUseNode` |
| `TOOL_USE_MODEL` | string | `claude-haiku-4-5-20251001` | No | `ToolUseNode` — overrides the Anthropic model used by all `ToolUseNode` subclasses |
| `GEMINI_API_KEY` | string | — | Conditional | `AgentNode` / `ModelProvider.GEMINI` |
| `OLLAMA_BASE_URL` | string | `http://localhost:11434/v1` | Conditional | `AgentNode` / `ModelProvider.OLLAMA` |
| `BEDROCK_AWS_ACCESS_KEY_ID` | string | — | Conditional | `AgentNode` / `ModelProvider.BEDROCK` |
| `BEDROCK_AWS_SECRET_ACCESS_KEY` | string | — | Conditional | `AgentNode` / `ModelProvider.BEDROCK` |
| `BEDROCK_AWS_REGION` | string | — | Conditional | `AgentNode` / `ModelProvider.BEDROCK` |
| `CLAUDE_CODE_BIN` | string | `claude` (on `$PATH`) | Conditional | `ClaudeAgentSdkBackend` — path to the `claude` binary; leave blank to use `claude` resolved from `$PATH` |
| `CLAUDE_CODE_CWD` | string | repo root | Conditional | `ClaudeAgentSdkBackend` — working directory passed to the SDK subprocess; leave blank to use the process working directory |
| `CLAUDE_CODE_PERMISSION_MODE` | string | `bypassPermissions` | Conditional | `ClaudeAgentSdkBackend` — SDK permission mode; `bypassPermissions` is required for non-interactive agent use |
| `CLAUDE_CODE_SDK_TIMEOUT_SECONDS` | integer | `180` | Conditional | `ClaudeAgentSdkBackend` — per-call timeout in seconds before the SDK subprocess is cancelled |
| `BASTION_BIN` | string | `bastion` (on `$PATH`) | Conditional | `BastionSessionBackend` — path to the `bastion` binary; resolved via `shutil.which` then verbatim fallback |
| `CLAUDE_CODE_TMUX_SESSION` | string | `orchestrator-claude` | Conditional | `BastionSessionBackend` — tmux session name that `bastion ask` targets |
| `CLAUDE_CODE_WORKDIR` | string | — | Conditional | `BastionSessionBackend` — pre-trusted working directory used when the Claude Code session was created |
| `CLAUDE_CODE_IO_DIR` | string | `CLAUDE_CODE_WORKDIR` | Conditional | `BastionSessionBackend` — directory where per-turn prompt/answer temp files are written; must be on the same host as the session |
| `CLAUDE_CODE_SESSION_TIMEOUT_SECONDS` | integer | `180` | Conditional | `BastionSessionBackend` — per-call timeout in seconds |
| `FIRECRAWL_API_KEY` | string | — | Optional | `ArticleExtractionService` Firecrawl fallback |
| `TAVILY_API_KEY` | string | — | Conditional | `SearchService` — required when any workflow uses web search |
| `CONTENT_DIGEST_DIR` | string | `./_digest` | Optional | `StorageNode` — root directory for static HTML digest pages; sub-folders per category are created automatically |
| `ORCHESTRATION_API_KEY` | string | — | **Required** (public) | `app/api/security.py` — `X-API-Key` value for `POST /events/`; if unset, the service returns `503` (fail-closed). Generate with `python -c "import secrets; print(secrets.token_hex(32))"`. |
| `ALLOWED_ORIGINS` | string | `https://learn-agentic-ai.com` | No | `app/main.py` — comma-separated list of origins for `CORSMiddleware`. |
| `TELEGRAM_BOT_TOKEN` | string | — | **Required** (bot) | `integrations/telegram/config.py` — token issued by @BotFather. |
| `ORCHESTRATION_API_BASE_URL` | string | `http://localhost:8080` | No | `integrations/telegram/config.py` — base URL the bot uses to reach `POST /events/`. Use `http://api:8080` inside Docker Compose. |
| `TELEGRAM_ALLOWED_CHAT_IDS` | string | — | No | `integrations/telegram/config.py` — comma-separated allowlist of Telegram chat IDs. When unset, the bot accepts all chats (not recommended for production). |
| `CF_ACCESS_CLIENT_ID` | string | — | No | `integrations/telegram/config.py` — Cloudflare Access service-token header; only required when the bot calls the API via the public hostname (`api.learn-agentic-ai.com`). |
| `CF_ACCESS_CLIENT_SECRET` | string | — | No | `integrations/telegram/config.py` — Cloudflare Access service-token secret; paired with `CF_ACCESS_CLIENT_ID`. |

"Conditional" means the variable is required only when a workflow node is configured with the
corresponding `ModelProvider` value (or service, in the case of `TAVILY_API_KEY`).

---

## 3. AI provider API keys

`AgentNode.__get_model_instance()` dispatches on `AgentConfig.model_provider` to select which
credentials to use. Each `ModelProvider` enum value and its required variables:

| `ModelProvider` enum value | String value | Required variables |
|---|---|---|
| `ModelProvider.OPENAI` | `"openai"` | `OPENAI_API_KEY` |
| `ModelProvider.AZURE_OPENAI` | `"azure_openai"` | `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `OPENAI_API_VERSION` |
| `ModelProvider.ANTHROPIC` | `"anthropic"` | `ANTHROPIC_API_KEY` |
| `ModelProvider.GEMINI` | `"gemini"` | `GEMINI_API_KEY` |
| `ModelProvider.OLLAMA` | `"ollama"` | `OLLAMA_BASE_URL` |
| `ModelProvider.BEDROCK` | `"bedrock"` | `BEDROCK_AWS_ACCESS_KEY_ID`, `BEDROCK_AWS_SECRET_ACCESS_KEY`, `BEDROCK_AWS_REGION` |
| `ModelProvider.CLAUDE_CODE_SDK` | `"claude_code_sdk"` | `CLAUDE_CODE_BIN`, `CLAUDE_CODE_CWD`, `CLAUDE_CODE_PERMISSION_MODE`, `CLAUDE_CODE_SDK_TIMEOUT_SECONDS` (all optional — see below) |
| `ModelProvider.CLAUDE_CODE_SESSION` | `"claude_code_session"` | `BASTION_BIN`, `CLAUDE_CODE_TMUX_SESSION`, `CLAUDE_CODE_WORKDIR`, `CLAUDE_CODE_IO_DIR`, `CLAUDE_CODE_SESSION_TIMEOUT_SECONDS` (all optional — see below) |

`ModelProvider` is defined in `app/core/nodes/agent.py` as a `StrEnum`:

```python
class ModelProvider(StrEnum):
    OPENAI          = "openai"
    AZURE_OPENAI    = "azure_openai"
    ANTHROPIC       = "anthropic"
    GEMINI          = "gemini"
    OLLAMA          = "ollama"
    BEDROCK         = "bedrock"
    CLAUDE_CODE_SDK = "claude_code_sdk"
    CLAUDE_CODE_SESSION = "claude_code_session"
```

If `model_provider` does not match any case in the `match` block, the node falls back to
`OpenAIModel("gpt-4.1")` — which will fail at runtime if `OPENAI_API_KEY` is not set.

**Azure OpenAI**: `AsyncAzureOpenAI()` is constructed with no explicit arguments, so it reads
`AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and `OPENAI_API_VERSION` from the environment
using the standard `openai` SDK conventions.

**Ollama**: `OLLAMA_BASE_URL` is read directly via `os.getenv("OLLAMA_BASE_URL")`. If missing, the
node raises `KeyError("OLLAMA_BASE_URL not set in .env")` rather than silently failing. The default
value `http://localhost:11434/v1` in `app/.env.example` assumes a locally running Ollama server.

**Bedrock**: `BEDROCK_AWS_ACCESS_KEY_ID`, `BEDROCK_AWS_SECRET_ACCESS_KEY`, and `BEDROCK_AWS_REGION`
are read via `os.getenv()` and passed directly to `boto3.client("bedrock-runtime", ...)`.

**Claude Code SDK**: `ModelProvider.CLAUDE_CODE_SDK` routes through `ClaudeAgentSdkBackend`
(in `app/services/claude_code/sdk_backend.py`). Unlike the other providers, it does **not**
authenticate with an API key — it drives the host's Claude Code subscription.

*Prerequisites (host running the API/worker):*

- The `claude-agent-sdk` Python package must be installed (it ships in `pyproject.toml`
  dependencies; `uv sync` installs it). Verify with `cd app && uv run python -c "import claude_agent_sdk"`.
- The `claude` CLI binary must be present on the host (`claude-agent-sdk` shells out to it) and
  **logged into a Claude Max / Pro subscription** (`claude login`). The backend cannot use this
  provider headlessly without an existing subscription session.

*Subscription billing:* no `ANTHROPIC_API_KEY` is used. The backend blanks both
`ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` in the spawned CLI's environment, so a key
exported on the host cannot redirect billing to the metered Anthropic API.

*Usage reporting:* SDK mode returns **real token usage** (`input_tokens` / `output_tokens`)
and the SDK's client-side cost estimate (`total_cost_usd`) from the terminal `ResultMessage`;
these flow into `NodeRun.usage` via `run_agent_recorded`.

All four env vars are optional with sensible defaults: `CLAUDE_CODE_BIN` (default: `claude` on
`$PATH`), `CLAUDE_CODE_CWD` (default: process cwd), `CLAUDE_CODE_PERMISSION_MODE` (default:
`bypassPermissions`), and `CLAUDE_CODE_SDK_TIMEOUT_SECONDS` (default: `180`).

The cross-repo design and the contract for the sibling `CLAUDE_CODE_SESSION` (bastion) mode are
tracked in the company-brain doc `agentic-portfolio/docs/integrations/claude-code-llm-provider.md`.

**Claude Code session (bastion)**: `ModelProvider.CLAUDE_CODE_SESSION` routes through
`BastionSessionBackend` (in `app/services/claude_code/bastion_backend.py`). Like SDK mode it is
subscription-billed and does **not** use an API key, but instead of an ephemeral CLI subprocess it
runs the turn on the **live interactive Claude Code session** that `bastion` manages in tmux, by
shelling out to `bastion ask`. The turn is therefore observable and attachable in `bastion sessions`.

*Prerequisites (host running the API/worker):*

- The `bastion` binary must be built and on the host `$PATH` (resolved via `BASTION_BIN`, falling
  back to `shutil.which("bastion")`). It must expose the `bastion ask` command (Block G, v0.1.0).
- The tmux host must be logged into the Claude Code subscription (`claude login`), and the session
  named by `CLAUDE_CODE_TMUX_SESSION` (default `orchestrator-claude`) must be reachable by `bastion`.
- `CLAUDE_CODE_WORKDIR` must be a directory the Claude Code session **already trusts** (pre-trusted
  scratch dir used to create the session). `CLAUDE_CODE_IO_DIR` (where the per-turn prompt/answer
  files are written; defaults to `CLAUDE_CODE_WORKDIR`) must be on the **same host** as the session.

*Subscription billing:* no `ANTHROPIC_API_KEY` is used — the turn runs on the host's logged-in
subscription session, so the Anthropic API console shows no key-billed spend for these calls.

*Limitations:*

- Session mode does **not** surface token usage. `ClaudeResult` returns `input_tokens`,
  `output_tokens`, and `cost_usd` as `None`, so `NodeRun.usage` token fields are `None` (the
  `model` field is still recorded).
- The per-turn `model` is **advisory only** in v0.1.0: the session's model is fixed at launch and is
  not switched per call.

All five env vars are optional with sensible defaults: `BASTION_BIN` (default: `bastion` on `$PATH`),
`CLAUDE_CODE_TMUX_SESSION` (default: `orchestrator-claude`), `CLAUDE_CODE_WORKDIR` (the trusted
scratch dir used to create the session), `CLAUDE_CODE_IO_DIR` (default: `CLAUDE_CODE_WORKDIR`), and
`CLAUDE_CODE_SESSION_TIMEOUT_SECONDS` (default: `180`).

**VoyageAI embeddings**: `VOYAGE_API_KEY` is read via `os.environ["VOYAGE_API_KEY"]` inside
`EmbeddingService.__init__()`. Unlike the `AgentNode` provider keys it is not gated on a
`ModelProvider` config — any workflow that constructs an `EmbeddingService` instance requires
this key to be set. If missing, a `KeyError` is raised at construction time.

---

## 4. PostgreSQL connection string assembly

`DatabaseUtils.get_connection_string()` in `app/database/database_utils.py` assembles the
SQLAlchemy connection URL:

```python
return f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
```

The five `os.getenv()` calls and their fallback values:

| `os.getenv()` call | Env variable | Fallback |
|---|---|---|
| `db_host` | `DATABASE_HOST` | `localhost` |
| `db_port` | `DATABASE_PORT` | `5432` |
| `db_name` | `DATABASE_NAME` | `postgres` |
| `db_user` | `DATABASE_USER` | `postgres` |
| `db_password` | `DATABASE_PASSWORD` | `postgres` |

**Docker mapping**: The Supabase Postgres container (`db`) exposes itself on the `${PROJECT_NAME}_network`
bridge with the container name `supabase-db`. The `api` and `celery_worker` containers receive their
database coordinates through the Compose environment translation described in section 1:

| `docker/.env` variable | Compose injects as | Python reads as |
|---|---|---|
| `POSTGRES_HOST` (default: `db`) | `DATABASE_HOST` | `db_host` |
| `POSTGRES_DB` (default: `postgres`) | `DATABASE_NAME` | `db_name` |
| `POSTGRES_PORT` (default: `5432`) | `DATABASE_PORT` | `db_port` |
| `POSTGRES_PASSWORD` | `DATABASE_PASSWORD` | `db_password` |
| *(hard-coded `postgres`)* | `DATABASE_USER` | `db_user` |

For example, with the defaults from `docker/.env.example`, the assembled URL is:

```
postgresql://postgres:your-super-secret-and-long-postgres-password@db:5432/postgres
```

---

## 5. Redis URL assembly

`get_redis_url()` in `app/worker/config.py` follows a two-step resolution:

```python
def get_redis_url():
    redis_url = os.getenv('REDIS_URL')
    if redis_url:
        return redis_url

    redis_host = f"{os.getenv('PROJECT_NAME')}_redis"
    return f"redis://{redis_host}:6379/0"
```

| Condition | Path taken | Example result |
|---|---|---|
| `REDIS_URL` is set in environment | Returns it directly | `redis://localhost:6379/0` |
| `REDIS_URL` is unset | Derives hostname from `PROJECT_NAME` | `redis://launchpad_redis:6379/0` |

**Local development**: Set `REDIS_URL=redis://localhost:6379/0` in `app/.env` to point at a
locally running Redis instance without relying on `PROJECT_NAME` container naming.

**Docker**: Do not set `REDIS_URL`. The Compose environment block for `api` and `celery_worker`
does not inject `REDIS_URL`, so the fallback path runs. With `PROJECT_NAME=launchpad`, the
derived URL is `redis://launchpad_redis:6379/0`, which resolves to the `redis` container on the
shared `${PROJECT_NAME}_network` bridge.

`get_redis_url()` is called by `get_celery_config()`, which uses the result as both `broker_url`
and `result_backend`:

```python
def get_celery_config():
    redis_url = get_redis_url()
    return {
        "broker_url": redis_url,
        "result_backend": redis_url,
        "task_serializer": "json",
        "accept_content": ["json"],
        "result_serializer": "json",
        "enable_utc": True,
        "broker_connection_retry_on_startup": True,
    }
```

---

## 6. Docker service topology

All services share a single external bridge network named `${PROJECT_NAME}_network`. The network
must be created before starting the stack (the `start.sh` script handles this).

### `api`

| Property | Value |
|---|---|
| Build context | repo root (`..` relative to `docker/`) |
| Dockerfile | `docker/Dockerfile.api` |
| Container name | `${PROJECT_NAME}_api` |
| Exposed port | `127.0.0.1:8080:8080` (loopback-only) |
| Restart policy | `always` |
| Volume mount | `../app/:/app` (live-reload of source) |
| Depends on | `db`, `redis` |

The `api` container receives `ORCHESTRATION_API_KEY` and `ALLOWED_ORIGINS` in its
environment block so that `POST /events/` auth and CORS are correctly configured inside
Docker (see section 2 for variable descriptions).

### `celery_worker`

| Property | Value |
|---|---|
| Build context | repo root |
| Dockerfile | `docker/Dockerfile.celery` |
| Container name | `${PROJECT_NAME}_celery_worker` |
| Exposed port | none |
| Restart policy | `always` |
| Volume mount | `../app:/app` |
| Depends on | `api` |

The `celery_worker` depends on `api`, not directly on `db` or `redis`. Both `api` and
`celery_worker` receive identical environment blocks (section 1).

### `redis`

| Property | Value |
|---|---|
| Image | `redis:latest` |
| Container name | `${PROJECT_NAME}_redis` |
| Exposed port | `127.0.0.1:6379:6379` (loopback-only) |
| Restart policy | `always` |
| Named volume | `redis_data:/data` |
| Health check | `redis-cli ping` every 30 s, 5 retries, 10 s timeout |

### `db` (Supabase Postgres)

| Property | Value |
|---|---|
| Image | `supabase/postgres:15.8.1.060` |
| Container name | `supabase-db` |
| Exposed port | none (access via network only) |
| Restart policy | `unless-stopped` |
| Named volumes | `db_data:/var/lib/postgresql/data`, `db_config:/etc/postgresql-custom` |
| Health check | `pg_isready -U postgres -h localhost` every 5 s, timeout 5 s, 10 retries |

The `db` container receives `JWT_SECRET` and `JWT_EXP` as environment variables (sourced from
`JWT_SECRET` and `JWT_EXPIRY` in `docker/.env`) for Supabase internal initialisation. It also
receives `POSTGRES_HOST=/var/run/postgresql` (Unix socket path, used internally) alongside
`PGPORT`, `POSTGRES_PORT`, `PGPASSWORD`, `POSTGRES_PASSWORD`, `PGDATABASE`, and `POSTGRES_DB`.

### Named volumes

| Volume | Used by |
|---|---|
| `redis_data` | `redis` |
| `db_data` | `db` |
| `db_config` | `db` |
| `caddy_config` | `caddy` (currently commented out) |
| `caddy_data` | `caddy` (currently commented out) |

### `telegram_bot`

| Property | Value |
|---|---|
| Build context | repo root |
| Dockerfile | `docker/Dockerfile.telegram` |
| Container name | `${PROJECT_NAME}_telegram_bot` |
| Exposed port | none |
| Restart policy | `unless-stopped` |
| Volume mount | `../integrations:/integrations` |
| Depends on | `api` |

Runs the long-poll Telegram bot from `integrations/telegram/bot.py`. Calls the API
over the internal Compose network (`http://api:8080`) using `X-API-Key` auth; never
routes through the public hostname, so `CF_ACCESS_CLIENT_ID`/`CF_ACCESS_CLIENT_SECRET`
are not needed in the Compose deployment.

**Alternative (non-Docker, Mac Mini):** run `python integrations/telegram/bot.py` as a
launchd service (mirroring `com.brandon.learn-ai`), with `ORCHESTRATION_API_BASE_URL=http://localhost:8080`.

### Depends-on chain

```
db ──┐
     ├──► api ──► celery_worker
redis┘              │
                    └──► telegram_bot
```

---

## 7. Supabase-specific variables

These variables live in `docker/.env` and are consumed either by the Supabase service containers
(via `docker-compose.supabase.yml`) or translated into `DATABASE_*` app variables for `api` and
`celery_worker`.

### Secrets — must change before production

| Variable | Purpose | Default in example |
|---|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL superuser password; also sets `PGPASSWORD` inside `db` container | `your-super-secret-and-long-postgres-password` |
| `JWT_SECRET` | Signs Supabase JWTs (GoTrue auth); must be at least 32 characters | placeholder string |
| `ANON_KEY` | Pre-signed JWT for anonymous client access | demo token (expired) |
| `SERVICE_ROLE_KEY` | Pre-signed JWT with service role privileges; bypass RLS | demo token (expired) |
| `DASHBOARD_USERNAME` | Supabase Studio login username | `supabase` |
| `DASHBOARD_PASSWORD` | Supabase Studio login password | `supabase` |
| `SECRET_KEY_BASE` | Internal Rails-style secret for session signing | placeholder |
| `VAULT_ENC_KEY` | Encryption key for Supabase Vault; minimum 32 characters | placeholder |

### Database connection variables

| Variable | Default | Notes |
|---|---|---|
| `POSTGRES_HOST` | `db` | Docker service name; becomes `DATABASE_HOST` for `api`/`celery_worker` |
| `POSTGRES_DB` | `postgres` | Database name; becomes `DATABASE_NAME` |
| `POSTGRES_PORT` | `5432` | Port; becomes `DATABASE_PORT` |

### Pooler (Supavisor)

| Variable | Default | Purpose |
|---|---|---|
| `POOLER_PROXY_PORT_TRANSACTION` | `6543` | Transaction-mode pooler port |
| `POOLER_DEFAULT_POOL_SIZE` | `20` | Connections per pool |
| `POOLER_MAX_CLIENT_CONN` | `100` | Maximum total client connections |
| `POOLER_TENANT_ID` | `launchpad` | Supavisor tenant identifier |

The application's `DatabaseUtils.get_connection_string()` connects directly to Postgres on port
5432, not through the Supavisor pooler. Use `POOLER_PROXY_PORT_TRANSACTION` only if you route
application connections through Supavisor explicitly.

---

## 8. Local development without Docker

The minimum required external services are **Redis** and **PostgreSQL**. Both must be running and
reachable on localhost before starting the API or worker.

### Minimum `app/.env` for local dev

```ini
PROJECT_NAME=launchpad

DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=postgres
DATABASE_USER=postgres
DATABASE_PASSWORD=your-password-here

REDIS_URL=redis://localhost:6379/0
```

Setting `REDIS_URL` directly bypasses the Docker container hostname derivation in `get_redis_url()`
and points both Celery broker and result backend at the local Redis instance.

Setting `DATABASE_HOST=localhost` directs `DatabaseUtils.get_connection_string()` to the local
Postgres server instead of the `db` Docker container.

### Starting the API and worker side by side

Open two terminal sessions from the repo root:

```bash
# Terminal 1 — FastAPI
cd app && uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

```bash
# Terminal 2 — Celery worker
cd app && uv run celery -A worker.config.celery_app worker --loglevel=info
```

Both processes load `app/.env` independently via `load_dotenv()` at import time. There is no
shared state between them other than the Redis broker and the Postgres database.

### Applying migrations locally

```bash
cd app && alembic upgrade head
```

This requires `DATABASE_*` variables to be set in `app/.env` and Postgres to be reachable.

**pgvector prerequisite:** The first migration (`12a5c7643ab9_enable_pgvector_extension`) runs
`CREATE EXTENSION IF NOT EXISTS vector`. The `supabase/postgres:15.8.1` Docker image ships with
pgvector pre-installed — no extra steps needed in the Docker stack. If you run a plain local
Postgres instance, install the pgvector extension first (e.g. `brew install pgvector` on macOS,
or the `postgresql-<ver>-pgvector` package on Linux) before applying migrations.

### Running Redis locally

If Redis is not already running, start it with:

```bash
redis-server
```

Or with Docker without the full stack:

```bash
docker run -d -p 6379:6379 redis:latest
```

Add the AI provider key(s) for whichever `ModelProvider` values your target workflows use (see
section 3). All other AI provider variables can be left blank.
