---
type: Plan
title: Incremental Execution Observability
description: Persist node-level workflow execution state as it happens, so any downstream consumer can observe a run in progress — not just its terminal result.
---

# Plan — Incremental Execution Observability

**Created:** 2026-06-18
**Status:** Not started
**Catalyst:** bastion (the Rust ops CLI) needs to render live workflow graphs, which surfaced a
gap that is the orchestrator's own to fix. See DECISIONS **D28**.

## TL;DR

Today a workflow's `task_context` is written to the `events` row **exactly once, at the very
end** of execution (`app/worker/tasks.py:44-46` assigns `db_event.task_context` only after
`workflow.run()` returns). While a workflow runs, every node's state lives **in memory** inside
the Celery worker and is invisible to anything reading the database.

This plan makes execution state **observable as it happens**: the framework records per-node
status + timing as each node completes, and the worker persists the `events` row at each node
boundary. This is observability hygiene the orchestrator wants on its own merits (crash
visibility, debuggability, the foundation for resumable runs). bastion is simply the first
consumer.

**The discipline that must hold:** the brain stays deployment-agnostic (D18 / D7). The workflow
loop never opens a DB session itself — persistence is **injected** as a callback the *worker*
supplies via `GenericRepository`. The brain knows nothing about who is watching or where state
is stored. No `if bastion:` anywhere; nothing references bastion in `app/`.

---

## The problem, precisely

`Workflow.run()` (`app/core/workflow.py:124-133`) is a synchronous in-memory loop:

```python
while current_node_class:
    current_node = self.nodes[current_node_class].node
    with self.node_context(current_node_class.__name__):
        task_context = current_node().process(task_context)   # result accrues in memory only
    current_node_class = self._get_next_node_class(current_node_class, task_context)
return task_context
```

The worker then persists once:

```python
# app/worker/tasks.py
task_context = workflow.run(db_event.data).model_dump(mode="json")
db_event.task_context = task_context     # single terminal write
```

Consequence for any DB reader polling mid-run: `task_context` is empty → empty → … → suddenly
complete. There is no intermediate state. A live monitor cannot exist against this model, and
`get_node_output()` notwithstanding, there is no persisted per-node *status* or *timing* at all —
only whatever payload each node chose to stash in `nodes[name]`.

---

## Design principles (non-negotiable)

1. **Brain stays agnostic (D18 / D7).** `Workflow.run()` gains an *optional injected* progress
   callback. Default is a no-op, so unit tests and any non-persisted caller are unaffected. Only
   the worker — the harness layer that already owns the session — wires the callback to
   `GenericRepository`. The first DB call inside a node or inside `workflow.py` would violate this.
2. **`customer_care` stays frozen.** The status/timing envelope is written by the *framework*
   (`node_context`), not by individual nodes. Zero node edits required, so the frozen reference
   workflow keeps working untouched.
3. **Every phase ships with tests (Standing Rule 1).** Each phase below names its test surface.
4. **Additive, not breaking.** New fields are optional/defaulted. Existing `nodes[name]` payloads
   and `get_node_output()` semantics are preserved.
5. **House style.** Python 3.10+ typing (`X | None`, `StrEnum`), module docstring line 1,
   `raise ... from e`, no f-strings in logging, `encoding="utf-8"`.

---

## Phase 1 — Node-boundary persistence + status envelope  *(load-bearing — do first)*

The minimum that makes a run observable. Nothing else in this plan matters without it.

**1a. Status/timing envelope on `TaskContext`.**
Add a first-class field so it survives `model_dump()` and is readable by any consumer:

```python
# app/core/task.py
class NodeStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED  = "failed"

class NodeRun(BaseModel):
    status: NodeStatus = NodeStatus.PENDING
    started_at: str | None = None       # ISO-8601 UTC
    completed_at: str | None = None
    error: str | None = None

class TaskContext(BaseModel):
    ...
    node_runs: dict[str, NodeRun] = Field(default_factory=dict)
```

**1b. Framework stamps the envelope in `node_context`.**
Extend `Workflow.node_context` (`app/core/workflow.py:55-75`) to set `RUNNING` + `started_at` on
entry, `SUCCESS` + `completed_at` on clean exit, and `FAILED` + `error` + `completed_at` in the
`except` branch (before re-raising). Nodes are not modified.

**1c. Injected progress callback.**
`Workflow.run()` accepts `on_progress: Callable[[TaskContext], None] | None = None` and calls it
after each node boundary (and once before the first node, so a freshly-dispatched run shows all
nodes `PENDING`). Default `None` → no-op.

