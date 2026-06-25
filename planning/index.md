---
type: Index
title: Brandon — Agentic Engineering Practice · Planning Docs
description: Documentation for this phase or specification.
---

# Brandon — Agentic Engineering Practice · Planning Docs

The planning and context documents for becoming an expert AI / agentic / harness engineer and building a practice from it. **Start with `context.md`** — it explains everything and routes you to the right file.

## Files, and where to start

| File | What it is | Open it when… |
|---|---|---|
| **context.md** | Orientation + router (read first) | You need to understand the project or find the right file |
| **status.md** | Current progress (updated as work happens) | You need to know what's done / what's next |
| **master-plan.md** | Strategy + technical: phase sequence, full project library (A–H), the **Role in Bastion** section + program-block crosswalk, the **Bastion Program Blocks** (Engine + Brain work) | You need the *what & when* and the *how* of a project or block |
| **harness.json** | SDLC pipeline validation suite (the checks `/test` runs) | You're wiring or changing what the pipeline validates |
| **decisions/** | Why settled choices were made — one atomic file per decision + `index.md` registry (append-only) | You're tempted to relitigate a settled question |
| **diagnostic-alignment/** | Constraint doc governing Projects B+C output schemas — ties them to The Diagnostic artifact schemas in the brain | You're speccing or reviewing Projects B or C |
| **`<concept>/`** *(created just-in-time)* | Per-concept work orders (`tasks.md`) with pipeline state under `<concept>/sdlc/` | You're starting a specific block (OKF concept-folder model) |

## Read order for a newcomer (human or LLM)
1. **context.md** — what this is, who Brandon is, governing principles, the repo's role in Bastion, how to use the set with an LLM
2. **status.md** — where things currently stand
3. The **relevant `master-plan.md` section** for whatever you're doing (pass the project/block section the question needs, not the whole file)

## How to use this set with an LLM
Pass the **minimum** subset a question needs — never the whole set by reflex. Rule of thumb: context.md + status.md + the one relevant `master-plan.md` section answers almost everything.

## What's *not* here
- **Code repos** live elsewhere. This Python orchestration framework is one monorepo; the **Console** (`bastion`, Rust — a separate Bastion layer that reads this repo, never shares code, D36) and the website are separate repos, each with its own `CLAUDE.md` (agent conventions) and `log.md` (daily log). See `decisions/` for the repo strategy (D12–D13, D17, D36).
- The **cross-repo Bastion program** (this repo is its Engine + Python-half-of-Brain) is planned in the brain: `agentic-portfolio/planning/bastion-product/`.
- An archived Socratic Tutor plan and physics/PhD exploration are intentionally excluded from this set.

---
*This README navigates. `context.md` orients. The plans contain. `status.md` tracks. `decisions/` remembers.*
