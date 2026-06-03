# Brandon's Master Plan — 2026
## Becoming an Expert in AI / Agentic / Harness Engineering — and Building a Practice From It

*Created: May 2026 · Living document — update as things shift*
*Time available: Mon / Wed / Fri, 10am–5pm (~21 hrs/week guaranteed)*
*No hard deadline. This plan is sequenced to breathe — build deeply, talk to people throughout, let opportunities surface naturally.*

---

## The Goal, Stated Plainly

The goal is **expertise** in AI Engineering, Agentic Engineering, Harness Engineering, and the surrounding architecture. Everything else — a consulting practice, a small team, a job at a São Paulo company, a product — *follows from* being genuinely expert. The work to get there is the same regardless of which outcome lands.

This reframes the old "build, ship, get paid" plan. The build *is* the point now, not a means to fast revenue. But expertise that has never met a real business's mess has a blind spot, so this plan keeps two things running in parallel from early on:

1. **Building the full project library** — deep, tested, real systems that make you expert.
2. **Low-stakes market contact** — conversations, network, and eventually paid diagnostics, so the expertise is *demonstrated*, not just claimed.

Both a studio and a job are served by identical work. The plan doesn't choose between them. It produces evidence of expertise that reads equally well to a client or a hiring manager.

### The destination, stated plainly (added June 2026)

The "endgame is open" framing below was the right call when this plan was written and you were less sure. You're more sure now, so name it: **you're building a teaching-led studio where cost-optimized, single-binary AI automation is the product, SMB work is the proof, and teaching is how clients adopt and how you grow in São Paulo.** The teaching isn't a separate future — it starts as teaching customers to use what you build for them, and may grow from there. A job remains a fine outcome and the same work serves it, so nothing is foreclosed; but decisions get pruned faster against a stated destination than against three open doors. The differentiator inside this destination is specific: not "I can build an automation," but "I can build it *cheaply and privately, on your own hardware*." That edge — measured cost/quality, local models where they thrive, delivered as a single binary a non-technical operator can run — is the spine, not a side-feature. (See the reframed Project H emphasis and the Rust appliance in the Projects plan.)

### The through-line you're building on

You are not pivoting into AI. You have been building adopted, practical AI-and-automation tools for years, and you have the judgment to know what's worth shipping. State that story as one arc, because it's true and it holds up:

> **Internal Support Dashboard** (saw an unmet need, built it solo, 100+ people across the company adopted it and still use it daily) → **Helpscout Support Automation** (saw a support bottleneck, built RAG-based automation to fix it, solo) → **AI Scribe** (contributed heavily to production healthcare AI at scale) → **early Claude Code / Aider experiments** (was early, shipped fast, learned where fast AI-building goes wrong) → **now**: the studio and the harness, applying all of it deliberately.

That arc serves a studio and a job hunt equally. Lead with it.

### What "ready" means (the competence checkpoint)

You are ready to sell — or to walk into a senior interview with confidence — when:

> **You can walk into an SMB you've never seen and name three automatable workflows in 30 minutes, and explain how you'd build each one on your own infrastructure.**

**Sharpened (June 2026):** name three workflows *and*, for at least one, say which steps are safe on a local model and roughly what that saves. This bakes your differentiation into the readiness bar itself, rather than leaving it as a Project H footnote — the thing that makes you the person who builds it cheaply and privately on the client's hardware, not just another person who can build it.

Confidence is pegged to *that skill*, not to finishing the project list. If you finish the core projects and still feel "not ready," that's the signal to send one diagnostic offer anyway and learn from the discomfort — not to add a ninth project. (And note: between the Dashboard and Helpscout, you have already *done* versions of this in production. You are closer to ready than the "about to build" framing suggests.)

---

## Existing Case Studies — You Are Already Expert

These predate this plan and are load-bearing evidence. Foreground them on LinkedIn, the résumé, the site's About section, and in every conversation. They are stronger than anything you're about to build, because they're shipped, adopted, and durable.

**Claim full ownership where you had it; claim honest contribution where you had that; let the difference show. The honesty makes the ownership claims more believable, not less.**

### Internal Support Dashboard — *flagship*
Built and architected solo, from the ground up. Also built the Internal Tools team around it.
- **100+ daily users** across sales, finance, support, and customer success — genuinely cross-functional adoption, which is a harder design problem than a single-team tool.
- Cut customer and technical support wait times by **24–48 hours**.
- Still in extensive daily use today, well over a year later — the durability proof most portfolio pieces can't offer.
- Demonstrates the three things that are hardest to verify in anyone: spotting an unmet need unprompted, building something people actually adopt, and leading.

