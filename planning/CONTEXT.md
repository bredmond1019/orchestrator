# CONTEXT — Project Overview & Document Router

*The orientation file for this project. Stable — rarely changes. Read this first.*
*For current progress and "what's next," see `STATUS.md` (the volatile companion to this file).*

---

## What This Project Is

This is Brandon's plan to become an **expert in AI Engineering, Agentic Engineering, and Harness Engineering**, and to build a practice (a consulting studio, a job, or a product) from that expertise. The technical spine is a **Python agentic orchestration framework** Brandon already built, on top of which a sequence of progressively harder projects are constructed — each one teaching a sellable competence and producing a portfolio artifact.

**The goal is expertise. Everything else — a studio, a São Paulo job, a product — follows from being genuinely expert.** The plan is built so the same work serves all three outcomes; it does not force a choice between them.

---

## Who Brandon Is (the through-line)

Not someone pivoting into AI — someone who has been building adopted, practical AI-and-automation tools for years, with the judgment to know what's worth shipping. Master's in Pure Mathematics, ~10 years of software engineering, self-taught developer, teacher and builder at the core. Based in São Paulo, bilingual (English native, Portuguese conversational/working), father of two young children, financial runway, no rush.

**The arc to lead with:** Internal Support Dashboard (built solo, 100+ daily cross-functional users, cut support wait times 24–48hr, still in daily use) → Helpscout Support Automation (solo, production RAG + vector + semantic search) → AI Scribe (heavy contribution to production healthcare AI through and past launch) → early Claude Code / Aider experiments (was early, shipped fast, learned where fast AI-building goes wrong) → now: the studio and the harness, applying all of it deliberately.

---

## The Document Set — What Each File Is and When to Read It

There are **seven files** in this planning set. They split cleanly so you only ever pass the subset a question needs. (Code repos and their own context files live elsewhere — see "Repo & per-repo files" below.)

| File | Role | Volatility | Read it when you need… |
|---|---|---|---|
| **README.md** | Navigation / front door | Stable | …a ten-second index of the folder and where to start |
| **CONTEXT.md** (this file) | Orientation + router | Stable | …to understand what the project is, who Brandon is, and where to look for what |
| **STATUS.md** | Current state | Changes weekly | …to know what's done and what's next |
| **Master_Plan_2026.md** | The *what & when* | Stable-ish | …the strategic spine: phases, blocks, sequence, business development, case studies, networking |
| **Agentic_Engineering_Projects_and_Learning_Plan.md** | The *how* | Stable-ish | …technical detail for a specific project, the codebase reference, component reuse |
| **Test_Plan.md** | The *testing standard* | Stable | …to know the testing scope (Option A), the four bug fixes, the per-project testing rule |
| **DECISIONS.md** | Why settled choices were made | Append-only | …to avoid relitigating a decision already made (with its reasoning) |

**Single source of truth:** the two plans (Master, Projects) and the Test Plan own the actual content. CONTEXT routes to them and never duplicates them. STATUS mirrors only the *names* of phases/blocks/projects as a status table — never their content — so nothing drifts. DECISIONS records *why* settled choices were made, so they aren't relitigated.

---

## Repo Strategy & Per-Repo Files (where code and code-context live)

These planning docs are the **parent / top-most context** for the whole endeavor. Code lives in separate repos, each carrying its own scoped context. (Full reasoning: DECISIONS.md, D12–D13.)

**One Python monorepo** holds the orchestration framework and every Python workflow (Projects A–H). Each project is a workflow directory (workflow + nodes + prompts + tests) added *alongside* the existing ones — **not** a clone. Heavy verbatim component reuse across projects is the reason; cloning would fragment the framework. **Separate repos** exist only for different languages / deploy lifecycles: the **Rust CLI**, the **website** (`learn-agentic-ai.com`), and a possible future **Rust runtime**. The test for "new repo?": *does it share the Python framework's code and dependency tree?* If yes, same repo.

