---
type: Decision
title: D13 — Per-repo agent context (CLAUDE.md) and daily log (log.md); just-in-time task specs
description: Each repo carries its own CLAUDE.md and log.md; per-block work orders are generated just-in-time with acceptance criteria.
doc_id: D13-per-repo-context-jit-specs
layer: [engine, meta]
project: python-orchestration
status: active
keywords: [CLAUDE.md, per-repo context, log.md, just-in-time specs, acceptance criteria]
related: [context, D11-docs-orientation-vs-state]
---

# D13 — Per-repo agent context (CLAUDE.md) and daily log (log.md); just-in-time task specs

**Decided:** Each code repo carries its own `CLAUDE.md` (how an agent works in that repo — conventions, build/test commands, the tests-ship-with-every-workflow rule) and `log.md` (append-only daily working log, repo-scoped). Per-block work orders are generated **just-in-time** into a `tasks/` folder when a block starts, each with explicit **acceptance criteria** — never pre-written for all blocks.
**Why:** Distinct jobs, no overlap: planning docs describe the endeavor; CLAUDE.md describes working in a repo; DEVLOG records repo history; STATUS rolls up cross-repo state; DECISIONS records why. Generating task specs just-in-time avoids planning-mode procrastination while a fixed template prevents rethinking the convention each time.
**Rejected:** Pre-writing all task specs up front (procrastination trap); a single global devlog (loses repo-local detail); reusing the planning context.md as repo agent-context (different reader, different job — hence separate CLAUDE.md per repo).
