---
type: Decision
title: "D20 — Self-improvement boundary: agents evolve what's gated; new capability enters by PR; the gates are never self-approved"
description: Agents may evolve prompts/routing/memory and compose workflows; new node code enters only by human-reviewed PR; validator, test-runner, rubric, and consolidation prompt are human-owned gates.
doc_id: D20-self-improvement-boundary
layer: [engine]
project: python-orchestration
status: active
keywords: [self-improvement, agent safety, human review, PR gate, validator]
related: [master-plan]
---

# D20 — Self-improvement boundary: agents evolve what's gated; new capability enters by PR; the gates are never self-approved

**Decided:** A permanent boundary governs self-evolving capability. The system may freely evolve prompts, routing, memory, and compose new workflows over trusted nodes. New node code enters only through human-reviewed PRs. The validator, test-runner, eval rubric, and consolidation prompt are human-owned gates.
**Why:** The seam between "every action needs approval" (unusable) and "no action needs approval" (unsafe) — the same seam Git/GitHub already found.
*Note: This is a Phase 3+ consideration, retained as a principle for if/when self-improving features are ever built.*