**1d. Worker wires persistence.**
`app/worker/tasks.py` passes an `on_progress` closure that updates `db_event.task_context` via
`GenericRepository` and flushes — at each node boundary, inside the existing transaction. The
terminal write stays as the final, authoritative one.

- **Why (own merits):** a crashed/hung worker now leaves a partial, inspectable trail; "which
  node was it on when it died?" becomes answerable from the DB. Prerequisite for any future
  resume-from-last-good-node capability.
- **Tests:** `node_runs` transitions PENDING→RUNNING→SUCCESS for a happy-path workflow;
  FAILED + error captured when a node raises; `on_progress` invoked once per boundary (assert call
  count/order with a spy); default no-op path leaves behavior identical to today. Add an
  integration test that polls the `events` row mid-run and sees a partial `node_runs`.

---

## Phase 2 — Per-node token + cost capture

`bastion costs` (and any spend dashboard) needs token usage. Today nothing records it.

- Capture token usage + model id from the provider response inside the framework node base
  classes — `AgentNode` (`app/core/nodes/agent.py`) and `ToolUseNode` (`app/core/nodes/tool_use.py`)
  — into a consistent slot (e.g. `NodeRun.usage = {input_tokens, output_tokens, model}` or a
  parallel `usage` field). These are framework-owned nodes, not `customer_care`.
- **Why (own merits):** cost-per-run and cost-per-node become queryable without re-deriving from
  logs; directly feeds capacity/spend awareness.
- **Tests:** a stubbed provider response yields a `NodeRun.usage` with the expected token counts;
  a non-LLM node records no usage.

---

## Phase 3 — Workflow graph introspection endpoint

To draw *pending* nodes (the full DAG) before any has executed, a consumer needs the static graph
from `WorkflowSchema` (`start`, `nodes`, `connections`) — which lives only in Python classes.

- Add read-only `GET /workflows` (list registered types) and `GET /workflows/{type}/graph`
  returning `{nodes: [...], edges: [[from, to], ...]}` serialized from
  `app/workflows/workflow_registry.py`. Node identity = class name (matches the keys used in
  `task_context.nodes` / `node_runs`).
- **Why (own merits):** general introspection — useful for docs generation, debugging a
  workflow's shape, and validating the registry. No consumer-specific coupling.
- **Tests:** endpoint returns the correct node/edge set for `customer_care`; unknown type → 404.

---

## Phase 4 — (Optional) Promoted status column for cheap active-run queries

Finding "what's running right now" currently means scanning + JSON-parsing every `events` row.

- Promote a top-level, indexed `status` column (and optionally `current_node`) onto the `events`
  table via an Alembic migration, written by the same `on_progress` path.
- **Why (own merits):** an indexed `WHERE status = 'running'` instead of a full-table JSON scan;
  matters once the table grows. **Tradeoff:** denormalizes state that otherwise lives in
  `task_context` — cuts slightly against the flexible-JSON design, hence optional and deferred
  until query volume justifies it.
- **Tests:** migration up/down; `status` column tracks the terminal `node_runs` aggregate.

---

## Phase 5 — (Future seam, do not build now) Push instead of poll

Once `on_progress` exists, the same callback is the natural place to *also* publish a lightweight
event (Redis pub/sub or SSE) per node transition — letting consumers subscribe instead of poll.
bastion's own Phase 4 wants exactly this. **Not in scope here.** Recorded only so we don't
architect against it: keep the `on_progress` signature broad enough that an additional publisher
can be layered in without changing the brain.

---

## Sequencing & effort

| Phase | What | Unblocks | Priority |
|---|---|---|---|
| 1 | Node-boundary persistence + status envelope | bastion live monitor — and crash/resume visibility | **Required** |
| 2 | Per-node token/cost capture | bastion costs + spend awareness | High |
| 3 | Graph introspection endpoint | rendering pending nodes; docs/debug | Medium |
| 4 | Promoted indexed `status` column | cheap active-run queries at scale | Optional |
| 5 | Push (pub/sub / SSE) | poll-free consumers | Future seam only |

Phase 1 is small and self-contained — the right thing to land **before** the framework grows more
nodes and workflows, while the `run()` loop and `tasks.py` are still simple to change. Phases 2–3
are independent and can follow in any order. Do this work in this repo, on its own merits;
bastion consumes the result and never reaches back in.

---

## Boundary check (what this plan must NOT do)

- No reference to bastion in `app/` — not in a comment, not in a name, not in a config key.
- No DB/session access inside `workflow.py` or any node — persistence is injected only.
- No change to `customer_care` workflow or its nodes.
- No breaking change to `nodes[name]` payloads or `get_node_output()`.
