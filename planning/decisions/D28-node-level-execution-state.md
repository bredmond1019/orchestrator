---
type: Decision
title: D28 — Persist node-level execution state incrementally
description: Workflow execution state is recorded per-node as it happens, via an injected persistence callback the worker supplies — the brain never opens a DB session itself.
doc_id: D28-node-level-execution-state
layer: [engine]
project: python-orchestration
status: active
keywords: [node_runs, incremental persistence, on_progress callback, TaskContext, execution state]
related: [data-contract, D30-data-contract-ownership, app-architecture-overview]
---

# D28 — Persist node-level execution state incrementally

**Decided:** The framework records per-node status + timing (`TaskContext.node_runs`) as each node
completes, and the Celery worker persists the `events` row at each node boundary — not only once
at the end of `workflow.run()`. Persistence is **injected** into `Workflow.run()` as an optional
`on_progress` callback the worker wires to `GenericRepository`; the default is a no-op.

**Why:** Until now `task_context` was written exactly once, at terminal completion
(`worker/tasks.py`), so a run in progress was invisible to anything reading the database and a
crashed worker left no trail of where it died. Incremental persistence gives crash visibility,
debuggability, and the foundation for resume-from-last-good-node — all wins for the orchestrator
on its own merits. It also happens to be the prerequisite for the bastion live monitor, which was
the catalyst that surfaced the gap.

**This preserves D18 / D7 (deployment-agnostic brain):** the workflow loop and nodes never touch a
session — the worker (harness layer) is the only thing that knows persistence exists, exactly as
`GenericRepository` and `model_provider` injection already work. The status envelope is stamped by
the framework's `node_context`, so individual nodes — including the frozen `customer_care`
reference — need zero changes.

**Rejected:**
- *Terminal-only persistence (status quo)* — makes mid-run observation impossible and loses all
  crash-state.
- *Opening a DB session inside `workflow.py` / nodes* — would couple the brain to persistence and
  deployment, violating D18.
- *A bastion-specific writer or table* — bastion is a read-only consumer; the orchestrator exposes
  state on its own merits and never references the consumer.

**Plan:** `planning/plans/incremental-execution-observability.md` (Phases 1–5; Phase 1 is the
load-bearing slice).
