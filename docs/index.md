---
type: Index
title: Developer Documentation Index
description: Index of the developer reference documentation for Synapse, the Brain layer.
doc_id: docs-index
layer: [brain]
project: synapse
status: active
keywords: [docs index, developer reference, brain, capabilities, getting-started, API reference]
related: [capabilities, api-reference, app-architecture-overview, brain-rag, workflows, getting-started, data-contract, workspace-contract, memory, mcp-contract, node-model-comparison]
---

# Documentation Index

Synapse is the **Brain** layer of Bastion — the corpus, embeddings, structural graph, memory and
retrieval. This is the file listing. **If you want to know what the system can do and what to type,
start at [capabilities.md](capabilities.md), not here.**

## Start here

| Doc | One line |
|---|---|
| [capabilities.md](capabilities.md) | **Everything Synapse can do, and how to run it** — workflows, the `syn` CLI, the HTTP API, ops routines. |
| [getting-started.md](getting-started.md) | Get the stack running — local Homebrew path or Docker/OrbStack path. |
| [app-architecture-overview.md](app-architecture-overview.md) | How FastAPI → Celery → Workflow DAG → TaskContext fits together. |

## Using the brain

| Doc | One line |
|---|---|
| [brain-rag.md](brain-rag.md) | How the corpus is indexed and searched — chunking, hybrid retrieval, age decay, the abstain gate. |
| [memory.md](memory.md) | The memory layer — episodes, semantic memory, consolidation, confidence decay. |
| [workflows.md](workflows.md) | The four workflows in detail — node DAGs, event payloads, curl examples. |
| [scripts.md](scripts.md) | Every script and every `syn` subcommand, with full flags. |

## Contracts (versioned — bump before you change a shape)

| Doc | One line |
|---|---|
| [data-contract.md](data-contract.md) | How external consumers read execution state: the `events` table, `task_context`, the HTTP surface. |
| [workspace-contract.md](workspace-contract.md) | The shared knowledge-workspace convention — names, resolution precedence, OKF corpus rules. |
| [mcp-contract.md](mcp-contract.md) | The Brain MCP server's tool schemas, result shape, and error envelope. |

## Building on the framework

| Doc | One line |
|---|---|
| [api-reference.md](api-reference.md) | Class-level reference for every abstraction you subclass when writing a node or workflow. |
| [configuration.md](configuration.md) | Every environment variable, connection string, and Docker service. |
| [node-model-comparison.md](./node-model-comparison.md) | Which model to run on which node, and what local hardware allows. |

## How each core abstraction works

Deeper walkthroughs of the pieces `api-reference.md` summarizes.

| Doc | One line |
|---|---|
| [architecture_review/workflow.md](architecture_review/workflow.md) | The `Workflow` base class and its execution loop. |
| [architecture_review/task_context.md](architecture_review/task_context.md) | `TaskContext` — how node outputs accumulate and are read back. |
| [architecture_review/workflow_schema.md](architecture_review/workflow_schema.md) | `WorkflowSchema` & `NodeConfig` — declaring start, nodes, connections. |
| [architecture_review/workflow_validator.md](architecture_review/workflow_validator.md) | `WorkflowValidator` — checking a graph before it runs. |
| [architecture_review/agent_node.md](architecture_review/agent_node.md) | `AgentNode` — the LLM-calling node. |
| [architecture_review/parallel_node.md](architecture_review/parallel_node.md) | `ParallelNode` — fan-out execution. |
| [architecture_review/router_node.md](architecture_review/router_node.md) | `RouterNode` & `BaseRouter` — conditional branching. |
| [architecture_review/prompt_manager.md](architecture_review/prompt_manager.md) | `PromptManager` — loading `.j2` prompts from `app/prompts/`. |

## External SDK references

Vendored third-party API docs, kept here so agents can read them offline.

| Doc | One line |
|---|---|
| [claude-agent-sdk.md](claude-agent-sdk.md) | Claude Agent SDK Python API — `query()`, `ClaudeSDKClient`, tools, MCP, hooks. |
| [voyage_ai.md](voyage_ai.md) | Voyage AI client — embedding models, rerankers, tokenization. |
| [logfire.md](logfire.md) | Logfire observability — instrumenting FastAPI + Celery, and querying traces. |
