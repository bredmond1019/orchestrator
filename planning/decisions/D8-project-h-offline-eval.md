---
type: Decision
title: D8 — Project H (model eval) is offline evaluation, NOT a runtime router
description: The eval harness produces per-node routing decisions baked in at design time, not per-request at runtime.
doc_id: D8-project-h-offline-eval
layer: [engine]
project: orchestrator
status: active
keywords: [Project H, model eval, offline evaluation, per-node routing, eval harness]
related: [D35-top-tier-models, master-plan]
---

# D8 — Project H (model eval) is offline evaluation, NOT a runtime router

**Decided:** The eval harness runs occasionally to *produce* per-node routing decisions that bake into each node's `model_provider` at design time. It does not select models per-request at runtime.
**Why:** Static per-node decisions capture most of the value; per-request runtime selection adds latency and complexity for marginal benefit. The expert skill is the measured routing *judgment*, not dynamic switching.
**Rejected:** A runtime model router — overkill; the impressive-but-unjustified trap.
