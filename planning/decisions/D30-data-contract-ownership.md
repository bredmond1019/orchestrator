---
type: Decision
title: D30 — Orchestrator owns the versioned data contract
description: The orchestrator publishes a single, versioned data-contract document (docs/data-contract.md) describing the execution state external consumers read, and captures per-node input + serializable output to complete it.
doc_id: D30-data-contract-ownership
layer: [engine, console]
project: python-orchestration
status: active
keywords: [data contract, versioning, orchestrator ownership, external consumer, node input/output]
related: [data-contract, D28-node-level-execution-state]
---

# D30 — Orchestrator owns the versioned data contract

**Decided:** The orchestrator publishes and owns `docs/data-contract.md` (starting at **v1.0.0**) —
the single source of truth for the execution state any external consumer reads: the `events` table,
the `task_context` / `node_runs` JSON, and the HTTP surface. To complete that picture for a live
monitor, the framework now also captures, per node, the **input** (prompt/messages) and a
**JSON-serializable output** — both stamped by the shared LLM node base classes (`AgentNode`,
`ToolUseNode`) alongside the existing token-usage capture. `NodeRun` gains an `input` field; node
output stored under `task_context.nodes[name]` must survive `model_dump(mode="json")` (helper
`to_jsonable()` in `core/task.py`).

**Why:** The bastion CLI is built specifically to observe this orchestrator. The shape it depends on
must be a versioned, owned artifact so the two repos can move together without drift. Per-node input
and guaranteed-serializable output are the two gaps a monitor's detail pane needs; capturing them in
the base classes means new workflows get them for free.

**This preserves D18 / D7 (deployment-agnostic brain):** capture lives in the framework's node base
classes, exactly where token usage already lives — no node-specific or consumer-specific code, no DB
session in the brain, and **no edits to the frozen `customer_care` workflow**. The contract documents
what the orchestrator exposes on its own merits; it never references the consumer.

**Rejected:**
- *Contract as tribal knowledge in code + scattered notes* — caused bastion to encode a
  non-existent relational schema; replaced by one owned, versioned doc.
- *A read API now (`GET /events/{id}`)* — deferred; Hybrid read path keeps direct Postgres for the
  live poll and reserves the endpoint for later (documented, not built).
- *Standardizing a full `{input, output, summary}` envelope on every node* — over-reach for now;
  minimal input + serializable output covers the monitor; the richer envelope is future work.

**Sync:** when any contract shape changes, bump the version + changelog in `docs/data-contract.md`
and re-pin `bastion/docs/data-contract.md`; the `/log-work` checklist enforces this. Cross-repo:
brain **D20**; consumed per bastion **D3**. Builds on **D28** (incremental execution observability).
