# CONTEXT — Project Overview & Document Router

*The orientation file for this project. Stable — rarely changes. Read this first.*
*For current progress and "what's next," see `STATUS.md` (the volatile companion to this file).*

---

## What This Project Is

This is Brandon's plan to become an **expert in AI Engineering, Agentic Engineering, and Harness Engineering**, and to build a **solo contracting practice** from that expertise. The technical spine is a **Python agentic orchestration framework** Brandon already built, on top of which a sequence of progressively harder projects are constructed — each one teaching a sellable competence and producing a portfolio artifact.

**The goal is expertise that funds a flexible life.** Not a studio with employees, not a VC-backed product, not a grind. A solo practice where Brandon works on interesting technical problems, controls his own schedule, and has real time left for music and family. The same project library that builds that expertise also builds the portfolio that wins the contracts.

**The destination is a sustainable solo contracting practice** with 1–2 retainer clients for stable recurring income and a stream of well-scoped project work for interesting problems and skill growth. Target: ~20 billable hours per week at senior AI engineer rates, leaving genuine time and energy for the rest of life. *(See DECISIONS D1, D26.)*

---

## Who Brandon Is (the through-line)

Not someone pivoting into AI — someone who has been building adopted, practical AI-and-automation tools for years, with the judgment to know what's worth shipping. Master's in Pure Mathematics, ~10 years of software engineering, self-taught developer, teacher and builder at the core. Based in São Paulo, bilingual (English native, Portuguese conversational/working), father of two young children, musician.

**The arc to lead with:** Internal Support Dashboard (built solo, 100+ daily cross-functional users, cut support wait times 24–48hr, still in daily use) → Helpscout Support Automation (solo, production RAG + vector + semantic search) → AI Scribe (heavy contribution to production healthcare AI through and past launch) → early Claude Code / Aider experiments (was early, shipped fast, learned where fast AI-building goes wrong) → now: building production-grade agentic systems and taking on contract work that puts those systems to use.

**Private corroborating evidence (do NOT publish with identifying detail):** Brandon formally proposed a knowledge-ingestion + retrieval + memory architecture internally in April 2025. It was declined; he built the foundations on his own time anyway, then left. Useful context for 1:1 conversations — de-identify fully before any public use. *(DECISIONS D10.)*

---

## The Document Set — What Each File Is and When to Read It

There are **seven files** in this planning set. They split cleanly so you only ever pass the subset a question needs. (Code repos and their own context files live elsewhere — see "Repo & per-repo files" below.)

| File | Role | Volatility | Read it when you need… |
|---|---|---|---|
| **README.md** | Navigation / front door | Stable | …a ten-second index of the folder and where to start |
| **CONTEXT.md** (this file) | Orientation + router | Stable | …to understand what the project is, who Brandon is, and where to look for what |
| **STATUS.md** | Current state | Changes weekly | …to know what's done and what's next |
| **MASTER_PLAN.md** | The *what & when* | Stable-ish | …the strategic spine: phases, blocks, sequence, contracting approach, case studies, networking |
| **Agentic_Engineering_Projects_and_Learning_Plan.md** | The *how* | Stable-ish | …technical detail for a specific project, the codebase reference, component reuse. Read `Agentic_Plan_Framing_Note.md` first. |
| **Test_Plan.md** | The *testing standard* | Stable | …to know the testing scope (Option A), the four bug fixes, the per-project testing rule |
| **DECISIONS.md** | Why settled choices were made | Append-only | …to avoid relitigating a decision already made (with its reasoning). Currently **D1–D26**. |

**Single source of truth:** the two plans (Master, Projects) and the Test Plan own the actual content. CONTEXT routes to them and never duplicates them. STATUS mirrors only the *names* of phases/blocks/projects as a status table — never their content — so nothing drifts. DECISIONS records *why* settled choices were made, so they aren't relitigated.

---

## Repo Strategy & Per-Repo Files (where code and code-context live)

These planning docs are the **parent / top-most context** for the whole endeavor. Code lives in separate repos, each carrying its own scoped context. *(Full reasoning: DECISIONS D12–D13.)*

**One Python monorepo** holds the orchestration framework and every Python workflow (Projects A–H). Each project is a workflow directory (workflow + nodes + prompts + tests) added *alongside* the existing ones — **not** a clone. Heavy verbatim component reuse across projects is the reason; cloning would fragment the framework. **Separate repos** exist only for different languages / deploy lifecycles: the **Rust CLI** (personal ops tooling, keeps the skill warm), the **website** (`learn-agentic-ai.com`). The test for "new repo?": *does it share the Python framework's code and dependency tree?* If yes, same repo.

