---
type: Index
title: Developer Documentation Index
description: Index of the developer reference documentation for the python-orchestration-system.
---

# Documentation Index

Developer reference for the orchestration framework. Start here, then open the doc that matches your task.

## Core reference

| Doc | Contents |
|---|---|
| [api-reference.md](api-reference.md) | Class-level reference for every public abstraction in `app/core/`, `app/database/`, `app/services/`, and `app/workflows/` that you subclass when writing a new workflow. |
| [data-contract.md](data-contract.md) | **Versioned** canonical contract for how external consumers (e.g. the `bastion` CLI) read execution state — the `events` table, `task_context`/`node_runs` JSON, and HTTP surface. Bump the version when any shape changes. |
| [configuration.md](configuration.md) | Every environment variable, connection-string assembly, and Docker service topology — configure the stack for local or Docker deployment without guessing. |
| [app-architecture-overview.md](app-architecture-overview.md) | Codebase analysis of the FastAPI → Celery → Workflow DAG → TaskContext architecture. |

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

## Agentic workflows (SDLC pipeline)

| Doc | Contents |
|---|---|
| [agentic-workflows/sdlc-workflow.md](agentic-workflows/sdlc-workflow.md) | The end-to-end SDLC workflow pipeline and its stages. |
| [agentic-workflows/sdlc-orchestration.md](agentic-workflows/sdlc-orchestration.md) | `/sdlc-block` — orchestrating a block through dependency-ordered waves of parallel task pipelines. |
| [agentic-workflows/sdlc-dynamic-workflows.md](agentic-workflows/sdlc-dynamic-workflows.md) | The dynamic SDLC workflow scripts and how they compose pipeline stages at runtime. |
