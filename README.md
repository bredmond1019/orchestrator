---
type: Index
title: Python Orchestration System — README
description: Event-driven AI pipeline framework — FastAPI, Celery, Workflow DAG, TaskContext. Entry point for the repo.
doc_id: readme
layer: [engine]
project: orchestrator
status: active
keywords: [orchestration framework, FastAPI, Celery, workflow DAG, quick start]
related: [docs-index, app-architecture-overview, getting-started]
---

# AI Event System — Orchestration Framework

An event-driven AI pipeline framework. FastAPI accepts events,
persists them to PostgreSQL, and queues them via Celery (Redis broker). A worker
picks up each job and runs it through a **Workflow** — a validated DAG of
**Nodes** — passing a shared `TaskContext` through each step. New workflows are
added as sibling directories alongside the reference `customer_care` workflow.

The framework core is complete and tested (712 passing tests); it is the delivery
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

712 tests pass, covering the framework core, shared services, the database layer,
the API, and five production workflows (content pipeline, research agent, proposal
generator, document ingest, document Q&A). Every new workflow ships with its own
tests as it lands. See `planning/Test_Plan.md` for scope (Option A).

## Sending a test event

`POST /events/` requires an `X-API-Key` header (set `ORCHESTRATION_API_KEY` in `app/.env`).

```bash
# Content pipeline — summarize a YouTube video
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: <your ORCHESTRATION_API_KEY>' \
  -d '{"workflow_type": "CONTENT_PIPELINE", "data": {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "make_blog": false}}'
```

See `docs/workflows.md` for all workflow types and example payloads.

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
├── docs/                     Developer reference (see Documentation table below)
├── planning/                 Strategy, status, decisions, test plan
├── playground/               Notebooks and visualisation helpers
├── integrations/             Standalone integrations (Telegram bot)
├── requests/                 Sample event payloads + send script
└── pyproject.toml
```

## Documentation

| File | Contents |
|---|---|
| [docs/getting-started.md](docs/getting-started.md) | Local dev setup (Homebrew scripts) and Docker/OrbStack path — the fast path to a running stack. |
| [docs/workflows.md](docs/workflows.md) | What each workflow does, its node DAG, event payload, and ready-to-paste curl examples. |
| [docs/scripts.md](docs/scripts.md) | Developer scripts: `dev-setup.sh`, `dev.sh`, `inspect_run.py`, `index_brain.py`. |
| [docs/brain-rag.md](docs/brain-rag.md) | Brain corpus indexing and semantic retrieval via `BrainDocument` + `index_brain.py`. |
| [docs/api-reference.md](docs/api-reference.md) | Class-level reference for every public abstraction in `app/core/`, `app/database/`, `app/services/`, and `app/workflows/` — the primary reference when writing a new workflow. |
| [docs/configuration.md](docs/configuration.md) | Every environment variable, connection string, and Docker service topology. |
| [docs/app-architecture-overview.md](docs/app-architecture-overview.md) | FastAPI → Celery → Workflow DAG → TaskContext architecture deep-dive. |
| [docs/data-contract.md](docs/data-contract.md) | Versioned contract for how external consumers (e.g. `bastion` CLI) read execution state. |
| [integrations/telegram/README.md](integrations/telegram/README.md) | Telegram bot setup, Docker Compose deployment, Mac Mini launchd, network topology. |
| [docs/index.md](docs/index.md) | Full documentation index. |
