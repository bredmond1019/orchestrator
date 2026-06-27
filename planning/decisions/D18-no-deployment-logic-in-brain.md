---
type: Decision
title: D18 — No deployment logic in the brain
description: Where models run and where data lives are injected, never hardcoded; no environment branching inside nodes.
doc_id: D18-no-deployment-logic-in-brain
layer: [engine]
project: orchestrator
status: active
keywords: [deployment agnostic, model injection, GenericRepository, environment branching, portability]
related: [D16-one-brain-two-shells, D33-deployment-agnostic-nodes]
---

# D18 — No deployment logic in the brain

**Decided:** Two things are injected, never hardcoded: where models run and where data lives. The first `if running_locally:` inside a node means two products have started being built.
**Why:** This single discipline keeps the brain portable across any deployment target. Already enforced by the existing abstractions (`model_provider` config, `GenericRepository`).
**Rejected:** Branching on environment inside nodes.
*Note: This principle remains fully load-bearing regardless of D26 — it's good engineering, not just product strategy.*
