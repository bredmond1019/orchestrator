---
type: Index
title: Developer Documentation Index
description: Index of the developer reference documentation for the python-orchestration-system.
---

# Documentation Index

Developer reference for the orchestration framework. Start here, then open the doc that matches your task.

## Start here

| Doc | Contents |
|---|---|
| [getting-started.md](getting-started.md) | Set up and run the stack — local dev (Homebrew scripts) and Docker/OrbStack path. Start here if you're new. |
| [workflows.md](workflows.md) | What each workflow does, its node DAG, event payload shape, and ready-to-paste curl examples. |
| [scripts.md](scripts.md) | All developer scripts: `dev-setup.sh`, `dev.sh`, `inspect_run.py`, `index_brain.py`. |
| [brain-rag.md](brain-rag.md) | Brain corpus indexing and semantic retrieval — `BrainDocument` model, `index_brain.py`, querying via `DOCUMENT_QA`. |

## Core reference

| Doc | Contents |
|---|---|
| [api-reference.md](api-reference.md) | Class-level reference for every public abstraction in `app/core/`, `app/database/`, `app/services/`, and `app/workflows/` that you subclass when writing a new workflow. |
| [data-contract.md](data-contract.md) | **Versioned** canonical contract for how external consumers (e.g. the `bastion` CLI) read execution state — the `events` table, `task_context`/`node_runs` JSON, and HTTP surface. Bump the version when any shape changes. |
| [configuration.md](configuration.md) | Every environment variable, connection-string assembly, and Docker service topology — configure the stack for local or Docker deployment without guessing. |
| [app-architecture-overview.md](app-architecture-overview.md) | Codebase analysis of the FastAPI → Celery → Workflow DAG → TaskContext architecture. |

## External SDK references

| Doc | Contents |
|---|---|
| [claude-agent-sdk.md](claude-agent-sdk.md) | Complete Python API reference for the Claude Agent SDK — `query()`, `ClaudeSDKClient`, tool definitions, MCP servers, permissions, hooks, and all message/config types. |
| [voyage_ai.md](voyage_ai.md) | Voyage AI Python client reference — API key setup, embedding models (`voyage-4-large`), rerankers, tokenization, async requests, and a quickstart RAG tutorial. |

## Architecture review — how each core abstraction works

| Doc | Contents |
|---|---|
| [architecture_review/workflow.md](architecture_review/workflow.md) | The `Workflow` base class and its execution loop. |
| [architecture_review/task_context.md](architecture_review/task_context.md) | `task.py` / `TaskContext` — node output accumulation and retrieval. |
| [architecture_review/workflow_schema.md](architecture_review/workflow_schema.md) | `WorkflowSchema` & `NodeConfig` — declaring start, nodes, and connections. |
| [architecture_review/workflow_validator.md](architecture_review/workflow_validator.md) | `WorkflowValidator` — validating a workflow graph before execution. |
| [architecture_review/agent_node.md](architecture_review/agent_node.md) | `AgentNode` — the LLM-calling node abstraction. |
| [architecture_review/parallel_node.md](architecture_review/parallel_node.md) | `ParallelNode` — fan-out execution of child nodes. |
| [architecture_review/router_node.md](architecture_review/router_node.md) | `RouterNode` & `BaseRouter` — conditional branching. |
| [architecture_review/prompt_manager.md](architecture_review/prompt_manager.md) | `PromptManager` — loading `.j2` system prompts from `app/prompts/`. |

## Integrations

| Doc | Contents |
|---|---|
| [../integrations/telegram/README.md](../integrations/telegram/README.md) | Telegram bot — setup, Docker Compose deployment, launchd (Mac Mini), network topology (Cloudflare/Tailscale/localhost). |
