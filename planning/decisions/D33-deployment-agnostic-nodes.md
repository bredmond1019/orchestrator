---
type: Decision
title: D33 — No deployment logic inside nodes
description: DAG workflow nodes contain workflow logic only; deployment concerns are injected at the harness layer.
doc_id: D33-deployment-agnostic-nodes
layer: [engine]
project: orchestrator
status: active
keywords: [deployment agnostic, node logic, model injection, GenericRepository, environment]
related: [D18-no-deployment-logic-in-brain, app-architecture-overview]
---

# D33 — No deployment logic inside nodes

**Decided:** The orchestration framework is deployment-agnostic. Nodes contain workflow logic only.
**Why:** Deployment targets change (local, Mac Mini, cloud). Coupling deployment config to node code creates lock-in and makes testing harder. The two things that vary by deployment — model choice (per-node `model_provider` config) and persistence (always via `GenericRepository`) — are injected, never hardcoded. The first `if running_locally:` inside a node means two products have started being built.
**Rejected:** Inline environment checks inside nodes — they produce divergent code paths that are impossible to test uniformly.

*Originated in brain D7. Moved to orchestrator 2026-06-22 — this is an orchestrator implementation convention, not a cross-repo mandate.*