### Helpscout Support Automation — *the SMB-support template*
Built and architected solo, in production. Read a support ticket, searched the help docs and the customer database, produced a summary for the rep to review and respond.
- Used **RAG, vector search, and semantic search** in production.
- Strategically important: this means the most common SMB request you'll get — and **Project D** in the Projects plan — is not a new competence. You've shipped and architected this pattern in production. Project D is *reinforcement and a portfolio refresh*, not first contact.

### AI Scribe — *production AI at scale (honest contribution)*
Production AI tool for medical professionals: ingest a Zoom transcript with a client, analyze the conversation, summarize, and auto-fill customizable forms and charting notes.
- Joined a Staff Engineer's existing architecture **before** production launch; contributed heavily to the production codebase; owned shipping, testing, troubleshooting, and support for **4+ months** after launch.
- Frame exactly that way — do not claim the architecture. "Joined before launch, contributed heavily to the production codebase, owned shipping and reliability after" is both true and strong. Structured-output-against-customizable-schemas is the *same skill* as your summarizer and proposal nodes.

### Rust orchestration engine — *pending review*
A Rust port of your Python orchestration engine. Shows range and is genuinely hard. **Keep pending your walk-through review** — feature it only once you've confirmed you can defend every design decision in an interview. (You're fairly confident you can.)

### The two de-featured projects — *repurposed, not deleted*
A Rust Claude Code SDK and a Python agent library, both built fast and mostly with AI in 2025. De-feature them from the portfolio for now. **Do not delete them** — they become the material for a high-value blog post (see Content Plan): being an early adopter, shipping fast and a lot, and learning that volume isn't quality with AI. That post is more honest and more impressive than a wall of polished repos.

---

## The Public Narrative Principle (Read Before Writing Anything Public)

You signed a non-disparagement agreement. The rule that keeps every public sentence safe *and* dignified:

> **Make yourself, your work, or your reasons the subject of every sentence. Never the company's conduct.**

The asymmetry is the safety. "I left to prioritize my health and my family" is entirely about your decision — it makes no claim about them, so it can't disparage and can't be read as a dig. The moment a sentence describes the *environment* ("toxic," "difficult," "not a fit"), it's a claim about them, however softened. Keep the subject on your side of the line and you're both safe and graceful.

**Company name:** never in public posts or the site. LinkedIn carries the factual employment record one click away; prose stays company-agnostic ("a healthcare technology company," "the AI team I joined"). This makes the writing easier, since every sentence naturally stays about your work.

**The safe return framing (bilingual, for the site and LinkedIn):**
> "After six months shipping production AI on the company's AI team, I made the decision to step back, prioritize my wellbeing, and be present for my family as we welcomed our daughter. Now I'm back and building in the open again."

Every clause is about you. It reads as someone who left from strength — which is the impression you want, and it's true.

---

## How to Use This Document

Sequenced by **dependency and competence**, not calendar pressure. Some things must come before others — you can't host a project before the server runs, can't trust a system you've built on top of an untested core, can't pitch a workflow you've never built.

**When things slip (and they will):** Don't restart. Don't guilt-spiral. Pick up where you left off in the next available session. The sequence matters more than the week number.

**The weekly rhythm:**
- **Monday** — Deep technical work. No LinkedIn or email until 4pm.
- **Wednesday** — Technical in the morning (10am–1pm). Business development / networking in the afternoon (2pm–5pm).
- **Friday** — Technical work + documentation + content creation. End by reviewing what shipped and what's next.

**The split:** roughly 70% building (~15 hrs), 30% visibility, networking, and writing (~6 hrs). Protect both. The visibility half is how expertise turns into a life in São Paulo.

**On testing:** The core engine gets locked down and four known production bugs get fixed *before* any client-facing system is built on top of it. After that, **every new workflow ships with its own tests.** Details in the separate Test Plan.

---

## Phase 0: Foundation
### Before Real Systems Get Built

Everything here unlocks the rest. Take the time it needs.

---

### Foundation Block A — Digital Presence + Codebase Ownership

