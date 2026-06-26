---
type: Decision
title: D35 — Top-tier models first, then introduce local/open-weight via Project H
description: All first implementations use the best available hosted model; local/open-weight alternatives enter via eval-driven routing in Project H.
doc_id: D35-top-tier-models
layer: [engine]
project: python-orchestration
status: active
keywords: [top-tier models, local models, open-weight, Project H, eval-driven routing]
related: [D8-project-h-offline-eval, D37-local-embeddings-mxbai]
---

# D35 — Top-tier models first, then introduce local/open-weight via Project H

**Decided:** All first implementations use the best available hosted model. Local/open-weight alternatives are introduced in Project H via eval-driven routing.
**Why:** Prototyping on weaker models masks capability gaps and produces misleading benchmarks. Establish the ceiling first, then optimize cost/latency with evidence.
**Rejected:** Premature model tiering — selecting cheaper models up front introduces noise before baselines exist and conflates capability limits with model limits.

*Originated in brain D9. Moved to python-orchestration-system 2026-06-22 — Project H is an orchestrator project; this is an orchestrator-scoped model selection rule.*
