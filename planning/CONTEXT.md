# CONTEXT — Project Overview & Document Router

*The orientation file for this project. Stable — rarely changes. Read this first.*
*For current progress and "what's next," see `STATUS.md` (the volatile companion to this file).*

---

## What This Project Is

This is Brandon's plan to become an **expert in AI Engineering, Agentic Engineering, and Harness Engineering**, and to build a practice from that expertise. The technical spine is a **Python agentic orchestration framework** Brandon already built, on top of which a sequence of progressively harder projects are constructed — each one teaching a sellable competence and producing a portfolio artifact.

**The goal is expertise. Everything else follows from being genuinely expert.** The plan is built so the same work serves multiple outcomes; it does not force a choice between them.

**As of June 2026 the destination has a name: the Company Brain.** A system that ingests a company's scattered knowledge (heads, email, Slack, tickets, docs), structures it, *keeps it current*, and emits an executable skills file agents can act on. This is not a pivot — it is the name for where the project library was already converging: **Project D** is its retrieval half (already shipped in production as Helpscout), **Project G** is its "keeps it current" engine (memory with confidence decay + contradiction handling), and the skills-file output is the harness's Claude Code skills primitive. The buyer wedge is **fast-growing SMBs at the ~30–80-employee inflection, privacy-first** ("your knowledge never leaves the building"), with **enterprise welcomed as a later expansion** served by the same core. A **job remains a fine outcome and identical work serves it** — nothing is foreclosed — but decisions now prune faster against a named destination than against three open doors. (Full reasoning: DECISIONS D14–D19.)

---

## Who Brandon Is (the through-line)

Not someone pivoting into AI — someone who has been building adopted, practical AI-and-automation tools for years, with the judgment to know what's worth shipping. Master's in Pure Mathematics, ~10 years of software engineering, self-taught developer, teacher and builder at the core. Based in São Paulo, bilingual (English native, Portuguese conversational/working), father of two young children, financial runway, no rush.