**Each repo carries two files this planning set does NOT contain:**
- **`CLAUDE.md`** — repo-scoped *agent context*: how to work in that repo (conventions, build/test commands, the tests-ship-with-every-workflow rule, the keyed-slot convention). This is a **different document** from this planning CONTEXT.md — different reader (an agent editing that repo), different job. Don't conflate them.
- **`DEVLOG.md`** — repo-scoped, append-only *daily working log* ("today: built X, hit bug Y, fixed by Z"). Distinct from STATUS: STATUS is the cross-repo state rollup; DEVLOG is within-repo history.

**The five jobs, no overlap:** planning docs describe the *endeavor* (cross-repo) · `CLAUDE.md` describes *working in a repo* · `DEVLOG.md` records *repo history* · `STATUS.md` rolls up *cross-repo state* · `DECISIONS.md` records *why*.

### Task specs (`tasks/`) — generated just-in-time, never pre-written

When starting a block, generate its work order into `tasks/phaseN-blockX.md` (the output of a "create low-level tasks for Phase X Block Y" query — **saved as a file, not left in chat**). It becomes both the whiteboard input and the work order handed to Claude Code. Do **not** pre-write specs for all blocks (planning-mode procrastination). Fixed template so the convention never needs rethinking:

```
# Task Spec — Phase N, Block/Project X
## Goal (one sentence, from the plan)
## Context pointers (which plan sections + which repo CLAUDE.md)
## Low-level tasks (checklist, sized to ~21 hrs/week across Mon/Wed/Fri)
## Acceptance criteria (REQUIRED — "done when: …", testable conditions)
## Notes / deviations (filled in as work happens)
```

Acceptance criteria are the required field — they're how you *and* an agent know the block is complete, and they close the loop.

### One-line summary of each plan

- **Master Plan** — Sequenced by dependency and competence (not calendar). Phases 0–3, each containing Blocks. Phase 0 = foundation (presence, the Mac Mini harness + site revival, test infra + core hardening, shared services). Phases 1–3 = the project sequence plus business development woven through. Also holds the case studies, the public-narrative rule, the warm leads, and the content plan.
- **Projects & Learning Plan** — The technical reference. Part 1: the existing codebase (component-by-component). Part 2: Phase 0 codebase orientation (5 questions). Part 3: the project library — Projects A→G, plus Project H (eval harness) and a Rust CLI parallel track. Part 4: three product ideas. Part 5: reference tables (components, tech stack, portfolio one-liners, red flags).
- **Test Plan** — Option A scope: test the core engine, infrastructure, and services; do **not** test the reference-only customer-care workflow. Fix four documented production bugs. Then every new workflow ships with its own tests.

---

## The Project Sequence at a Glance

*Names only — full content lives in the plans. Sequence is load-bearing; calendar is not (see Governing Principles).*

**Phase 0 — Foundation:** Block A (presence + codebase ownership) · Block B (Mac Mini agentic harness + revive `learn-agentic-ai.com`) · Block C (test infra + core hardening + 4 bug fixes) · Block D (shared services + first scaffold)

**Phase 1 — Sellable Competence:** Project A (content pipeline) · Project B (research agent) · Project C (proposal generator) · Project D (document Q&A + RAG)

**Phase 2 — Depth + First Paid Work:** Project E (specialization refactor) · Project F (semantic search) · Project H (model eval & routing harness — flexible placement) · First paid diagnostic

**Phase 3 — The Differentiating Build:** Project G (agent memory system)

**Parallel track (anytime after the harness exists):** Rust Harness CLI

**Dependencies that must hold:** read the core before testing it (A→C) · harness before deploying anything (B) · A's components feed C and D · D feeds F and H · Project H needs real nodes to evaluate (after D) · the first paid diagnostic waits for the competence checkpoint, not a date.

---

## Governing Principles (these explain *why* the plans are shaped as they are)

