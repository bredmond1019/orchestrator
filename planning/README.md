---
type: Index
title: Brandon — Agentic Engineering Practice · Planning Docs
description: Documentation for this phase or specification.
---

# Brandon — Agentic Engineering Practice · Planning Docs

The planning and context documents for becoming an expert AI / agentic / harness engineer and building a practice from it. **Start with `CONTEXT.md`** — it explains everything and routes you to the right file.

## Files, and where to start

| File | What it is | Open it when… |
|---|---|---|
| **CONTEXT.md** | Orientation + router (read first) | You need to understand the project or find the right file |
| **STATUS.md** | Current progress (updated as work happens) | You need to know what's done / what's next |
| **MASTER_PLAN.md** | Strategy: phases, blocks, sequence, business development | You need the *what & when* |
| **Agentic_Engineering_Projects_and_Learning_Plan.md** | Technical: codebase, project library (A–H), Rust appliance shell track | You need the *how* of a project |
| **Test_Plan.md** | Testing standard (Option A) + the four bug fixes | You need the testing scope or per-project rule |
| **DECISIONS.md** | Why settled choices were made (append-only) | You're tempted to relitigate a settled question |
| **tasks/** *(created just-in-time)* | Per-block work orders with acceptance criteria | You're starting a specific block |

## Read order for a newcomer (human or LLM)
1. **CONTEXT.md** — what this is, who Brandon is, governing principles, how to use the set with an LLM
2. **STATUS.md** — where things currently stand
3. The **relevant plan section** for whatever you're doing (don't read all three plans in full — pass the section the question needs)

## How to use this set with an LLM
Pass the **minimum** subset a question needs — never the whole set by reflex. CONTEXT.md's "How to Use This Document Set With an LLM" table gives the exact recipe per query type. Rule of thumb: CONTEXT + STATUS + the one relevant plan section answers almost everything.

## What's *not* here
- **Code repos** live elsewhere. The Python orchestration framework (one monorepo, all Python workflows), the **Rust appliance shell** (the SMB single-binary delivery vehicle — formerly "Rust CLI"), and the website are separate repos, each with its own `CLAUDE.md` (agent conventions) and `DEVLOG.md` (daily log). See DECISIONS.md for the repo strategy (D12–D13, D17).
- An archived Socratic Tutor plan and physics/PhD exploration are intentionally excluded from this set.

---
*This README navigates. `CONTEXT.md` orients. The plans contain. `STATUS.md` tracks. `DECISIONS.md` remembers.*
