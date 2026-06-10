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
| `GEMINI_API_KEY` | string | — | Conditional | `AgentNode` / `ModelProvider.GEMINI` |
| `OLLAMA_BASE_URL` | string | `http://localhost:11434/v1` | Conditional | `AgentNode` / `ModelProvider.OLLAMA` |
| `BEDROCK_AWS_ACCESS_KEY_ID` | string | — | Conditional | `AgentNode` / `ModelProvider.BEDROCK` |
| `BEDROCK_AWS_SECRET_ACCESS_KEY` | string | — | Conditional | `AgentNode` / `ModelProvider.BEDROCK` |
| `BEDROCK_AWS_REGION` | string | — | Conditional | `AgentNode` / `ModelProvider.BEDROCK` |
| `FIRECRAWL_API_KEY` | string | — | Optional | `ArticleExtractionService` Firecrawl fallback |

"Conditional" means the variable is required only when a workflow node is configured with the
corresponding `ModelProvider` value.

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

`ModelProvider` is defined in `app/core/nodes/agent.py` as a `StrEnum`:

```python
class ModelProvider(StrEnum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    OLLAMA = "ollama"
    BEDROCK = "bedrock"
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

### Depends-on chain

```
db ──┐
     ├──► api ──► celery_worker
redis┘
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
