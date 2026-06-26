---
type: Decision
title: "D11 — Documentation: separate orientation from state; minimum-context by default"
description: Five planning files with distinct jobs; pass only the subset a question needs; CONTEXT routes, STATUS mirrors names only.
doc_id: D11-docs-orientation-vs-state
layer: [engine, meta]
project: python-orchestration
status: active
keywords: [documentation structure, context vs state, minimum context, planning files]
related: [context, status, planning-index]
---

# D11 — Documentation: separate orientation from state; minimum-context by default

**Decided:** Five planning files with distinct jobs — CONTEXT (orientation/router, stable), STATUS (state, volatile), the three plans (content), plus README (navigation) and this DECISIONS file. Pass only the subset a question needs. CONTEXT routes and never duplicates the plans; STATUS mirrors only names, never content.
**Why:** Orientation and state age differently; folding them together makes the whole thing feel stale on every task completion. Single-source-of-truth prevents drift.
**Rejected:** One fat context.md containing everything — goes stale fast, forces passing bloat for narrow queries.