**Each repo carries two files this planning set does NOT contain:**
- **`CLAUDE.md`** — repo-scoped *agent context*: how to work in that repo (conventions, build/test commands, the tests-ship-with-every-workflow rule, the keyed-slot convention). This is a **different document** from this planning CONTEXT.md — different reader (an agent editing that repo), different job. Don't conflate them.
- **`DEVLOG.md`** — repo-scoped, append-only *daily working log*. Distinct from STATUS: STATUS is the cross-repo state rollup; DEVLOG is within-repo history.

**The five jobs, no overlap:** planning docs describe the *endeavor* (cross-repo) · `CLAUDE.md` describes *working in a repo* · `DEVLOG.md` records *repo history* · `STATUS.md` rolls up *cross-repo state* · `DECISIONS.md` records *why*.

### Task specs (`tasks/`) — generated just-in-time, never pre-written

When starting a block, generate its work order into `tasks/phaseN-blockX.md`. It becomes both the whiteboard input and the work order handed to Claude Code. Do **not** pre-write specs for all blocks (planning-mode procrastination). Fixed template:

```
# Task Spec — Phase N, Block/Project X
## Goal (one sentence, from the plan)
## Context pointers (which plan sections + which repo CLAUDE.md)
## Low-level tasks (checklist, sized to ~21 hrs/week across Mon/Wed/Fri)
## Acceptance criteria (REQUIRED — "done when: …", testable conditions)
## Notes / deviations (filled in as work happens)
```

Acceptance criteria are the required field — they're how you *and* an agent know the block is complete.

### One-line summary of each plan

- **Master Plan** — Sequenced by dependency and competence (not calendar). Phases 0–2, each containing Blocks. Phase 0 = foundation (presence, the Mac Mini harness + site revival, test infra + core hardening, shared services). Phases 1–2 = the project sequence plus contracting activity woven through. Covers case studies, public-narrative rule, warm leads, content plan, and the contracting approach.
- **Projects & Learning Plan** — The technical reference. Part 1: the existing codebase (component-by-component). Part 2: Phase 0 codebase orientation (5 questions). Part 3: the project library — Projects A→G plus Project H (eval harness) and the Rust CLI parallel track. Part 4: reference tables (components, tech stack, local model reference, portfolio one-liners, red flags). The Company Brain architecture material is retained as technical depth and a portfolio story, not as an active product build. Read `Agentic_Plan_Framing_Note.md` before using the full plan for task generation.
- **Test Plan** — Option A scope: test the core engine, infrastructure, and services; do **not** test the reference-only customer-care workflow. Fix four documented production bugs. Then every new workflow ships with its own tests.

---

## The Project Sequence at a Glance

*Names only — full content lives in the plans. Sequence is load-bearing; calendar is not.*

**Phase 0 — Foundation:** Block A (presence + codebase ownership) · Block B (Mac Mini harness + revive `learn-agentic-ai.com`) · Block C (test infra + core hardening + 4 bug fixes) · Block D (shared services + first scaffold + clean API)

**Phase 1 — Sellable Competence:** Project A (content pipeline → personal knowledge feed + optional blog) · Project B (research agent) · Project C (proposal generator) · Project D (document Q&A + RAG) → **first paid contract after D**

**Phase 2 — Depth + Ongoing Contracting:** Project E (specialization refactor) · Project F (semantic search) · Project H (model eval & routing harness) · Project G (agent memory system — the differentiating capstone)

**Parallel track (anytime):** Rust CLI — keeps the skill warm, useful personal ops tooling

**Dependencies that must hold:** read the core before testing it · harness before deploying anything · A's components feed C and D · D feeds F and H · Project H needs real nodes to evaluate (after D) · first contract offer waits for the competence checkpoint, not a date.

---

## Governing Principles

1. **Expertise first; contracting follows.** The build is the goal. Contracts are the proof and the income.
2. **Sequence, not calendar.** Blocks and projects have no dates. Work them in order, at whatever pace life allows.
3. **Just-in-time building.** Build the thinnest thing that teaches the pattern or meets a real need. Expand only when a client or downstream project forces it.
4. **Every project ships with its own tests.** The core was hardened in Phase 0 so this discipline holds from Project A onward.
5. **The competence checkpoint defines "ready," not a finished list.** Ready = *can walk into an unfamiliar SMB and name three automatable workflows in 30 minutes, and explain how to build each.* If the checkpoint is met and there's still hesitation, send one offer anyway — don't add a project.
6. **The public-narrative rule (non-disparagement-safe).** In anything public, make Brandon, his work, or his reasons the subject of every sentence — never the previous company's conduct. Never name the company in posts.
7. **Right tool for the job.** Python for orchestration. Rust where it genuinely wins (single-binary CLI tooling, keeping the skill warm). Never the orchestration core.
8. **Resist the impressive-but-unjustified.** The discriminating "no" is itself the expertise. No infinite internal tooling, no product builds without a paying client pulling.
9. **The practice has a ceiling — and that's the point.** Solo contracting at 20 hrs/week is the goal, not a stepping stone to something bigger. Resist scope creep toward hiring, managing, or building a product nobody has paid for yet.