1. **Expertise first; the business/job follows.** The build is the goal, not a means to fast revenue.
2. **Sequence, not calendar.** Blocks and projects have no dates. Work them in order, at whatever pace life allows. Brandon supplies cadence via his separate whiteboard system (THIS WEEK / TODAY); these documents answer "what's next," the whiteboard answers "what today."
3. **Just-in-time building.** Build the thinnest thing that teaches the pattern or meets a real need. Expand only when a prospect, client, or downstream project forces it. Avoid infinite tool-building with no revenue.
4. **Every project ships with its own tests.** The core was hardened in Phase 0 so this discipline could hold from Project A onward.
5. **The competence checkpoint defines "ready," not a finished list.** Ready = *can walk into an unfamiliar SMB and name three automatable workflows in 30 minutes, and explain how to build each.* If the list is done but readiness is in doubt, send one diagnostic offer anyway — don't add a project.
6. **The public-narrative rule (non-disparagement-safe).** In anything public, make Brandon, his work, or his reasons the subject of every sentence — never the previous company's conduct. Never name the company in posts (LinkedIn carries the factual record).
7. **Right tool for the job.** Python for orchestration (I/O-bound). Rust only where it genuinely wins — the CLI now (daily use), a potential inference runtime layer only when a measured limit demands it (not in scope yet).
8. **Resist the impressive-but-unjustified.** Overkill Rust, runtime routers, summary-mill content, claiming work not done — the discriminating "no" is itself the expertise.

---

## How to Use This Document Set With an LLM (or a New Engineer)

The ideology: **pass the minimum context needed for the result — never the whole set by reflex.** Compose the subset the question requires. Recipes:

| You want to ask… | Pass these files | Why this subset |
|---|---|---|
| "What are my tasks for this week?" | CONTEXT + STATUS + the **one relevant block** from the Master Plan | Needs the rules, where you are, and the immediate unit — nothing more |
| "I'm just starting — what low-level tasks this week?" | CONTEXT + STATUS + Master Plan Phase 0 (Blocks A–B) | Same, scoped to the start |
| "Create low-level tasks for Phase X, Block/Project Y" | CONTEXT + that block's section (Master Plan) + the matching project section (Projects Plan) | Pure decomposition of a known unit — **STATUS not needed**. Save output to `tasks/phaseN-blockX.md` with acceptance criteria |
| "Here's what I've done — what's next?" | CONTEXT + STATUS + Master Plan | State drives the answer; plan supplies the next unit |
| "Was this already decided? / why did we choose X?" | CONTEXT + DECISIONS | DECISIONS holds the settled reasoning |
| "Explain this project to a new collaborator" | CONTEXT alone (add one plan if they'll do the work) | Orientation is the whole job |
| "Help me with the technical detail of Project D" | CONTEXT + Projects Plan (Project D section) + Test Plan (per-project rule) | The *how* and the testing standard; skip strategy |
| "Write a LinkedIn post / the return post / résumé" | CONTEXT + Master Plan (case studies + narrative rule + content plan) | Needs the arc and the safety rule, not the codebase |

**When generating task lists:** respect the governing principles above — especially just-in-time scope (don't task out features a real need hasn't summoned yet), tests-per-project, and sequence-not-calendar (produce a *this-week* batch sized to ~21 hrs/week across Mon/Wed/Fri, not a dated schedule).

**When updating progress:** edit `STATUS.md` only. Leave the plans clean. Record deviations and decisions in STATUS's log so the plans stay the stable source of truth.

---

## Fast Facts (for grounding any reader)

- **Time available:** Mon / Wed / Fri, ~10am–5pm (~21 hrs/week). ~70% building, ~30% visibility/networking.
- **Existing infrastructure:** a working Python agentic orchestration framework (FastAPI + Celery + Redis + PostgreSQL; Workflow / Node / TaskContext / AgentNode abstractions). Has zero tests currently — Phase 0 fixes that for the core.
- **Self-hosting:** a Mac Mini becomes the deployment + remote-agent harness; hosts `learn-agentic-ai.com` (bilingual PT/EN, currently down after hitting a Vercel limit).
- **Warm leads:** a CrossFit gym (Jardins — likely first diagnostic: trainer sourcing/scheduling, WhatsApp/Instagram automation) and an e-commerce seller (Mercado Livre — trend-spotting, competitor analysis, multi-CNPJ invoicing).
- **Archived, not in scope here:** an earlier Socratic Tutor app plan and physics/PhD exploration live in separate documents and are intentionally excluded from this set.

---

*This file orients; it does not track. For state, open `STATUS.md`. For content, open the relevant plan. For why a choice was made, open `DECISIONS.md`.*
*Last updated: May 2026*
