---
type: Reference
title: Orchestrator ↔ Consumer Data Contract
description: The versioned, canonical contract for how external consumers (e.g. the bastion CLI) read this orchestrator's execution state from PostgreSQL and the HTTP API.
---

# Data Contract — Orchestrator Execution State

**Contract Version: 1.0.0**

This is the **single source of truth** for the shape any external consumer reads to observe a
workflow run — the `events` table, the `task_context` / `node_runs` JSON, and the HTTP surface.
The orchestrator **owns** this document. Consumers (e.g. [`bastion`](../../bastion)) reference and
*pin* it; they never fork it. When any shape here changes, bump the version and add a changelog row
(see [Versioning](#versioning)).

> This contract exists on the orchestrator's own merits (crash visibility, debuggability,
> resume foundation — see `planning/decisions/D28-node-level-execution-state.md`). It documents
> what the orchestrator already exposes; it does not couple the framework to any consumer.

---

## 1. Identity rule (load-bearing)

**Node identity = the node's Python class name** (e.g. `AnalyzeTicketNode`). It is the join key
across *every* source in this contract:

- the keys of `task_context.nodes`
- the keys of `task_context.node_runs`
- the `nodes` / `edges` of the graph-introspection endpoint

A consumer reconstructs a live run by joining these three on the class name.

---

## 2. Two-source merge model

A live monitor needs two things the orchestrator exposes separately:

| Need | Source | Frequency |
|---|---|---|
| DAG shape — which nodes exist, which points to which (incl. *pending* nodes) | `GET /workflows/{type}/graph` (HTTP) | once per workflow type (static) |
| Live per-node state — status, timing, error, tokens, input | `events.task_context.node_runs` (PostgreSQL) | poll per run |

The orchestrator seeds **every** node `PENDING` and persists that snapshot *before the first node
executes*, then re-persists at every node boundary. So from the first poll, `node_runs` already
contains all nodes; the graph endpoint supplies the **edges** (`node_runs` carries no edges).

---

## 3. Read path (Hybrid)

- **Now:** consumers read PostgreSQL **directly** (read-only) for the live poll — cheap and
  high-frequency. This is the supported path for v1.x.
- **Reserved (not built):** an HTTP read API — `GET /events/{id}` and a list-active-runs endpoint
  — is reserved for a future minor version, to be added only if direct DB-schema coupling becomes a
  problem. Both sides should architect toward it but not depend on it yet.

Consumers are **observers, never writers** — no consumer writes to the DB or triggers
orchestrator-side persistence.

---

## 4. PostgreSQL — the `events` table

Defined in `app/database/event.py`. One row per workflow run. There are **no** relational
`workflow_runs` / `node_states` tables; all run/node state lives in the `task_context` JSON.

| Column | Type | Meaning |
|---|---|---|
| `id` | UUID (`uuid1`) | run id |
| `workflow_type` | `varchar(150)` | registry key; selects the graph + schema |
| `data` | JSON | the **run input** (the original event payload) |
| `task_context` | JSON | full execution state — see §5 |
| `created_at` | timestamp | row creation |
| `updated_at` | timestamp | last write (advances at every node boundary) |

**Active-run discovery:** scan `events` for rows whose `task_context.node_runs` values are not all
terminal (`success`/`failed`). (A promoted indexed `status` column is a deferred optimization —
orchestrator plan Phase 4 — not part of v1.0.0.)

---

## 5. `task_context` JSON

The JSON serialization of `TaskContext` (`app/core/task.py`) via `model_dump(mode="json")`:

```jsonc
{
  "event":    { ... },              // parsed event (the per-workflow Pydantic schema)
  "nodes":    { "<ClassName>": { ... } },   // per-node OUTPUT, keyed by class name
  "metadata": { ... },              // workflow-level metadata
  "node_runs":{ "<ClassName>": NodeRun }    // per-node execution envelope (§6)
}
```

- **`nodes[<ClassName>]`** holds each node's **output**. Contract rule: whatever a node stores here
  **must be JSON-serializable**. The framework LLM base classes store a serializable `output` key
  for free (`AgentNode` → `result.output` dumped; `ToolUseNode` → final text); non-LLM node authors
  must store plain dicts/scalars (use `to_jsonable()` in `app/core/task.py` if dumping a model).
- **`metadata`** — the transient runtime node registry stashed under `metadata["nodes"]` during a
  run is **stripped on serialization** (it is not JSON-serializable); consumers never see it.
- **`event`** — the run input is also available verbatim in the `events.data` column.

---

## 6. `NodeRun` envelope

Per-node execution record (`app/core/task.py`), keyed by class name in `node_runs`:

| Field | Type | Meaning |
|---|---|---|
| `status` | string enum | `pending` \| `running` \| `success` \| `failed` (lowercase) |
| `started_at` | string \| null | ISO-8601 UTC, set on entry |
| `completed_at` | string \| null | ISO-8601 UTC, set on success/failure |
| `error` | string \| null | stringified exception on failure |
| `input` | any \| null | prompt/messages sent (LLM nodes); JSON-serializable; null otherwise |
| `usage` | object \| null | `{ "input_tokens": int\|null, "output_tokens": int\|null, "model": string }` for LLM nodes; null for non-LLM nodes |

Status lifecycle: `pending` (seeded) → `running` (on entry) → `success` \| `failed` (on exit).

**Detail-pane field provenance** (where a consumer reads each thing it displays):

| Display | Source |
|---|---|
| node status / timing | `node_runs[name].{status,started_at,completed_at}` |
| node error | `node_runs[name].error` |
| node input (prompt) | `node_runs[name].input` |
| node tokens / model | `node_runs[name].usage` |
| node output | `nodes[name]` (look for the `output` key) |
| run input | `events.data` |

---

## 7. HTTP surface

Mounted at `/` (`app/api/`):

| Method | Path | Request | Response |
|---|---|---|---|
| `POST` | `/` | `{ "workflow_type": str, "data": object }` | `202 { "task_id": str, "message": str }` — **trigger** a run |
| `GET` | `/health` | — | `{ "status": str, "version": str }` |
| `GET` | `/workflows` | — | `{ "workflows": [str, ...] }` — registered types |
| `GET` | `/workflows/{type}/graph` | — | `{ "nodes": [str, ...], "edges": [[from, to], ...] }` |

`GET /workflows/{type}/graph` returns `404` for an unknown type. Node names in `nodes`/`edges` are
class names (§1).

**Reserved (not implemented in v1.x):** `GET /events/{id}`, `GET /events?status=running`.

---

## 8. Versioning

Semver on this document:

- **Patch** — wording/clarification, no shape change.
- **Minor** — additive, backward-compatible (a new optional field, a new endpoint, the reserved
  read API landing).
- **Major** — a breaking change (rename/remove a field, change a type or status value, change an
  endpoint path or payload).

When you change any shape here: bump the version in the header, add a row below, and **re-pin the
consumer** (`bastion/docs/data-contract.md`). The `/log-work` command in both repos carries a
checklist step prompting this.

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-06-20 | Initial contract: `events` table, `task_context`/`node_runs` (status, timing, error, **input**, usage), serializable-output rule, HTTP surface, Hybrid read path, reserved read API. |
