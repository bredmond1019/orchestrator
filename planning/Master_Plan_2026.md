# Brandon's Master Plan — 2026
## Becoming an Expert in AI / Agentic / Harness Engineering — and Building the Company Brain From It

*Created: May 2026 · Major revision: June 2026 (Company Brain destination + architecture) · Living document — update as things shift*
*Time available: Mon / Wed / Fri, 10am–5pm (~21 hrs/week guaranteed)*
*No hard deadline. This plan is sequenced to breathe — build deeply, talk to people throughout, let opportunities surface naturally.*

---

## The Goal, Stated Plainly

The goal is **expertise** in AI Engineering, Agentic Engineering, Harness Engineering, and the surrounding architecture. Everything else — a consulting practice, a small team, a job at a São Paulo company, a product — *follows from* being genuinely expert. The work to get there is the same regardless of which outcome lands. *(See DECISIONS D1.)*

This reframes the old "build, ship, get paid" plan. The build *is* the point now, not a means to fast revenue. But expertise that has never met a real business's mess has a blind spot, so this plan keeps two things running in parallel from early on:

1. **Building the full project library** — deep, tested, real systems that make you expert.
2. **Low-stakes market contact** — conversations, network, and eventually paid diagnostics, so the expertise is *demonstrated*, not just claimed.

Both a studio and a job are served by identical work. The plan doesn't choose between them. It produces evidence of expertise that reads equally well to a client or a hiring manager.

### The destination, now named: the Company Brain (revised June 2026)

The earlier revision of this plan named the destination as "a teaching-led studio where cost-optimized, single-binary AI automation is the product." That's still true, and it's now sharpened into a **specific product the studio builds and sells: the Company Brain.** *(See DECISIONS D14.)*

A Company Brain ingests a company's scattered knowledge — the stuff in people's heads, old email, Slack threads, support tickets, databases — structures it, **keeps it current**, and turns it into an executable skills file that AI agents can act on. Not a search box. Not a chatbot over documents. A living map of how a company actually works, that gets smarter over time and that agents can use to do real work safely and consistently.