**Technical:**
- Read `core/workflow.py`, `core/task.py`, `core/nodes/agent.py` line by line. Annotate. Understand *why*, not just how.
- Then `core/nodes/parallel.py`, `core/nodes/router.py`, `core/schema.py`, `core/validate.py`, `services/prompt_loader.py`.
- Run the existing Customer Care workflow end-to-end once and trace every call. It's the *reference implementation* — understand it, don't extend it.
- **Checkpoint:** answer the five orientation questions (Projects plan, Phase 0) from memory and draw the three-tier architecture diagram without looking.

**Visibility:**
- **LinkedIn overhaul.** Highest-ROI single action.
  - Headline: `AI / Agentic Systems Engineer | Multi-agent pipelines, orchestration & agentic harnesses | São Paulo`
  - About: the through-line arc above — teacher and builder, self-taught developer, a decade shipping software, built an adopted internal platform and production AI, now focused on agentic and harness engineering. Bilingual. Rooted in São Paulo. Open to local roles and consulting.
  - **Foreground the three case studies** with their real numbers (Dashboard 100+ users / 24–48hr; Helpscout RAG in production; AI Scribe production contribution).
  - Master's in Pure Mathematics, prominently.
- **GitHub cleanup.** Archive stale repos. **Pin the Python orchestration engine and (pending review) the Rust engine; de-feature the Rust SDK and Python agent library.** Rewrite the profile README around the through-line. Create an empty `agentic-portfolio` repo.

---

### Foundation Block B — The Mac Mini Agentic Harness + Reviving the Site

This is **harness engineering** — a named target expertise — and the artifact is portfolio-grade. Do it in one focused push.