**The arc to lead with:** Internal Support Dashboard (built solo, 100+ daily cross-functional users, cut support wait times 24–48hr, still in daily use — *a primitive company brain*) → Helpscout Support Automation (solo, production RAG + vector + semantic search — *the Company Brain's retrieval half, already shipped*) → AI Scribe (heavy contribution to production healthcare AI through and past launch) → early Claude Code / Aider experiments (was early, shipped fast, learned where fast AI-building goes wrong) → now: the Company Brain and the harness, applying all of it deliberately.

**Private corroborating evidence (do NOT publish with identifying detail):** Brandon formally proposed the Company Brain — by that architecture, multi-source retrieval + synthesis + source attribution + a learn-and-improve loop — *internally, in April 2025*. It was declined as not-a-priority; he built the foundations (this orchestration framework, the Helpscout automation) on his own time anyway, then left. This is firsthand, paper-trailed founder-market fit and the spine of the return post — but it names a company, so it is private evidence and one-on-one conversation material only. De-identify fully if any of it becomes public content (DECISIONS D10; the return post draft handles this correctly).

---

## The Document Set — What Each File Is and When to Read It

There are **seven files** in this planning set. They split cleanly so you only ever pass the subset a question needs. (Code repos and their own context files live elsewhere — see "Repo & per-repo files" below.)

| File | Role | Volatility | Read it when you need… |
|---|---|---|---|
| **README.md** | Navigation / front door | Stable | …a ten-second index of the folder and where to start |
| **CONTEXT.md** (this file) | Orientation + router | Stable | …to understand what the project is, who Brandon is, and where to look for what |
| **STATUS.md** | Current state | Changes weekly | …to know what's done and what's next |
| **MASTER_PLAN.md** | The *what & when* | Stable-ish | …the strategic spine: phases, blocks, sequence, business development, case studies, networking |
| **Agentic_Engineering_Projects_and_Learning_Plan.md** | The *how* | Stable-ish | …technical detail for a specific project, the codebase reference, component reuse |
| **Test_Plan.md** | The *testing standard* | Stable | …to know the testing scope (Option A), the four bug fixes, the per-project testing rule |
| **DECISIONS.md** | Why settled choices were made | Append-only | …to avoid relitigating a decision already made (with its reasoning). Currently **D1–D20**; D14–D20 cover the Company Brain destination, the one-brain-two-shells architecture, and the self-improvement boundary |

**Single source of truth:** the two plans (Master, Projects) and the Test Plan own the actual content. CONTEXT routes to them and never duplicates them. STATUS mirrors only the *names* of phases/blocks/projects as a status table — never their content — so nothing drifts. DECISIONS records *why* settled choices were made, so they aren't relitigated.

---

## Repo Strategy & Per-Repo Files (where code and code-context live)

These planning docs are the **parent / top-most context** for the whole endeavor. Code lives in separate repos, each carrying its own scoped context. (Full reasoning: DECISIONS.md, D12–D13.)

**One Python monorepo** holds the orchestration framework and every Python workflow (Projects A–H) — *this is the deployment-agnostic brain*. Each project is a workflow directory (workflow + nodes + prompts + tests) added *alongside* the existing ones — **not** a clone. Heavy verbatim component reuse across projects is the reason; cloning would fragment the framework. **Separate repos** exist only for different languages / deploy lifecycles: the **Rust appliance shell** (the SMB single-binary delivery vehicle, formerly "Rust CLI"), the **website** (`learn-agentic-ai.com`), a possible future **Rust runtime**, and a future **enterprise shell** (cloud control plane — only when an enterprise pulls). The test for "new repo?": *does it share the Python framework's code and dependency tree?* If yes, same repo. Note the architecture intent (DECISIONS D16): the brain stays one codebase; the shells are separate repos that drive it over its HTTP API, never forks of it.

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

- **Master Plan** — Sequenced by dependency and competence (not calendar). Phases 0–3, each containing Blocks. Phase 0 = foundation (presence, the Mac Mini harness + site revival, test infra + core hardening, shared services + clean API contract). Phases 1–3 = the project sequence plus business development woven through. Now also names the **Company Brain destination**, the **one-brain-two-shells architecture** (deployment-agnostic Python brain + Rust SMB appliance shell + later enterprise shell), the case studies, the public-narrative rule, the warm leads, and the content plan (including the drafted return post).
- **Projects & Learning Plan** — The technical reference. Part 1: the existing codebase (component-by-component) — *the brain of the Company Brain*. Part 2: Phase 0 codebase orientation (5 questions). Part 3: the project library — Projects A→G, plus Project H (eval harness) and the **Rust appliance shell** parallel track. Part 4: the Company Brain assembly + the three product ideas. **Part 5: the self-improving system capstone** (Phase 3+ — self-correction / self-evolution / self-construction, governed by D20). Part 6: reference tables (components, tech stack, **the local & open-weight model reference**, portfolio one-liners, red flags).
- **Test Plan** — Option A scope: test the core engine, infrastructure, and services; do **not** test the reference-only customer-care workflow. Fix four documented production bugs. Then every new workflow ships with its own tests.

---

## The Project Sequence at a Glance

*Names only — full content lives in the plans. Sequence is load-bearing; calendar is not (see Governing Principles).*

**Phase 0 — Foundation:** Block A (presence + codebase ownership) · Block B (Mac Mini agentic harness + revive `learn-agentic-ai.com`) · Block C (test infra + core hardening + 4 bug fixes) · Block D (shared services + first scaffold + clean API contract)

**Phase 1 — Sellable Competence:** Project A (content pipeline → *personal knowledge feed + optional blog; a one-person Company Brain*) · Project B (research agent) · Project C (proposal generator) · Project D (document Q&A + RAG — *the Company Brain's retrieval half*)

**Phase 2 — Depth + First Paid Work:** Project E (specialization refactor) · Project F (semantic search) · Project H (model eval & routing harness — *the spine of the privacy differentiator; makes "runs on your hardware" measured and honest*) · First paid diagnostic

**Phase 3 — The Differentiating Build:** Project G (agent memory system — *two-stage reasoning-first memory, multi-peer entity model, Honcho-informed architecture; the Company Brain's "keeps it current" engine*) · then Brain v1 assembly + shells, gated on real pull

**Parallel track (anytime after the harness exists):** Rust **appliance shell** (formerly "Harness CLI") — the SMB single-binary delivery vehicle; the privacy promise made physical

**Phase 3+ capstone (assembles from the plan, not a detour):** the self-improving system (Part 5) — prompt/routing/memory evolution gated by Project H, agent-composed workflows over trusted nodes, new capability by human-reviewed PR (D20)

**Dependencies that must hold:** read the core before testing it (A→C) · harness before deploying anything (B) · A's components feed C and D · D feeds F and H · Project H needs real nodes to evaluate (after D) · the first paid diagnostic waits for the competence checkpoint, not a date · the self-improving capstone needs a node library + validator/test-gate + Project H, so it is strictly Phase 3+.

---

## Governing Principles (these explain *why* the plans are shaped as they are)

1. **Expertise first; the business/job follows.** The build is the goal, not a means to fast revenue.
2. **Sequence, not calendar.** Blocks and projects have no dates. Work them in order, at whatever pace life allows. Brandon supplies cadence via his separate whiteboard system (THIS WEEK / TODAY); these documents answer "what's next," the whiteboard answers "what today."
3. **Just-in-time building.** Build the thinnest thing that teaches the pattern or meets a real need. Expand only when a prospect, client, or downstream project forces it. Avoid infinite tool-building with no revenue.
4. **Every project ships with its own tests.** The core was hardened in Phase 0 so this discipline could hold from Project A onward.
5. **The competence checkpoint defines "ready," not a finished list.** Ready = *can walk into an unfamiliar SMB and name three automatable workflows in 30 minutes, and explain how to build each — and, for at least one, say which steps are safe on a local model and roughly what that saves.* (The local-vs-paid clause was added June 2026; it bakes the privacy differentiator into the readiness bar — DECISIONS D15.) If the list is done but readiness is in doubt, send one diagnostic offer anyway — don't add a project.
6. **The public-narrative rule (non-disparagement-safe).** In anything public, make Brandon, his work, or his reasons the subject of every sentence — never the previous company's conduct. Never name the company in posts (LinkedIn carries the factual record). *Note: the April 2025 proposal is powerful private evidence but names a company — de-identify fully before any public use.*
7. **Right tool for the job.** Python for orchestration (I/O-bound). Rust only where it genuinely wins — now with a *defined product home*: the **SMB appliance shell** (single static binary, instant startup, the "your data never leaves the building" promise made physical — DECISIONS D17), plus daily-ops use. A potential Rust inference runtime layer only when a measured limit demands it (not in scope yet). Never the orchestration core.
8. **Resist the impressive-but-unjustified.** Overkill Rust, runtime routers, summary-mill content, claiming work not done — the discriminating "no" is itself the expertise.
9. **The brain never knows where it's running (the one-product discipline).** The orchestration framework is the deployment-agnostic *brain*; what varies by deployment (model choice, where data lives) is injected via config, never hardcoded. SMB and enterprise are one core with two shells, not two products. The first `if running_locally:` in a node means two products have started (DECISIONS D16, D18).
10. **Evolve what's gated; new capability enters by PR; never self-approve the gates.** For any self-improving/self-building feature (Phase 3+): the system may freely do the measured-and-gated things (self-correct outputs, evolve prompts/routing/memory scored by Project H, compose workflows over trusted nodes validated before run). New node code enters only by human-reviewed PR. The validator, test-runner, eval rubric, and consolidation prompt are human-owned gates agents may propose changes to but never self-approve. The thing being graded never rewrites its grader (DECISIONS D20).

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
| "How does SMB vs enterprise deployment work / the architecture?" | CONTEXT + DECISIONS (D16–D18) + Master Plan (architecture section) | The one-brain-two-shells design and the injection-point discipline |
| "Which model should this node use / local vs frontier?" | CONTEXT + Projects Plan (Project H + the model reference) + DECISIONS (D8, D19) | The eval-driven routing rule and the local/open-weight shortlist |
| "How would the self-improving / agent-contribution system work?" | CONTEXT + Projects Plan (Part 5) + DECISIONS (D20) | The capstone design and its hard boundary; flag it's Phase 3+ |
| "Write a LinkedIn post / the return post / résumé" | CONTEXT + Master Plan (case studies + narrative rule + content plan) | Needs the arc and the safety rule, not the codebase. The EN + PT return posts are already drafted — reference them |

**When generating task lists:** respect the governing principles above — especially just-in-time scope (don't task out features a real need hasn't summoned yet), tests-per-project, and sequence-not-calendar (produce a *this-week* batch sized to ~21 hrs/week across Mon/Wed/Fri, not a dated schedule).

**When updating progress:** edit `STATUS.md` only. Leave the plans clean. Record deviations and decisions in STATUS's log so the plans stay the stable source of truth.

---

## Fast Facts (for grounding any reader)

- **Destination (named June 2026):** the **Company Brain** — privacy-first, SMB-wedge (~30–80-employee inflection), enterprise as a later expansion. One deployment-agnostic Python brain, two shells (Rust SMB appliance + later cloud enterprise). A job remains a fine, non-foreclosed outcome served by identical work.
- **Time available:** Mon / Wed / Fri, ~10am–5pm (~21 hrs/week). ~70% building, ~30% visibility/networking.
- **Existing infrastructure:** a working Python agentic orchestration framework (FastAPI + Celery + Redis + PostgreSQL; Workflow / Node / TaskContext / AgentNode abstractions). Has zero tests currently — Phase 0 fixes that for the core. *This framework is the brain of the Company Brain.*
- **Self-hosting:** a Mac Mini with two faces. **Public face** (Caddy + Cloudflare DNS): hosts `learn-agentic-ai.com` (bilingual PT/EN, currently down after hitting a Vercel limit) — accessible to anyone with the URL. **Private face** (Tailscale): personal knowledge feed, orchestration API, all private tooling — accessible only from your own devices (Pixel tablet, phone, Kindle, laptop), completely off the public internet. The two faces are architecturally separate by design (DECISIONS D23).
- **Model strategy:** top-tier models everywhere on the first run-through to confirm everything works; then introduce and measure local/open-weight swaps via Project H. Voyage embeddings are a legitimate standing default, not a compromise. Local shortlist + per-node routing live in the Projects Plan's model reference. The Project G consolidation step stays on Claude — never local (DECISIONS D19).
- **Warm leads:** a CrossFit gym (Jardins — likely first diagnostic: trainer sourcing/scheduling, WhatsApp/Instagram automation; note: *below* the Company-Brain inflection, so a bounded automation sale, not a brain) and an e-commerce seller (Mercado Livre — trend-spotting, competitor analysis, multi-CNPJ invoicing). **Gap to close: the sharpest Company-Brain-shaped lead — a fast-growing 30–80-person firm — is not yet among the warm leads. Finding one is a named networking goal (Master Plan).**
- **Drafted and ready:** the bilingual return post — EN ("The Builder's Arc") and PT — both subject-on-you, no company named, the April 2025 proposal story.
- **Archived, not in scope here:** an earlier Socratic Tutor app plan and physics/PhD exploration live in separate documents and are intentionally excluded from this set.

---

*This file orients; it does not track. For state, open `STATUS.md`. For content, open the relevant plan. For why a choice was made, open `DECISIONS.md`.*
*Last updated: June 2026 — Company Brain destination, one-brain-two-shells architecture, self-improvement boundary (D14–D20).*