This isn't a pivot. It's the name for where your project library was already converging: **Project D** is the ingestion and retrieval layer (a pattern you've already shipped in production as Helpscout), **Project G** is the engine that "keeps it current" (episodic→semantic consolidation with confidence decay and contradiction handling — the hard part most teams get wrong), and the skills-file output is the **Claude Code skills primitive your harness already runs.** The Company Brain is your existing build with a product name on it.

**Why this, why you.** This is not a hypothetical you found attractive on a list. You *lived* it. At your last company you watched the team grow from 30 to 200 people, you diagnosed the exact knowledge-fragmentation failure a Company Brain solves, you pitched building this literal thing internally, and they said no — and then the cost of that no compounded as the company scaled. That is firsthand, scar-tissue conviction. You know where the knowledge leaks because you watched it leak. *(See DECISIONS D14.)*

### The buyer, named: fast-growing SMBs at the inflection — and enterprise later (revised June 2026)

The wedge is **fast-growing small companies caught at roughly the 30–80-employee inflection** — past the point where tribal knowledge fits in a few heads, before the point where they've already built (and abandoned) a wiki graveyard. That's a *window, not a size*: it's exactly the company you were inside of. *(See DECISIONS D15.)*

Enterprise is **explicitly welcomed as a later expansion** — you're open to it, and the architecture (below) is built so the same core serves both. Enterprise is not foreclosed; it's sequenced. It's the most crowded, best-capitalized lane on the whole RFS page, the worst first fight for a solo builder, and the place your differentiator matters least — so you earn into it from a position of proof, not enter it cold.

**The differentiator that funded competitors structurally won't copy: privacy-first, on the company's own hardware.** Every venture-backed Company Brain will be cloud, multi-tenant SaaS — correct *for them*, because that's how you scale to a thousand customers, but it means the company's knowledge lives on someone else's servers. The uncontested wedge is the opposite: **a Company Brain that never leaves the building.** In Brazil specifically, LGPD plus a real wariness of US cloud makes "never leaves the building" concrete, not abstract. *(See DECISIONS D15, D19.)*

The honest version of that promise — because it has to survive contact with reality — is **"local-by-default, frontier-for-the-named-few-steps."** Most of a Company Brain is retrieval and structured extraction, which local models now do well. A small, *named and auditable* set of steps (above all the Project G consolidation step) stays on Claude because a weak model there silently corrupts everything downstream. Project H produces the list of which steps go where and what each costs, and the operator sees it in plain numbers. That honesty is *more* defensible than absolutism, not less. *(See DECISIONS D19.)*

### The through-line you're building on

You are not pivoting into AI. You have been building adopted, practical AI-and-automation tools for years, and you have the judgment to know what's worth shipping. State that story as one arc, because it's true and it holds up:

> **Internal Support Dashboard** (saw an unmet need, built it solo, 100+ people across the company adopted it and still use it daily) → **Helpscout Support Automation** (saw a support bottleneck, built RAG-based automation to fix it, solo) → **AI Scribe** (contributed heavily to production healthcare AI at scale) → **early Claude Code / Aider experiments** (was early, shipped fast, learned where fast AI-building goes wrong) → **now**: the Company Brain and the harness, applying all of it deliberately.

That arc serves a studio and a job hunt equally. Lead with it. And note the new resonance: the Dashboard *was* a primitive company brain (cross-functional knowledge, made queryable, adopted), and Helpscout *was* the retrieval layer in production. You've shipped pieces of this product before. *(See DECISIONS D9.)*

### What "ready" means (the competence checkpoint)

You are ready to sell — or to walk into a senior interview with confidence — when:

> **You can walk into an SMB you've never seen and name three automatable workflows in 30 minutes, and explain how you'd build each one on your own infrastructure** — *and*, for at least one, say which steps are safe on a local model and roughly what that saves.

Confidence is pegged to *that skill*, not to finishing the project list. If you finish the core projects and still feel "not ready," that's the signal to send one diagnostic offer anyway and learn from the discomfort — not to add a ninth project. (And note: between the Dashboard and Helpscout, you have already *done* versions of this in production. You are closer to ready than the "about to build" framing suggests.)

---

## The Architecture That Makes SMB and Enterprise One Product

*This is the load-bearing design decision of the June 2026 revision. Read it before sequencing the work. (See DECISIONS D16, D17, D18.)*

The trap to avoid is building an SMB appliance, getting enterprise interest, and discovering you have to rewrite everything. You avoid it with one discipline: **the brain never knows where it's running.** Three layers:

**Layer 1 — The Brain (Python, identical in both versions).** Everything you're already building: the orchestration framework, Project D ingestion/RAG, Project G consolidation/decay/contradiction, embeddings, the skills-file emitter. It exposes one clean, documented HTTP API and makes *zero* assumptions about deployment. Two things are **injected, never hardcoded** *(DECISIONS D18)*:
- **Where models run** — per-node `model_provider` comes from a config file that is the *output of Project H*. SMB config points mostly at local Ollama; enterprise config points at a private/cloud endpoint. Same code, different config.
- **Where data lives** — all persistence goes through the existing `GenericRepository` against Postgres+pgvector. SMB: local. Enterprise: managed, possibly multi-tenant. Same queries either way.

If you hold that line, you write the Company Brain **once.** The rule that enforces it: *the first time you write `if running_locally:` inside a brain node, you've started building two products.*

**Layer 2 — The Shell (where SMB and enterprise diverge, and where Rust earns its place).**
- **SMB shell = the Rust single binary.** It supervises the local Python brain and Postgres, owns first-run setup, is the operator's local interface (`clap` CLI, optionally `ratatui` TUI), and surfaces the Project H cost/quality numbers ("this week 94% ran locally, 6% hit Claude, here's the bill"). This is the *only* part that's Rust, and it's Rust for the reasons that hold up: single static binary, instant startup, "copy one file, double-click, your data stays here." A Python app cannot make that promise credibly. *(See DECISIONS D17.)*
- **Enterprise shell = a thin cloud control plane.** Same brain, deployed as a service: multi-tenant, SSO, audit logs, admin dashboard, the integration connectors enterprises expect. Built **only when an enterprise pulls** — and because the brain is identical, it's *new surface around the same core*, not a rewrite.

**Layer 3 — The Agent Interface (the Software-for-Agents angle).** Design the brain's HTTP API as a first-class, documented, agent-discoverable interface from day one. The Rust binary drives it. The enterprise dashboard drives it. The client's *own* coding agent drives it. Agent access isn't retrofitted later; the API *is* the product surface, and humans, binaries, and agents are all just clients of it.

```
              ┌─────────────────────────────────────┐
              │  THE BRAIN  (Python — ONE codebase)  │
              │  orchestration · RAG (D) · memory (G)│
              │  skills-file emitter · embeddings    │
              │  clean documented HTTP API           │
              │  injected, never hardcoded:          │
              │    • model routing (← Project H)     │
              │    • persistence (Postgres/pgvector) │
              └──────────────────┬───────────────────┘
                                 │  same API, every client
        ┌────────────────────────┼────────────────────────┐
        │                        │                         │
  ┌─────▼──────┐         ┌────────▼───────┐        ┌────────▼───────┐
  │ SMB SHELL  │         │ ENTERPRISE     │        │ CLIENT'S OWN   │
  │ Rust binary│         │ SHELL          │        │ CODING AGENT   │
  │ local brain│         │ cloud: multi-  │        │ drives same API│
  │ + Postgres │         │ tenant, SSO,   │        │                │
  │ local model│         │ connectors,    │        │                │
  │ cost/qual  │         │ audit, dash    │        │                │
  │ TUI        │         │ (only on pull) │        │                │
  └────────────┘         └────────────────┘        └────────────────┘
   never leaves           scales to many             agent-native
   the building           orgs                       from day one
```

**The three RFS ideas, resolved as layers:** Company Brain = Layer 1 (the brain). Software for Agents = Layer 3 (the interface). AI OS for Companies = Layer 2 (the enterprise shell). They were never three choices. You're already building the hardest layer. *(See DECISIONS D16.)*

---

## Existing Case Studies — You Are Already Expert

These predate this plan and are load-bearing evidence. Foreground them on LinkedIn, the résumé, the site's About section, and in every conversation. They are stronger than anything you're about to build, because they're shipped, adopted, and durable. *(See DECISIONS D9.)*

**Claim full ownership where you had it; claim honest contribution where you had that; let the difference show. The honesty makes the ownership claims more believable, not less.**

### Internal Support Dashboard — *flagship, and the original company brain*
Built and architected solo, from the ground up. Also built the Internal Tools team around it.
- **100+ daily users** across sales, finance, support, and customer success — genuinely cross-functional adoption, a harder design problem than a single-team tool.
- Cut customer and technical support wait times by **24–48 hours**.
- Still in extensive daily use today, well over a year later — the durability proof most portfolio pieces can't offer.
- Demonstrates the three things hardest to verify in anyone: spotting an unmet need unprompted, building something people actually adopt, and leading. **Frame it as the seed of the Company Brain thesis** — cross-functional knowledge made queryable and adopted.

### Helpscout Support Automation — *the retrieval layer, already shipped*
Built and architected solo, in production. Read a support ticket, searched the help docs and the customer database, produced a summary for the rep to review and respond.
- Used **RAG, vector search, and semantic search** in production.
- Strategically central: the most common SMB request — and **Project D**, the ingestion/retrieval half of the Company Brain — is not a new competence. You've shipped and architected this pattern in production. Project D is *reinforcement and a portfolio refresh*, not first contact.

### AI Scribe — *production AI at scale (honest contribution)*
Production AI tool for medical professionals: ingest a Zoom transcript, analyze, summarize, and auto-fill customizable forms and charting notes.
- Joined a Staff Engineer's existing architecture **before** production launch; contributed heavily to the production codebase; owned shipping, testing, troubleshooting, and support for **4+ months** after launch.
- Frame exactly that way — do not claim the architecture. Structured-output-against-customizable-schemas is the *same skill* as the Company Brain's extraction and the proposal nodes.

### Rust orchestration engine — *pending review*
A Rust port of your Python orchestration engine. Shows range and is genuinely hard. **Keep pending your walk-through review** — feature it only once you've confirmed you can defend every design decision in an interview. (Note: per DECISIONS D6, Python remains the *production* orchestration path; this port is a learning artifact and range-demonstrator, not the path forward.)

### The two de-featured projects — *repurposed, not deleted*
A Rust Claude Code SDK and a Python agent library, built fast and mostly with AI in 2025. De-feature them from the portfolio for now. **Do not delete them** — they become the material for a high-value blog post: being an early adopter, shipping fast and a lot, and learning that volume isn't quality with AI. *(See DECISIONS D10.)*

---

## The Public Narrative Principle (Read Before Writing Anything Public)

You signed a non-disparagement agreement. The rule that keeps every public sentence safe *and* dignified *(DECISIONS D10)*:

> **Make yourself, your work, or your reasons the subject of every sentence. Never the company's conduct.**

The asymmetry is the safety. "I left to prioritize my health and my family" is entirely about your decision. The moment a sentence describes the *environment* ("toxic," "difficult," "not a fit"), it's a claim about them, however softened.

**One useful exception you now own:** the 30→200 story is tellable *because it keeps the subject on you* — "I watched a company I was in grow fast, I saw the knowledge fragment, I proposed a fix" is about your perception and your idea, not their failure. Tell it that way and it's both safe and a powerful founder origin story. Never "they were too short-sighted to build it"; always "I saw the need and it's the thing I'm building now."

**Company name:** never in public posts or the site. LinkedIn carries the factual employment record one click away; prose stays company-agnostic.

**The safe return framing (bilingual, for the site and LinkedIn):**
> "After six months shipping production AI on the company's AI team, I made the decision to step back, prioritize my wellbeing, and be present for my family as we welcomed our daughter. Now I'm back and building in the open again."

---

## How to Use This Document

Sequenced by **dependency and competence**, not calendar pressure. *(See DECISIONS D2.)* Some things must come before others — you can't host a project before the server runs, can't trust a system built on an untested core, can't pitch a workflow you've never built.

**When things slip (and they will):** Don't restart. Don't guilt-spiral. Pick up where you left off in the next available session. The sequence matters more than the week number.

**The weekly rhythm:**
- **Monday** — Deep technical work. No LinkedIn or email until 4pm.
- **Wednesday** — Technical in the morning (10am–1pm). Business development / networking in the afternoon (2pm–5pm).
- **Friday** — Technical work + documentation + content creation. End by reviewing what shipped and what's next.

**The split:** roughly 70% building (~15 hrs), 30% visibility, networking, and writing (~6 hrs). Protect both.

**On testing:** The core engine gets locked down and four known production bugs get fixed *before* any client-facing system is built on top of it. After that, **every new workflow ships with its own tests.** *(See DECISIONS D5.)*

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
- **New (June 2026):** as you read, note the two injection points that make the one-brain-two-shells architecture work (DECISIONS D18) — `model_provider` as config, persistence via `GenericRepository`. Confirm both are already config/abstraction, not hardcoded. This is reconnaissance for the architecture, costs nothing now.

**Visibility:**
- **LinkedIn overhaul.** Highest-ROI single action.
  - Headline: `AI / Agentic Systems Engineer | Multi-agent pipelines, orchestration & agentic harnesses | São Paulo`
  - About: the through-line arc — teacher and builder, self-taught developer, a decade shipping software, built an adopted internal platform and production AI, now focused on agentic and harness engineering. Bilingual. Rooted in São Paulo. Open to local roles and consulting.
  - **Foreground the three case studies** with their real numbers.
  - Master's in Pure Mathematics, prominently.
- **GitHub cleanup.** Archive stale repos. **Pin the Python orchestration engine and (pending review) the Rust engine; de-feature the Rust SDK and Python agent library.** Rewrite the profile README around the through-line. Create an empty `agentic-portfolio` repo.

---

### Foundation Block B — The Mac Mini Agentic Harness + Reviving the Site

This is **harness engineering** — a named target expertise — and the artifact is portfolio-grade. Do it in one focused push.

**The Mac Mini wears two faces — keep them architecturally separate (DECISIONS D23):**

**Public face — `learn-agentic-ai.com` and the public blog (Caddy + Cloudflare DNS):**
- Port forwarding (80/443 → Mac Mini) for public-facing traffic only.
- Caddy for reverse proxy + automatic SSL (Let's Encrypt).
- DNS for `learn-agentic-ai.com` via Cloudflare (free, DDoS protection, hides home IP). Dynamic DNS if no static IP.
- Anyone with the URL can reach this — correct, that's the point.
- **Revive `learn-agentic-ai.com` on the Mini as the first real thing the public face hosts.** Revive, don't redesign. A live old site beats a perfect unlaunched one.

**Private face — everything else (Tailscale):**
- Install **Tailscale** on the Mac Mini and on all your personal devices (Pixel tablet, Pixel phone, Kindle, laptop). They join a private encrypted mesh network (a "tailnet") automatically — no port forwarding, no firewall rules, no public exposure.
- The personal knowledge feed, the orchestration API, Celery dashboard, Postgres, Claude Code sessions — all of this is reachable from any of your devices anywhere, **and unreachable by anyone else**. This is the correct architecture for private tooling.
- MagicDNS gives friendly hostnames (`mini.tailnet`, `brain.mini.tailnet`) instead of IP addresses.
- The Personal plan supports unlimited devices per user and includes MagicDNS, subnet routing, and basic access controls — free forever for personal use. Your use case (one person, several devices) fits entirely within the free tier.
- **The personal knowledge feed lives here, not on the public face.** It's private by design, unreachable unless you're on the tailnet. That's correct — it's yours.

**What this is NOT:** Tailscale cannot make `learn-agentic-ai.com` publicly accessible to strangers — that's the public face's job (Caddy + Cloudflare). Tailscale is for *your* devices only. Keep this boundary clear or you'll end up trying to solve a public-access problem with a private-network tool.

```
Mac Mini
├── Public face  (Caddy + Cloudflare DNS — port 80/443 open)
│   └── learn-agentic-ai.com  →  portfolio site, public blog
│       accessible to anyone with the URL
│
└── Private face  (Tailscale only — no open ports)
    ├── personal-feed.mini    →  personal knowledge digest
    ├── :8080                 →  orchestration API
    ├── :5555                 →  Celery dashboard
    └── everything else       →  your devices only
```

**The harness layer — the actual point:** stand up async **Claude Code** triggerable remotely (over Tailscale, from the phone). Wire one path end-to-end first (GitHub issue → Claude Code run → result back). Expand over time.

  **Note (June 2026):** Claude Code now ships **Agent View** (`claude agents`), `claude --bg`, and **Claude Code Web**. For the *coding-agent* case, lean on these built-ins first. The only seam they don't cover is *phone → your own Mac Mini, surviving sleep* — that trigger runs over Tailscale to the Mini's private face.
- **The recursion is the story:** the public site is hosted on your self-built harness and fed by your own agentic pipeline; the private tooling runs on the same box, visible only to you.

**Visibility:** Publish the **return post** using the safe framing above. The English draft is written — "The Builder's Arc" (`LinkedIn_Return_Post_Builders_Arc.docx`): the April 2025 proposal story, subject-on-you throughout, no company named, the denial in one neutral clause. Review the two pre-publish checks in the doc's usage notes before posting. The **Portuguese version is a fresh write for the São Paulo audience, not a translation** — same story, different voice. After the return post, a second LinkedIn post: rebuilding your practice around agentic and harness engineering, documenting in the open.

---

### Foundation Block C — Test Infrastructure + Core Hardening

Make the framework trustworthy before building on it. *(Test Plan, Option A scope: core engine only, no customer-care tests — DECISIONS D5.)*

- Add test tooling, create `pytest.ini` with env defaults, build `tests/conftest.py`. Confirm `pytest --collect-only` succeeds with zero errors.
- Core-engine unit tests: `TaskContext`, `WorkflowSchema`, `WorkflowValidator`, `Workflow.run`, `BaseRouter`, `ParallelNode`. Then `core/`, `database/`, `api/`, `services/`.
- **Fix the four documented bugs:** `GenericRepository.exists()`, the ghost-row commit-before-`send_task` ordering, import-time side effects, router key coupling.
- Most test-writing goes to Claude Code under your supervision. Supervising agent-written tests *is* agentic-engineering practice.

**Visibility:** A post on testing agentic systems — why an untested orchestration core is a liability, the four bugs, how you closed them.

---

### Foundation Block D — Shared Services + First Scaffold

Build once, reuse everywhere: pgvector migration; `EmbeddingService` (Voyage); `TranscriptService`; `ArticleExtractionService` (trafilatura + Firecrawl fallback); `SearchService` (Tavily); `ChunkingService`; add dependencies. Run `createworkflow` to scaffold Project A's structure (no logic yet).

**On Firecrawl (DECISIONS D24):** `ArticleExtractionService` uses trafilatura as the default (free, local, fast for clean articles) and Firecrawl as a fallback for JS-heavy or paywall-adjacent pages. Firecrawl also provides `CrawlSiteNode` for the Company Brain's site-ingestion path (client help docs, wikis — entire sites by URL, not just single pages). Start on Firecrawl's free tier (500 credits/month); upgrade only when a real client crawl demands it. When Firecrawl runs inside an agent tool loop, add a `max_calls` guard (same discipline as Project B's `max_iterations`).

**New (June 2026) — make the API contract explicit here.** The Company Brain architecture (D16) depends on the brain exposing one clean, documented HTTP API that any shell or agent can drive (Layer 3). You're not building shells now — but when you define the FastAPI endpoints, treat the API as a *product surface*, not an internal detail: clear request/response schemas, documented, stable. This costs nothing extra now and is the seam everything later hangs off.

**End of Phase 0 checkpoint:** LinkedIn and the revived bilingual site read like someone actively building in AI, with three real case studies front and center. GitHub triaged. You own the codebase (5 questions from memory). The Mini serves the site over SSL *and* runs Claude Code remotely via at least one trigger. Core engine tested, four bugs fixed, shared services exist, API contract clean.

---

## Phase 1: Sellable Competence
### The Projects That Teach What You'll Actually Sell — and Build the Brain

Four projects, in order, build the competence behind the checkpoint. Each ships **with its own tests.** Note the reframing: **Projects D and G together are the Company Brain.** A–C are the competence and prospecting tools that surround it; D is its retrieval half; G (Phase 3) is its memory half.

---

### Block 1 — Project A: Content Pipeline (YouTube/Article → Personal Digest + optional Blog)

Fastest end-to-end rep, and it produces two things you'll use: a **personal knowledge feed** (Day 1, every morning) and your content engine. The self-critic → revise loop is still the engineering lesson.
- **Dual input:** YouTube URL (transcript) *or* article URL (new `FetchArticleNode` + `SourceRouterNode`). **Dual output:** every item → a categorized **personal digest** (default); `make_blog` flag → also a blog draft via `BlogWriterNode → SelfCriticNode → ReviseNode`. Store to `LearningArtifact` with embedding at write time for *every* item.
- **Reading surface:** static HTML served privately by Caddy on the Mini — readable on the Pixel tablet/phone and Kindle. Deliberately dumb: no search/tagging/sync yet (those attach via Projects F/G later, over the same embeddings). (DECISIONS D21, D22.)
- **It's a one-person Company Brain** — the dogfood version of the product. `FetchArticleNode` is reused by the real Company Brain to ingest web-based client knowledge.
- **Learning content:** the AI/agentic/harness material you want to absorb — *plus* your personal interests (physics/relativity, music), which the same pipeline handles. Each item teaches you and grows the corpus.
- **`blog_writer.j2` is a long-term asset** (blog branch only) — generates content under your name, in two languages, on your own domain. Spend real time on voice in PT and EN.
- **Caveat:** the pipeline feeds the site's *cadence*, not its *spine*. The signal posts are your own project writeups.
- Tests ship with it. Deploy to the Mini.

**Visibility:** First portfolio post. **Networking:** list 10 people in your São Paulo network and adjacent tech scene. Don't message yet.

---

### Block 2 — Project B: Research Agent (thin first, then hardened)

Most directly sellable competence: research a company, find the automation opportunity. Also your prospecting tool — **and now doubly so, because researching a company's workflows is the front edge of scoping a Company Brain for them.**
- **Thin cut first:** one `ToolUseNode` (raw Anthropic SDK — write the `while stop_reason == "tool_use"` loop yourself, *feel it*) + Tavily. Company name in, structured brief out. No Celery, no critic, no storage. ~50 lines.
- **Then harden** into `PlannerNode → ResearchNode → CriticNode → ReviseNode → StorageNode` once a real prospect makes you want more.
- Tests ship with it.

**Networking:** Begin *research conversations* (not pitches). "I'm building automation tooling for SMBs — what's the most annoying repetitive thing your team does, and where does knowledge live that only one person knows?" That last clause is Company-Brain reconnaissance. Start with the two warm leads.

---

### Block 3 — Project C: Proposal Generator

The most client-facing thing in the plan. The opportunity-identification prompt *is* the checkpoint skill.
- `CompanyResearchNode` (reuses B's tool loop) → `OpportunityIdentifierNode` → `OpportunityRouterNode` → `ProposalWriterNode` (PT and EN) → `ProposalReviewNode` → `ReviseNode` → `StorageNode`.
- Real time on `proposal_writer.j2` and review criteria. One recommendation, not three.
- Tests ship with it.

**Networking:** Run the pipeline on the two warm leads as practice. Output ~80% ready; that's valuable.

---

### Block 4 — Project D: Document Q&A + Session Memory (RAG) — *the Company Brain's retrieval half*

The most common SMB request — **and a pattern you've already shipped in production (Helpscout).** Reinforcement and a portfolio refresh, not first contact. Frame for business documents (SOPs, catalogs, internal wikis), not textbooks. **This is half the Company Brain; build it knowing that.**
- Ingestion: `ParseDocumentNode → ChunkDocumentNode → EmbedChunksNode → StoreChunksNode`.
- Query: `EmbedQuestionNode → RetrieveChunksNode → AssembleContextNode → AnswerNode → UpdateSessionMemoryNode`.
- Build `RetrieveChunksNode` carefully — reused verbatim later. Internalize RAG-vs-session-memory.
- **New (June 2026):** this is the first node set whose model routing genuinely matters for the privacy pitch. Note which steps are pure retrieval/embedding (local-friendly) vs. which need a strong model for the answer — you'll formalize this in Project H, but start observing it here.
- Tests ship with it.

**Visibility:** A post connecting this to the Helpscout production work — "I shipped RAG-based support automation in production; here's me rebuilding the pattern cleanly on my own infrastructure." Proven, not aspirational. **Competence checkpoint review:** test yourself honestly against the checkpoint.

---

## Phase 2: Depth + First Paid Work

### Block 5 — Project E: Specialization Refactor
Kept separate from A on purpose — the *before/after* is the lesson that lets you explain to a client why specialization matters. Refactor A into `[ConceptExtractorNode ‖ StructureAnalystNode] → BlogDraftNode → VoiceMatchNode → SelfCritic → Revise → Storage`. **Fix the `ParallelNode` merge gap here** (keyed slots, merge after). Compare old vs new outputs; write it up.

### Block 6 — Project F: Semantic Search Over Your Corpus
Mostly D's components. `GET /knowledge/search?q=...` → top-k artifacts + optional synthesis. The tool you'll actually use to study. Seeds the #1 client-memory product — **which is now understood as part of the Company Brain (the cross-document retrieval surface).**

### Block 6.5 — Project H: Model Evaluation & Routing Harness *(the spine of the privacy differentiator)*
**This is the project that turns "your data never leaves the building" from a slogan into measured, defensible fact.** *(See DECISIONS D8, D19.)* Still best built after Project D (needs real nodes to evaluate) and pairs naturally with G. An offline tool that runs each node against frontier and local models, scores the outputs (deterministic for structured nodes, bias-corrected LLM-as-judge for prose), and produces empirical per-node routing decisions — "this node is safe on local-70B." Its output is literally the model-routing config the brain reads at startup (D18) — so **Project H is what makes the SMB shell's privacy promise honest and the cost numbers real.** Offline eval, not a runtime router.

**Funding discipline (the 2+3 trap):** the local-model bet may be a year ahead of where most SMBs *feel* the pain, even though the *technology* is ready now (D19). That's fine *only if services revenue funds it.* Let the studio (warm leads, paid diagnostics) pay the bills while H and the appliance mature.

### Parallel Track — Rust Appliance Shell *(whenever you want a Rust session)* — *upgraded scope, June 2026*
**Formerly "Rust Harness CLI." Now explicitly the SMB shell of the Company Brain (DECISIONS D17).** A single-binary terminal control plane that supervises the local Python brain, owns first-run setup, observes runs, and surfaces Project H's cost/quality numbers. It is the privacy promise made physical: "copy one file, double-click, your data stays in the building." **Distinct from Claude Code:** Claude Code does the coding work; this binary commands and observes *your infrastructure*. Rust commands, Python executes — clean HTTP boundary, no rewriting working Python (D6, D18). Start with one command (e.g. trigger one ingestion + query against a local model and print the result); let it grow just-in-time. The "client appliance a non-technical operator runs" is the destination, not the first commit.

### Block 7 — First Paid Diagnostic
When the checkpoint is genuinely met and you've had weeks of research conversations, make a **paid diagnostic offer** to the strongest warm lead. A small fixed-fee engagement (1–2 weeks): map the workflow, deliver a concrete plan with one quick win built and working. **New framing:** where it fits, scope the quick win as a *thin slice of a Company Brain* — ingest one body of their documents, answer real questions from it, on their hardware. That's the wedge demonstrated, not described.

---

## Phase 3: The Differentiating Build

### Block 8 — Project G: Agent Memory System (Episodic → Semantic) — *the Company Brain's "keeps it current" engine*
The most architecturally important and differentiating thing you'll build — durable agent memory with confidence decay and contradiction handling. **This is the half of the Company Brain that turns a static RAG box into a living, self-updating map of how a company works.** It's also the one place the privacy pitch has an honest asterisk: the `consolidation.j2` step must stay on Claude (D19), and Project H proves exactly that. The capstone, given expertise-first. Budget a full, unhurried block. Tests ship with it — and matter most here, because bad memory output degrades everything downstream silently.

**Visibility:** Your strongest technical content — a deep post and a live demo on the Mini on building durable agent memory. **This is also the demo that sells the Company Brain:** show a system that learns a fake company's operations across sessions, handles a contradiction, and gets a fact right that no single document stated.

---

## The Company Brain, Assembled (Phase 3+ → product)

Once D, G, F, and H exist, the Company Brain is *assembled, not invented* — the brain is the sum of parts you built for their own sake. The remaining work is product work, gated on real pull, never built a feature ahead:

| Step | What | Built on | Trigger |
|---|---|---|---|
| **Brain v1 (internal)** | Wire D + G + skills-file emitter behind the clean API | D, G, F, H | After G ships |
| **SMB shell v1** | Rust binary supervises a local brain end-to-end on real docs | Rust track + Brain v1 | First diagnostic client wants it on their hardware |
| **Skills-file emitter** | Turn the structured knowledge into an executable skills file agents act on | Brain v1 + harness skills primitive | When a client has an agent task to automate |
| **Enterprise shell** | Cloud control plane: multi-tenant, SSO, connectors, audit | Brain v1 (unchanged) | An enterprise pulls — not before (D16) |

The trap to avoid is the same as ever: **infinite internal-tool building with no revenue.** The studio earns by shipping client work. Build the thinnest cut of each at the moment of real need, never a feature ahead.

---

## Potential First Clients (Real, Warm Leads)

### CrossFit gym (Jardins) — *likely first diagnostic*
Your personal trainer is part-owner. Workflows are concrete and bounded: sourcing/scheduling trainers, WhatsApp/Instagram marketing automation. Stack is Instagram + WhatsApp; the WhatsApp Business API constraints are exactly the fiddly integration that makes you valuable. Clean first diagnostic. **Note:** a gym this size is *below* the Company-Brain inflection — so here the sale is a bounded automation, not a brain. That's correct; not every client is a brain client. Use it to earn revenue and reps.

### E-commerce (Mercado Livre) — *more interesting, harder, later*
Three pains: trend-spotting (full research-agent territory, bigger than a first engagement), competitor analysis (accuracy is hard — don't be judged against a precision bar you can't hit yet), and invoicing/multi-CNPJ (least AI-flavored, possibly most valuable, most tractable). **The most sellable thing isn't always the most AI-impressive thing.** The invoicing pain may be the better first paid problem here.

### The Company-Brain-shaped lead you don't have yet — *go find one*
Your sharpest wedge (a fast-growing 30–80-person firm feeling the knowledge-fragmentation pain) is **not** represented in your current two warm leads. Action item, from Phase 1 networking onward: in research conversations, listen specifically for the inflection — "we're growing fast and onboarding is painful / only one person knows how X works / we keep re-answering the same questions." That company is your real Company-Brain design partner. Finding one is a networking goal, not a build goal.

---

## Content Plan & Business Development

**The site (`learn-agentic-ai.com`), bilingual PT/EN, two channels:**
- **Blog/Learn — volume:** Project A's pipeline output keeps the site alive at a regular cadence.
- **Blog/Learn — signal:** your own project writeups are the spine.

**High-value posts already identified:**
- **The return post — "The Builder's Arc"** *(drafted — `LinkedIn_Return_Post_Builders_Arc.docx`)* — the April 2025 proposal story: I saw it, I built the pieces anyway, the idea got a name, I left to build it right. Subject-on-you throughout. **This is the anchor that reopens your public presence.** Post the EN version first; write the PT version fresh for the São Paulo audience. Pre-publish: confirm "built on my own time" accuracy; review the denial clause against your NDA comfort.
- **Follow-up: "Retrieval is the easy half"** — the distinction between static RAG (the easy half, which everyone is shipping) and keeping knowledge current (decay, contradiction, confidence — the hard half, which almost nobody gets right). Standalone post, 1–2 weeks after the return. This is the piece that signals technical depth to prospects and hiring managers and quietly separates you from the vector-store-and-call-it-a-brain wave.
- **The slop-projects / early-adopter post** — used Aider before Claude Code existed, shipped fast and a lot, learned that volume isn't quality with AI, and *that's exactly why the harness and context management matter.* One of your strongest pieces.
- The four-bug testing writeup (senior judgment).
- The Project E parallel/specialization comparison (architectural thinking).
- The Helpscout-to-Project-D piece (proven production RAG).
- The Project G memory deep-dive + live demo (frontier-adjacent).
- **The Company Brain thesis post** — the 30→200 story told subject-on-you (D10), the architecture (one brain, two shells), and why privacy-first on-prem is the wedge funded competitors won't take. Founder-narrative anchor; the thing you point a prospect or investor at. *Note: the April 2025 internal proposal is private corroborating evidence for this story — de-identify fully if any of it ever becomes public content.*
- **The "local-by-default, frontier-for-the-few" post** — the honest version of the privacy pitch, with Project H data. Bias-corrected eval as a senior signal.

**Networking before selling:** From Phase 1, have *research conversations*, not pitches. Be known in São Paulo's tech scene.

**Content cadence:** ~1 post per shipped project or notable learning. PT and EN.

**First paid offer:** at the checkpoint, to the warmest lead, as a paid diagnostic. If you hit the checkpoint and still hesitate, send one anyway.

**Job hunt, in parallel:** São Paulo roles, or US/EU companies with a São Paulo office reachable 1–2x/week. The portfolio that wins clients wins interviews. The Company Brain build reads as strongly to a hiring manager (deep agentic/memory/eval systems) as to a client. Keep résumé and LinkedIn current as projects ship.

**The endgame is more defined now, and that's the point (D14):** the destination is a teaching-led studio whose product is the Company Brain, SMB-first and privacy-first, with enterprise as a welcomed later expansion. A job remains a fine outcome and the same work serves it — nothing is foreclosed — but decisions prune faster against a named destination than against three open doors.

---

## Quick Reference: Sequence

| Phase | Block | What | Why | Company Brain role |
|---|---|---|---|---|
| 0 | A | Presence (case studies) + codebase ownership | Foundation | note injection points (D18) |
| 0 | B | Mac Mini harness + revive bilingual site | Harness engineering + infra | hosts the demo |
| 0 | C | Test infra + core hardening + 4 bug fixes | Trustworthy foundation | brain must be trustworthy |
| 0 | D | Shared services + first scaffold + clean API | Reused everywhere | the API is the product surface (Layer 3) |
| 1 | Project A | Content pipeline | Fast rep + content engine | — |
| 1 | Project B | Research agent (thin→hardened) | Most sellable competence | brain-scoping reconnaissance |
| 1 | Project C | Proposal generator | Client-facing; checkpoint skill | how you sell the brain |
| 1 | Project D | Document Q&A + memory (RAG) | Common request; shipped before | **the brain's retrieval half** |
| 2 | Project E | Specialization refactor | Architectural judgment | — |
| 2 | Project F | Semantic search over corpus | Reuse + learning tool | cross-document retrieval surface |
| 2 | Project H | Model eval & routing harness | Proves local-model thesis | **makes the privacy promise honest** |
| 2 | — | First paid diagnostic | Demonstrated expertise | thin-slice brain on client hardware |
| 3 | Project G | Agent memory system | The differentiating centerpiece | **the brain's "keeps it current" engine** |
| ∥ | Rust appliance shell | SMB delivery vehicle | Keeps Rust warm; single-binary privacy promise | **the SMB shell (Layer 2)** |
| 3+ | Brain v1 → shells | Assemble, gate on real pull | Product work | **the product itself** |

*Every project from A onward ships with its own tests. The core was locked down in Phase 0.*

---

*This document serves you — you don't serve it. When life gets in the way, pick up where you left off. The sequence is what matters, not the calendar. The goal is expertise; the Company Brain is the thing expertise builds; everything else follows.*

*Last updated: June 2026 — Company Brain destination + one-brain-two-shells architecture.*