- Port forwarding (80/443 → Mac Mini).
- Caddy for reverse proxy + automatic SSL (Let's Encrypt).
- DNS for `learn-agentic-ai.com` via Cloudflare (free, DDoS protection, hides home IP). Dynamic DNS if no static IP.
- **Revive `learn-agentic-ai.com` on the Mini as the first real thing the harness hosts.** The site is down because you hit the Vercel limit — that's the forcing function. **Revive, don't redesign.** Get the existing bilingual (PT/EN) site back up largely as-is; a redesign is a someday item. A live old site beats a perfect unlaunched one.
- **The harness layer — the actual point:** stand up async **Claude Code** triggerable remotely. Wire one path end-to-end first (GitHub issue → Claude Code run → result back). Expand over time to webhooks, Dispatch, Telegram. Goal: kick off work from your phone, away from the desk.

  **Note (June 2026):** Claude Code now ships **Agent View** (`claude agents`, background sessions run by a per-user supervisor that survive terminal/shell closure), `claude --bg`, and **Claude Code Web** (sessions that survive machine sleep, run in Anthropic's cloud). For the *coding-agent* case, lean on these built-ins first rather than building your own trigger plumbing. The only seam they don't cover is *phone → your own Mac Mini, surviving sleep* — build custom remote-trigger plumbing only if you still want that after trying the built-ins. This thins (doesn't delete) the original justification for the harness's remote-trigger work and the Rust CLI's first job; see the reframed CLI section in the Projects plan.
- **The recursion is the story:** the site is hosted on your self-built harness and partly fed by your own agentic pipeline. That *is* the portfolio, demonstrated rather than claimed.

**Visibility:** Publish the **bilingual return post** using the safe framing above. This answers the year-long gap head-on as a deliberate chapter, not silence. Then a first LinkedIn post: rebuilding your practice around agentic and harness engineering, documenting in the open.

---

### Foundation Block C — Test Infrastructure + Core Hardening

Make the framework trustworthy before building on it. (Test Plan, Option A scope: core engine only, **no** customer-care tests.)

- Add test tooling, create `pytest.ini` with env defaults, build `tests/conftest.py`. Confirm `pytest --collect-only` succeeds with zero errors.
- Core-engine unit tests: `TaskContext`, `WorkflowSchema`, `WorkflowValidator`, `Workflow.run`, `BaseRouter`, `ParallelNode`. Then `core/`, `database/`, `api/`, `services/`.
- **Fix the four documented bugs:** `GenericRepository.exists()`, the ghost-row commit-before-`send_task` ordering, import-time side effects, router key coupling.
- Most test-writing goes to Claude Code under your supervision. Supervising agent-written tests *is* agentic-engineering practice — treat it as learning.

**Visibility:** A post on testing agentic systems — why an untested orchestration core is a liability, the four bugs, how you closed them. Signals senior judgment.

---

### Foundation Block D — Shared Services + First Scaffold

Build once, reuse everywhere: pgvector migration; `EmbeddingService` (Voyage); `TranscriptService`; `SearchService` (Tavily); `ChunkingService`; add dependencies. Run `createworkflow` to scaffold Project A's structure (no logic yet).

**End of Phase 0 checkpoint:** LinkedIn and the revived bilingual site read like someone actively building in AI, with three real case studies front and center. GitHub triaged. You own the codebase (5 questions from memory). The Mini serves the site over SSL *and* runs Claude Code remotely via at least one trigger. Core engine tested, four bugs fixed, shared services exist.

---

## Phase 1: Sellable Competence
### The Projects That Teach What You'll Actually Sell

Four projects, in order, build the competence behind the checkpoint. Each ships **with its own tests.** (Build detail in the Projects plan.)

---

### Block 1 — Project A: Content Pipeline (YouTube → Summary → Blog)

Fastest end-to-end rep, and it produces your content engine. The self-critic → revise loop is the lesson.
- `FetchTranscriptNode → SummarizerNode → BlogWriterNode`, then `SelfCriticNode → ReviseNode → StorageNode`. Store to `LearningArtifact` with embedding at write time.
- **Learning content:** the AI/agentic/harness material you want to absorb — TAC course, orchestration and agent talks, harness/agentic-coding content. Each video both teaches you and grows the corpus.
- **`blog_writer.j2` is a long-term asset — and now it generates content under your name, in two languages, on your own domain.** Matching your voice in PT and EN is a real prompt-design consideration, not automatic. Spend real time here.
- **Caveat:** the pipeline feeds the site's *cadence* (regular posts so it looks alive), not its *spine*. The signal posts are your own project writeups (the four-bug testing piece, the parallel-merge fix, the memory system, the harness, the slop-projects post). Don't let convenience turn the site into a summary mill.
- Tests ship with it. Deploy to the Mini.

**Visibility:** First portfolio post. **Networking:** list 10 people in your São Paulo network and adjacent tech scene. Don't message yet.

---

### Block 2 — Project B: Research Agent (thin first, then hardened)

Most directly sellable competence: research a company, find the automation opportunity. Also your prospecting tool.
- **Thin cut first:** one `ToolUseNode` (raw Anthropic SDK — write the `while stop_reason == "tool_use"` loop yourself, *feel it*) + Tavily. Company name in, structured brief out. No Celery, no critic, no storage. ~50 lines.
- **Then harden** into `PlannerNode → ResearchNode → CriticNode → ReviseNode → StorageNode` once a real prospect makes you want more.
- Tests ship with it.

**Networking:** Begin *research conversations* (not pitches). "I'm building automation tooling for SMBs — what's the most annoying repetitive thing your team does?" Start with the two warm leads.

---

### Block 3 — Project C: Proposal Generator

The most client-facing thing in the plan. The opportunity-identification prompt *is* the checkpoint skill.
- `CompanyResearchNode` (reuses B's tool loop) → `OpportunityIdentifierNode` → `OpportunityRouterNode` → `ProposalWriterNode` (PT and EN) → `ProposalReviewNode` → `ReviseNode` → `StorageNode`.
- Real time on `proposal_writer.j2` and review criteria. One recommendation, not three.
- Tests ship with it.

**Networking:** Run the pipeline on the two warm leads as practice. Output ~80% ready; that's valuable.

---

### Block 4 — Project D: Document Q&A + Session Memory (RAG)

The most common SMB request — **and a pattern you've already shipped in production (Helpscout).** This is reinforcement and a portfolio refresh, not first contact. Frame for business documents (SOPs, catalogs, internal wikis), not textbooks.
- Ingestion: `ParseDocumentNode → ChunkDocumentNode → EmbedChunksNode → StoreChunksNode`.
- Query: `EmbedQuestionNode → RetrieveChunksNode → AssembleContextNode → AnswerNode → UpdateSessionMemoryNode`.
- Build `RetrieveChunksNode` carefully — reused verbatim later. Internalize RAG-vs-session-memory.
- Tests ship with it.

**Visibility:** A post that connects this to the Helpscout production work — "I shipped RAG-based support automation in production; here's me rebuilding the pattern cleanly on my own infrastructure." Proven, not aspirational. **Competence checkpoint review:** test yourself honestly against "three workflows in 30 minutes."

---

## Phase 2: Depth + First Paid Work

### Block 5 — Project E: Specialization Refactor
Kept separate from A on purpose — the *before/after* is the lesson that lets you explain to a client why specialization matters. Refactor A into `[ConceptExtractorNode ‖ StructureAnalystNode] → BlogDraftNode → VoiceMatchNode → SelfCritic → Revise → Storage`. **Fix the `ParallelNode` merge gap here** (keyed slots, merge after). Compare old vs new outputs; write it up — strong post.

### Block 6 — Project F: Semantic Search Over Your Corpus
Mostly D's components. `GET /knowledge/search?q=...` → top-k artifacts + optional synthesis. The tool you'll actually use to study. Seeds the #1 client-memory product.

### Block 6.5 — Project H: Model Evaluation & Routing Harness *(the spine, not a side-quest)*
**Reframed (June 2026): this is the centerpiece of your differentiation, not a flexible add-on.** Still best built after Project D (needs real nodes to evaluate) and pairs naturally with G — so the *build order* doesn't change — but it is the project that earns the deep blog post and that the client appliance is built around. An offline tool that runs each node against frontier and local models, scores the outputs (deterministic for structured nodes, bias-corrected LLM-as-judge for prose), and produces empirical per-node routing decisions — "this node is safe on local-70B." Proves the local-models thesis with data, and is directly sellable as substantial cost reduction with measured quality retention. **Offline eval, not a runtime router.** Projects A–D partly exist to give H real nodes to measure. (Full detail in the Projects plan.)

**Funding discipline (the 2+3 trap):** the local-model bet may be a year ahead of where most SMBs feel the pain. That's fine *only if services revenue funds it.* Let the studio (warm leads, paid diagnostics) pay the bills while H and the appliance mature; don't let the bet jump ahead of the revenue that buys time for it.

### Parallel Track — Rust Harness CLI *(whenever you want a Rust session)*
A single-binary terminal control plane for triggering and observing remote agent runs and workflows — the local counterpart to the phone-based remote triggers. **Distinct from Claude Code:** Claude Code does the coding work; this CLI commands and observes your infrastructure. This is where Rust stays warm through genuine daily use (instant startup, single binary, mature CLI ecosystem). Rust commands, Python executes — clean language boundary, no rewriting working Python. Start with one command; let it grow just-in-time.

### Block 7 — First Paid Diagnostic
When the checkpoint is genuinely met and you've had weeks of research conversations, make a **paid diagnostic offer** to the strongest warm lead (likely the gym). A small fixed-fee engagement (1–2 weeks): map the workflow, deliver a concrete plan with one quick win built and working. Low-risk yes for them; qualifies whether they'll spend money; gives you the inside view to scope the real project.

---

## Phase 3: The Differentiating Build

### Block 8 — Project G: Agent Memory System (Episodic → Semantic)
The most architecturally important and differentiating thing you'll build — durable agent memory with confidence decay and contradiction handling. Underpins the #1 and #5 product ideas. The capstone, given expertise-first. Budget a full, unhurried block. The `consolidation.j2` prompt is the hardest thing in the plan. Tests ship with it — and matter most here, because bad memory output degrades everything downstream silently.

**Visibility:** Your strongest technical content — a deep post and a live demo on the Mini on building durable agent memory.

---

## The Three Internal-Tool / Product Ideas

Build the thinnest version only when a real need forces it. They validate the problem; productizing is a separate, later decision.

| Idea | Built on | Studio role | Build trigger |
|---|---|---|---|
| **#3 Research / intelligence synthesis** | Project B + Project G | Prospecting & client ramp | Prospecting the first client |
| **#1 Account / client memory layer** | Project G + Project F | Delivery & retention | ~3 clients; you start forgetting things |
| **#5 Expert "second brain"** | Project G | Capturing your own judgment | Optional; may never need formalizing |

The trap: infinite internal-tool building with no revenue. The studio earns by shipping client work. Thinnest cut at the moment of real need, never a feature ahead.

---

## Potential First Clients (Real, Warm Leads)

### CrossFit gym (Jardins) — *likely first diagnostic*
Your personal trainer is part-owner. Workflows are concrete, bounded, unglamorous in the right way:
- Finding/sourcing trainers for classes (their stated pain)
- Outreach to and scheduling with trainers
- WhatsApp / Instagram marketing automation

Stack is Instagram + WhatsApp. WhatsApp Business API has real constraints — solving that fiddly integration is what makes you valuable. Clean first diagnostic: trusted relationship, scopeable workflow, visible quick win.

### E-commerce (Mercado Livre) — *more interesting, harder, later*
Three distinct pains, in his words:
- **Trend-spotting** ("what's booming on Amazon US to sell on Mercado Livre") — a genuine product, but full research-agent territory; bigger than a first engagement.
- **Competitor analysis** ("existing tools are all inaccurate") — a classic wedge, but accuracy is hard; don't let a first deliverable be judged against a precision bar you can't yet hit.
- **Invoicing / multi-CNPJ** (Bling has gaps; no tool lets him pick between two CNPJs across marketplaces) — least AI-flavored, possibly most valuable to him, most tractable. Integration plumbing.

**The most sellable thing isn't always the most AI-impressive thing.** The invoicing pain may be the better first paid problem here.

---

## Content Plan & Business Development

**The site (`learn-agentic-ai.com`), bilingual PT/EN, two channels:**
- **Blog/Learn — volume:** Project A's pipeline output keeps the site alive at a regular cadence (summaries of AI/agentic/harness content you're studying).
- **Blog/Learn — signal:** your own project writeups are the spine — the posts that make someone want to hire you.

**High-value posts already identified (write these as projects surface them):**
- **The slop-projects / early-adopter post** — used Aider before Claude Code existed, shipped fast and a lot, learned that volume isn't quality with AI, and *that's exactly why the harness and context management matter*. Ties your two de-featured projects into a narrative about judgment, and gives the harness work a scar-tissue origin story instead of a hype one. One of your strongest pieces.
- The four-bug testing writeup (senior judgment).
- The Project E parallel/specialization comparison (architectural thinking).
- The Helpscout-to-Project-D piece (proven production RAG).
- The Project G memory deep-dive + live demo (frontier-adjacent).

**Networking before selling:** From Phase 1, have *research conversations*, not pitches. Solves the in-a-vacuum risk and pre-warms prospects without needing a finished product. Be known in São Paulo's tech scene — coffee, meetups, warm intros.

**Content cadence:** ~1 post per shipped project or notable learning. Don't manufacture content; ship something, write about that. PT and EN.

**First paid offer:** at the checkpoint, to the warmest lead, as a paid diagnostic. If you hit the checkpoint and still hesitate, send one anyway.

**Job hunt, in parallel:** São Paulo roles, or US/EU companies with a São Paulo office reachable 1–2x/week (you want out of the house and into a room with people — honor that). The portfolio that wins clients wins interviews. Keep résumé and LinkedIn current as projects ship, with the three case studies foregrounded.

**The endgame is open and that's fine:** studio with a small team, a job, or a product from the memory work. The work is identical until one pulls ahead. You have runway; the goal is expertise.

---

## Quick Reference: Sequence

| Phase | Block | What | Why |
|---|---|---|---|
| 0 | A | Presence (case studies) + codebase ownership | Foundation |
| 0 | B | Mac Mini harness + revive bilingual site | Harness engineering + infra |
| 0 | C | Test infra + core hardening + 4 bug fixes | Trustworthy foundation |
| 0 | D | Shared services + first scaffold | Reused everywhere |
| 1 | Project A | Content pipeline | Fast rep + content engine |
| 1 | Project B | Research agent (thin→hardened) | Most sellable competence |
| 1 | Project C | Proposal generator | Client-facing; checkpoint skill |
| 1 | Project D | Document Q&A + memory (RAG) | Common request; you've shipped it before |
| 2 | Project E | Specialization refactor | Architectural judgment |
| 2 | Project F | Semantic search over corpus | Reuse + learning tool |
| 2 | Project H | Model eval & routing harness | Proves local-model thesis; sellable cost win |
| 2 | — | First paid diagnostic | Demonstrated expertise |
| 3 | Project G | Agent memory system | The differentiating centerpiece |
| ∥ | Rust CLI | Harness control plane | Keeps Rust warm through daily use |

*Every project from A onward ships with its own tests. The core was locked down in Phase 0.*

---

*This document serves you — you don't serve it. When life gets in the way, pick up where you left off. The sequence is what matters, not the calendar. The goal is expertise; everything else follows.*

*Last updated: May 2026*