---

## How to Use This Document Set With an LLM (or a New Engineer)

The ideology: **pass the minimum context needed for the result — never the whole set by reflex.**

| You want to ask… | Pass these files | Why this subset |
|---|---|---|
| "What are my tasks for this week?" | CONTEXT + STATUS + the **one relevant block** from the Master Plan | Needs the rules, where you are, and the immediate unit |
| "Create low-level tasks for Phase X, Block/Project Y" | CONTEXT + that block's section (Master Plan) + the matching project section (Projects Plan) | Pure decomposition — STATUS not needed. Save to `tasks/` with acceptance criteria |
| "Here's what I've done — what's next?" | CONTEXT + STATUS + Master Plan | State drives the answer; plan supplies the next unit |
| "Was this already decided? / why did we choose X?" | CONTEXT + DECISIONS | DECISIONS holds the settled reasoning |
| "Help me with the technical detail of Project D" | CONTEXT + Projects Plan (Project D section) + Test Plan | The *how* and the testing standard |
| "Which model should this node use / local vs frontier?" | CONTEXT + Projects Plan (Project H + model reference) + DECISIONS (D8, D19) | The eval-driven routing rule |
| "Write a LinkedIn post / the return post / résumé" | CONTEXT + Master Plan (case studies + narrative rule + content plan) | Needs the arc and the safety rule, not the codebase |
| "Help me scope or pitch a contracting gig" | CONTEXT + Master Plan (contracting section + warm leads) | The offer framing and positioning |

**When generating task lists:** respect the governing principles — especially just-in-time scope, tests-per-project, and sequence-not-calendar (produce a *this-week* batch sized to ~21 hrs/week across Mon/Wed/Fri, not a dated schedule).

**When updating progress:** edit `STATUS.md` only. Leave the plans clean.

---

## Fast Facts (for grounding any reader)

- **Goal:** a solo contracting practice at ~20 billable hrs/week, leaving real time for music and family. 1–2 retainer clients + occasional project work. Senior AI/automation engineering rates.
- **Time available:** Mon / Wed / Fri, ~10am–5pm (~21 hrs/week). ~70% building, ~30% visibility/networking/contracting.
- **Existing infrastructure:** a working Python agentic orchestration framework (FastAPI + Celery + Redis + PostgreSQL; Workflow / Node / TaskContext / AgentNode abstractions). Phase 0 complete — tested, four bugs fixed, shared services built.
- **Self-hosting:** a Mac Mini with two faces. **Public face** (Caddy + Cloudflare DNS): hosts `learn-agentic-ai.com` — accessible to anyone. **Private face** (Tailscale): personal knowledge feed, orchestration API, all private tooling — accessible only from personal devices. The two faces are architecturally separate. *(DECISIONS D23.)*
- **Model strategy:** top-tier models everywhere on the first run-through; then introduce and measure local/open-weight swaps via Project H. Voyage embeddings are a legitimate standing default. Project G consolidation stays on Claude — never local. *(DECISIONS D19.)*
- **Warm leads:** a CrossFit gym (Jardins — trainer sourcing/scheduling, WhatsApp/Instagram automation; good first diagnostic) and an e-commerce seller (Mercado Livre — trend-spotting, competitor analysis, multi-CNPJ invoicing). Both are bounded automation projects, correct for early contracting work.
- **Contracting platforms:** Upwork (fastest to first client, RAG/automation gigs), Toptal (higher rates, rigorous vetting, worth applying once D is shipped), LinkedIn (warm São Paulo relationships), Wellfound (startup contracts).
- **Drafted and ready:** the bilingual return post — EN ("The Builder's Arc") and PT — both subject-on-you, no company named. Update the ending to reflect contracting goal before publishing.
- **Archived, not in scope here:** an earlier Socratic Tutor app plan and physics/PhD exploration live in separate documents and are intentionally excluded from this set.

---

*This file orients; it does not track. For state, open `STATUS.md`. For content, open the relevant plan. For why a choice was made, open `DECISIONS.md`.*
*Last updated: June 2026 — revised goal from studio/product to solo contracting practice (D26).*
