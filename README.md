# AI Event System — Orchestration Framework

An event-driven AI pipeline framework. FastAPI accepts events,
persists them to PostgreSQL, and queues them via Celery (Redis broker). A worker
picks up each job and runs it through a **Workflow** — a validated DAG of
**Nodes** — passing a shared `TaskContext` through each step. New workflows are
added as sibling directories alongside the reference `customer_care` workflow.

The framework core is complete and tested (549 passing tests); it is the delivery
vehicle each new automation ships into, not a hardened, deployed product.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- Docker + Docker Compose

## Setup

```bash
# 1. Install dependencies
uv sync

# 2. Copy and fill in env files
cp app/.env.example app/.env          # local dev env
cp docker/.env.example docker/.env    # docker env (set PROJECT_NAME, passwords, API keys)

# 3. Create the Docker network and start services
cd docker && ./start.sh
```

The `docker/.env` controls `PROJECT_NAME` (used as the Docker network/container
prefix), database credentials, and all AI provider keys. See `.env.example` for
the full list.

## Running locally (outside Docker)

Requires Redis and Postgres already running (or started via Docker).

```bash
# API (from app/)
cd app && uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# Worker (from app/)
cd app && uv run celery -A worker.config.celery_app worker --loglevel=info

# Apply migrations (from app/)
cd app && alembic upgrade head
```

## Running via Docker

```bash
cd docker
./start.sh    # build + up (reads docker/.env)
./stop.sh     # tear down
./logs.sh     # tail logs
```

## Tests

```bash
uv run pytest
```

549 tests pass, covering the framework core, shared services, the database layer,
the API, and three production workflows (content pipeline, research agent, proposal
generator). Every new workflow ships with its own tests as it lands. See
`planning/Test_Plan.md` for scope (Option A).

## Sending a test event

```bash
python requests/send_event.py
# or post one of the sample payloads:
# curl -X POST http://localhost:8080/ -H 'Content-Type: application/json' -d @requests/events/refund.json
```

## Directory map

```
orchestration/
├── app/
│   ├── api/                  FastAPI router + endpoint
│   ├── core/
│   │   ├── commands/         CLI tools (createworkflow)
│   │   ├── nodes/            Node, AgentNode, ParallelNode, RouterNode
│   │   ├── schema.py         WorkflowSchema, NodeConfig
│   │   ├── task.py           TaskContext
│   │   ├── validate.py       WorkflowValidator
│   │   └── workflow.py       Workflow base class
│   ├── database/             SQLAlchemy models, GenericRepository, session
│   ├── prompts/              Jinja2 .j2 prompt templates
│   ├── schemas/              Pydantic event schemas (one per workflow)
│   ├── services/             Shared services: embedding, chunking, search,
│   │                         article extraction, transcript, PromptManager
│   ├── worker/               Celery config + task
│   └── workflows/            Workflow implementations + node packages
├── docker/                   Dockerfiles, compose files, start/stop scripts
├── docs/                     app-architecture-overview.md
├── planning/                 Strategy, status, decisions, test plan
├── playground/               Notebooks and visualisation helpers
├── requests/                 Sample event payloads + send script
└── pyproject.toml
```

## Documentation

| File | Contents |
|---|---|
| [docs/api-reference.md](docs/api-reference.md) | Precise class-level reference for every public abstraction in app/core/, app/database/, app/services/, and app/workflows/ that a developer must understand and subclass when writing a new workflow. |
| [docs/configuration.md](docs/configuration.md) | Complete reference for every environment variable, connection string assembly, and Docker service topology so a developer can configure the stack for local development or a Docker deployment without guessing. |
