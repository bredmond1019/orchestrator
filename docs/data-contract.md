---
type: Reference
title: Orchestrator ↔ Consumer Data Contract
description: The versioned, canonical contract for how external consumers (e.g. the bastion CLI) read this orchestrator's execution state from PostgreSQL and the HTTP API.
doc_id: data-contract
layer: [engine, console]
project: orchestrator
status: active
keywords: [data contract, versioning, node_runs, task_context, external consumer, bastion, cancellation, abort, budget gate]
related: [D28-node-level-execution-state, D30-data-contract-ownership, app-architecture-overview]
---

# Data Contract — Orchestrator Execution State

**Contract Version: 1.1.0**

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

Consumers are **observers, never writers** of the `events` table itself — no consumer writes to
the DB or persists execution state directly. `bastion` never opens a write connection to
PostgreSQL and never mutates `task_context` by hand.

**This does not forbid a consumer from *triggering* a write the execution runtime performs on its
own behalf.** As of v1.1.0, `bastion` may call `POST /events/{run_id}/abort` (§7) to request that a
live run stop; the runtime — the orchestrator, or `engine-rs`'s embedded execution engine per
brain decision D25 ("bastion triggers, the Engine executes"; see
`agentic-portfolio/docs/decisions/D25-bastion-acts-through-engine.md`) — is what actually flips
the cancellation token and stamps the resulting `metadata["cancellation"]` marker (§5). The
consumer never writes the row itself; it only asks the runtime that owns the row to.

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

**Run-level terminal annotations (as of v1.1.0).** Two outcomes are *not* spelled as a new
`NodeRun.status` value (§6 stays exactly `pending|running|success|failed` — adding a status value
would be a MAJOR bump, and these are properties of the *run*, not any one node's lifecycle).
Instead both are recorded as structured keys under `metadata`, per
`engine-rs/planning/decisions/D6-cancellation-and-budget-semantics.md`:

  - **Cancelled** — a run stopped mid-walk via `POST /events/{run_id}/abort` (§7):
    ```jsonc
    { "metadata": { "cancellation": { "cancelled": true, "at": "<iso8601>" } } }
    ```
    Nodes that never ran because the walk stopped remain `NodeRunStatus::pending` on their own
    `NodeRun` entry — only `metadata.cancellation` marks the run itself as cancelled rather than
    still-in-progress or failed.

  - **Budget-halted** — a run stopped pre-dispatch because a configured cost/token cap was already
    reached:
    ```jsonc
    {
      "metadata": {
        "budget": {
          "halted": true,
          "reason": { "cap": "max_total_tokens" | "max_cost_usd", "spent": <number>, "limit": <number> }
        }
      }
    }
    ```
    The budget cap itself (`max_total_tokens: u64 | null`, `max_cost_usd: f64 | null`) is
    **run-configuration**, supplied by the caller when triggering a run — it is not persisted as
    its own `events` column; it lives only as the input the runtime consults before each dispatch,
    surfacing in `metadata.budget` only once a halt actually occurs. A run with no budget
    configured behaves exactly as it did before v1.1.0: no gate, no `metadata.budget` key.

  Consumers must read these `metadata` keys — not `NodeRunStatus` — to distinguish "cancelled" or
  "budget-halted" from a plain `failed` run.

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

**Conformance fixture.** `tests/fixtures/task_context/research_agent_task_context.json` is a real,
code-path-captured `task_context` (emitted by `scripts/emit_task_context_fixture.py`), not a
hand-authored one — `engine-rs`'s `round_trip.rs` asserts against a checked-in copy of it, and this
repo's own `tests/test_task_context_fixture.py` asserts the live shape still matches it. Re-emit and
update both copies whenever §5/§6 change; see `docs/scripts.md`.

---

## 7. HTTP surface

Mounted at `/` (`app/api/`):

| Method | Path | Request | Response |
|---|---|---|---|
| `POST` | `/events/` | `{ "workflow_type": str, "data": object }` | `202 { "task_id": str, "message": str }` — **trigger** a run |
| `GET` | `/health` | — | `{ "status": str, "version": str }` |
| `GET` | `/workflows` | — | `{ "workflows": [str, ...] }` — registered types |
| `GET` | `/workflows/{type}/graph` | — | `{ "nodes": [str, ...], "edges": [[from, to], ...] }` |
| `POST` | `/events/{run_id}/abort` | — (no body) | `202 { "run_id": str, "status": "aborting" }` — **abort** a live run (new in v1.1.0) |

`GET /workflows/{type}/graph` returns `404` for an unknown type. Node names in `nodes`/`edges` are
class names (§1).

**`POST /events/` authentication:** as of v1.0.1 this endpoint requires an `X-API-Key`
header matching the `ORCHESTRATION_API_KEY` environment variable. The request/response
shape is unchanged. Consumers that previously called this endpoint without auth (e.g.
from a private-network shell script) must add the header. `bastion` is a **read-only
Postgres observer** — it never POSTs to this endpoint — so no re-pin is required.

**`POST /events/{run_id}/abort` (new in v1.1.0).** Requests that a live run stop. Reuses the same
`X-API-Key` gate as `POST /events/`:

- **`401 Unauthorized`** — missing or mismatched `X-API-Key` header (no body).
- **`404 Not Found`** — `run_id` is unknown, or the run has already reached a terminal state
  (success, failure, or a prior cancellation) — `{ "error": "unknown or finished run" }`.
- **`202 Accepted`** — `run_id` names a live run: `{ "run_id": str, "status": "aborting" }`. The
  runtime's cancellation token for that run is triggered synchronously with the response, but the
  run itself stops asynchronously at its **next node boundary** (in-flight node work is not
  interrupted mid-node — see `engine-rs/crates/engine-core/src/nodes/claude_code_step.rs` for the
  one node kind that drops rather than awaits an in-flight future). The eventual terminal state is
  the `metadata.cancellation` marker documented in §5, not a `NodeRunStatus` value.

This endpoint triggers a write (the cancellation flag, and eventually `metadata.cancellation`) but
the caller never performs that write itself — see the reconciled read-path note in §3.

**Reserved (not implemented in v1.x):** `GET /events/{id}`, `GET /events?status=running`.
`event_id` / result-fetch polling remain deferred; this contract version does not add them.

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
| 1.0.1 | 2026-06-23 | Patch clarification: `POST /events/` now requires `X-API-Key` auth (shape unchanged). `event_id`/`GET /events/{id}` remain deferred. `bastion` (read-only Postgres observer, never POSTs) needs no re-pin. |
| 1.1.0 | 2026-07-16 | Minor: new `POST /events/{run_id}/abort` endpoint (§7) — 401/404/202, reuses the `X-API-Key` gate. New run-level `metadata.cancellation` and `metadata.budget` annotations (§5) for cancelled and budget-halted runs, spelled in `metadata` rather than a new `NodeRunStatus` value (§6 unchanged). §3's "observers, never writers" prose reconciled: consumers may trigger a runtime-owned write (the abort) without writing the row themselves (D25: bastion triggers, the Engine executes). `bastion` must re-pin — see `bastion/docs/data-contract.md`. |
