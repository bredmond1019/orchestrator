---
type: Decision
title: Decisions Registry
description: Log of architectural decisions and settled choices for the python-orchestration-system.
---

# DECISIONS — Settled Choices & Their Reasoning

*Append-only. Records non-obvious decisions so they don't get relitigated. Newest at the bottom.*
*This is the "why" that outlives `STATUS.md`'s deviation log. If a choice here is reversed, add a new entry superseding it — don't edit the old one.*

Format per entry: **what was decided · why · what was rejected and why.**

---

### D1 — Expertise first; business/job follows
**Decided:** The goal is expertise in AI/agentic/harness engineering. A studio, a job, or a product are outcomes that follow, and the plan is built so identical work serves all three.
**Why:** Removes the false choice between "build" and "earn," and resolves the build-vs-sell tension — building the full project set *is* the goal, not a detour from revenue.
**Rejected:** The original "build, ship, get paid in 16 weeks" framing — too revenue-pegged for someone whose real driver is mastery and who has runway.

### D2 — Sequence, not calendar
**Decided:** Plans are ordered by dependency and competence, with no dates assigned. Cadence comes from Brandon's separate whiteboard system.
**Why:** "Let it breathe" — no rush, life events (job hunt, family) make dates brittle. Dependencies are real; timing is not.
**Rejected:** The original week-by-week 16-week schedule — broke on first slip and induced guilt.

### D3 — Drop the Socratic Tutor as the organizing goal
**Decided:** Projects are sequenced by "does this teach something sellable / make me demonstrably expert," not by assembling one app. The Socratic Tutor and physics study are archived in separate docs and excluded from this set.
**Why:** The tutor's dependency graph was distorting the project order; the real goal is general expertise, and the tutor is a crowded, hard-to-defend market (researched).
**Rejected:** Keeping the tutor as the capstone — it pulled the timeline away from expertise/revenue and isn't defensible as a startup as originally conceived.

### D4 — Project G (agent memory) is the centerpiece, retained at full weight
**Decided:** The episodic→semantic memory system stays as the differentiating build.
**Why:** Durable agent memory with confidence decay and contradiction handling is frontier-adjacent, the thing most teams get wrong, and the technical depth that justifies retainer relationships. Given expertise-first, it's the capstone.
**Rejected:** Cutting/deferring it as "premature" — valid under revenue-first, wrong under expertise-first.

### D5 — Testing scope: Option A (core only)
**Decided:** Test the core engine, infrastructure, and services; fix four documented production bugs; do **not** test the reference-only customer-care workflow. Then every new workflow ships with its own tests.
**Why:** Customer-care is disposable reference code Brandon won't extend; testing it spends effort on throwaway. The same testing patterns are learned by testing code that's kept.
**Rejected:** Option B (full sweep including customer-care) — more thorough but wastes time on code that won't ship.

### D6 — Python for orchestration; Rust only where it genuinely wins
**Decided:** The orchestration framework stays Python (I/O-bound — model/DB/network latency dominates). Rust is reserved for genuinely CPU/latency/memory-bound work.
**Why:** Rewriting orchestration in Rust is a *learning* win, not an *architecture* win; microseconds saved are meaningless behind a 2-second model call.
**Rejected:** Porting the engine to Rust for performance — already done once as learning; not worth maintaining as the production path.

### D7 — Rust's home: the CLI now, an inference runtime only later (with data)
**Decided:** The Rust CLI is the near-term Rust project (instant startup, single binary, daily use — keeps the skill warm through genuine use). A Rust local-inference *runtime* layer is kept in mind but **not** in scope; it gets built only if a measured limit makes off-the-shelf serving (Ollama et al.) insufficient.
**Why:** The CLI's Rust advantages are unambiguous and immediate; the runtime's are situational and announce themselves with data. The MIDI tool was dropped — it was an excuse to write Rust, not a real need.
**Rejected:** Forcing a Rust project for its own sake (MIDI tool); pre-building the runtime before a bottleneck is measured.

### D8 — Project H (model eval) is offline evaluation, NOT a runtime router
**Decided:** The eval harness runs occasionally to *produce* per-node routing decisions that bake into each node's `model_provider` at design time. It does not select models per-request at runtime.
**Why:** Static per-node decisions capture most of the value; per-request runtime selection adds latency and complexity for marginal benefit. The expert skill is the measured routing *judgment*, not dynamic switching.
**Rejected:** A runtime model router — overkill; the impressive-but-unjustified trap.

### D9 — Existing production work is foregrounded as case studies
**Decided:** The Internal Support Dashboard (100+ users, 24–48hr wait-time cut, solo, still in daily use), Helpscout automation (solo, production RAG), and AI Scribe (heavy contribution, honest framing — not architect) are featured as proof of existing expertise. Project D is framed as reinforcing the proven Helpscout pattern, not first contact.
**Why:** Brandon undersells; these are stronger than anything not-yet-built and reposition him from "aspiring" to "proven."
**Rejected:** Treating the portfolio as only forward-looking — a material undersell.

### D10 — Public narrative: subject-is-always-you; never name the company
**Decided:** In anything public, the subject of every sentence is Brandon, his work, or his reasons — never the previous company's conduct. The company is never named in posts (LinkedIn carries the factual record).
**Why:** A non-disparagement agreement was signed. The asymmetry (talk about yourself, not them) is both legally safe and more dignified. Two suspected-"slop" repos are de-featured but repurposed as an honest "early adopter, learned volume isn't quality" blog post rather than deleted.
**Rejected:** Any framing that describes the environment ("toxic," "difficult") — that's a claim about them, however softened.

### D11 — Documentation: separate orientation from state; minimum-context by default
**Decided:** Five planning files with distinct jobs — CONTEXT (orientation/router, stable), STATUS (state, volatile), the three plans (content), plus README (navigation) and this DECISIONS file. Pass only the subset a question needs. CONTEXT routes and never duplicates the plans; STATUS mirrors only names, never content.
**Why:** Orientation and state age differently; folding them together makes the whole thing feel stale on every task completion. Single-source-of-truth prevents drift.
**Rejected:** One fat CONTEXT.md containing everything — goes stale fast, forces passing bloat for narrow queries.

### D12 — Repo strategy: one Python monorepo; separate repos only for different languages/deployables
**Decided:** The Python framework and all Python workflows (Projects A–H) live in **one monorepo** — every project is a workflow directory (workflow + nodes + prompts + tests) added alongside the existing ones, not a clone. Separate repos only for genuinely different languages/deploy lifecycles: the Rust CLI, the website.
**Why:** The architecture is "framework as scaffold, projects as attached workflows," with heavy verbatim component reuse across projects. Clone-per-project would fragment the framework into divergent copies with no clean way to propagate fixes. Test for "new repo?": *does it share the Python framework's code/dependency tree?* If yes, same repo.
**Rejected:** Cloning the orchestration repo per project — optimizes for unwanted isolation at the cost of the reuse that is the whole design.

### D13 — Per-repo agent context (CLAUDE.md) and daily log (DEVLOG.md); just-in-time task specs
**Decided:** Each code repo carries its own `CLAUDE.md` (how an agent works in that repo — conventions, build/test commands, the tests-ship-with-every-workflow rule) and `DEVLOG.md` (append-only daily working log, repo-scoped). Per-block work orders are generated **just-in-time** into a `tasks/` folder when a block starts, each with explicit **acceptance criteria** — never pre-written for all blocks.
**Why:** Distinct jobs, no overlap: planning docs describe the endeavor; CLAUDE.md describes working in a repo; DEVLOG records repo history; STATUS rolls up cross-repo state; DECISIONS records why. Generating task specs just-in-time avoids planning-mode procrastination while a fixed template prevents rethinking the convention each time.
**Rejected:** Pre-writing all task specs up front (procrastination trap); a single global devlog (loses repo-local detail); reusing the planning CONTEXT.md as repo agent-context (different reader, different job — hence separate CLAUDE.md per repo).

### D14 — The destination has a named product: the Company Brain *(superseded by D26 as active build; retained as technical reference)*
**Decided:** The three RFS ideas Brandon was drawn to (YC S26: Company Brain, AI Operating System for Companies, Software for Agents) are not three options to choose between — they are three layers of **one** system the plan now names explicitly: a **Company Brain** that ingests a company's scattered knowledge, structures it, keeps it current via the Project G memory engine, and emits an executable skills file agents can act on.
**Why:** Founder-market fit is unusually strong and *lived*, not hypothetical — Brandon watched a previous employer grow 30→200 people, diagnosed the exact knowledge-fragmentation failure Company Brain describes, proposed this literal solution internally, and was turned down, then watched the cost compound.
**Rejected:** Treating the three RFS ideas as a menu and picking one.
*Note: D26 supersedes the "active product build" framing. The architecture remains valid as portfolio depth.*

### D15 — Buyer wedge: fast-growing SMBs caught at the 30–80 inflection, privacy-first *(superseded by D26 as product strategy; retained as technical depth)*
**Decided:** The primary wedge is fast-growing small companies at roughly the 30–80-employee inflection point, privacy-first.
**Why:** Matches lived experience, instant-value-then-compounding, LGPD context in Brazil.
*Note: D26 supersedes the product-company framing. The wedge insight is still useful for scoping contracting conversations.*

### D16 — Architecture: one deployment-agnostic Python brain, two shells *(superseded by D26 as product architecture; retained as engineering discipline)*
**Decided:** Build the Company Brain as one Python core exposing a clean HTTP API. Two shells wrap the same core: SMB Rust appliance + cloud enterprise.
**Why:** Avoids rewrite when scaling; clean layer separation; deployment-agnostic discipline keeps the orchestration core portable.
*Note: D26 supersedes the "two-product-shells" framing. The deployment-agnostic discipline remains good engineering practice.*

### D17 — Rust earns its place as the appliance shell *(scope revised by D26 back to personal CLI)*
**Decided:** Rust's role was upgraded to the SMB appliance shell.
*Note: D26 revises this back. Rust remains the personal ops CLI (D7) — not a product delivery vehicle. Build what you use.*

### D18 — No deployment logic in the brain
**Decided:** Two things are injected, never hardcoded: where models run and where data lives. The first `if running_locally:` inside a node means two products have started being built.
**Why:** This single discipline keeps the brain portable across any deployment target. Already enforced by the existing abstractions (`model_provider` config, `GenericRepository`).
**Rejected:** Branching on environment inside nodes.
*Note: This principle remains fully load-bearing regardless of D26 — it's good engineering, not just product strategy.*

### D19 — The privacy wedge is real today, with honest qualifiers; "local-by-default, frontier-for-the-few"
**Decided:** Local-model privacy is viable now (mid-2026) with two honest qualifiers: hardware requirements (64–128GB unified-memory machine for 70B-class at Q4) and routing honesty (Project G consolidation stays on Claude). The promise is "local-by-default, frontier-for-the-named-few-steps" with Project H producing the auditable list.
**Why:** Open-weight models closed the gap hard. For RAG specifically, retrieval quality matters more than raw model size. The honest, audited version is more defensible.
*Note: The local-model thesis remains worth proving via Project H — both for contracting differentiation and technical honesty. The "never leaves the building" anchor is now a differentiator in contracting conversations where relevant, not a product pitch.*

### D20 — Self-improvement boundary: agents evolve what's gated; new capability enters by PR; the gates are never self-approved
**Decided:** A permanent boundary governs self-evolving capability. The system may freely evolve prompts, routing, memory, and compose new workflows over trusted nodes. New node code enters only through human-reviewed PRs. The validator, test-runner, eval rubric, and consolidation prompt are human-owned gates.
**Why:** The seam between "every action needs approval" (unusable) and "no action needs approval" (unsafe) — the same seam Git/GitHub already found.
*Note: This is a Phase 3+ consideration, retained as a principle for if/when self-improving features are ever built.*

### D21 — Project A is a personal knowledge feed first, blog engine second; digest-always, blog-on-flag; static HTML on the Mini
**Decided:** Dual-input (YouTube/article), dual-output (personal digest always + blog on flag). Static HTML on the Mac Mini, served privately via Caddy. Embeddings stored at write time.
**Why:** Makes Project A useful every morning, compounds into harness work, is the universal device format, teaches transferable patterns.
**Rejected:** Notion (vendor dependency, poor Kindle story); per-item "is this blog-worthy?" decisioning (flag is simpler).

### D22 — Project A MVP boundary: ingestion + store + dumb display now; search and "what I know" via Projects F/G later
**Decided:** Day-1 Project A ships ingestion + store + deliberately dumb reading surface only. No tagging UI, search box, intelligence, cross-device sync, or Kindle EPUB generation.
**Why:** Smart layers attach for free later because embeddings are stored at write time now. Building a personal platform on Day 1 is the infinite-internal-tooling trap.
**Rejected:** Building search/tagging/recommendation now; EPUB generation now.

### D23 — Mac Mini two-face architecture: Caddy+Cloudflare for public, Tailscale for private
**Decided:** Two architecturally separate networking paths. Public face (Caddy + Cloudflare DNS): `learn-agentic-ai.com` accessible to anyone. Private face (Tailscale): all private tooling, no open ports, your devices only.
**Why:** Tailscale cannot make a public website accessible to strangers — it's a private mesh by design. Each concern gets the right tool.
**Rejected:** Routing the public site through Tailscale; Tailscale Funnel for the public site; a unified public setup for everything.

### D24 — Firecrawl role: trafilatura-first for single articles, Firecrawl-fallback for JS/paywall, CrawlSiteNode for site ingestion; free tier until a real crawl demands upgrade
**Decided:** `ArticleExtractionService` uses trafilatura as default, Firecrawl as fallback. Firecrawl's `/crawl` endpoint powers a `CrawlSiteNode` for multi-page site ingestion. Free tier (500 credits/month) until a real crawl demands upgrade. Add `max_calls` guard when Firecrawl runs inside an agent tool loop.
**Why:** trafilatura handles most personal feed extraction for free. Firecrawl earns its place for JS-rendered pages, systematic crawling, and MCP-native access.
**Rejected:** Replacing trafilatura entirely with Firecrawl; self-hosting Firecrawl; skipping the `max_calls` guard.

### D25 — Honcho as Project G reference architecture; personal feed as Honcho validation experiment; build your own G for production
**Decided:** Three choices: (1) Read Honcho source before writing any Project G code; adopt its two-stage pipeline, multi-peer entity model, and NL query interface. (2) Personal knowledge feed uses Honcho for its Phase 3 memory upgrade as a competitive-intelligence experiment. (3) Build custom G for the Company Brain in production — not Honcho — for domain specificity, privacy-first deployment, and full traceability.
**Why:** Honcho is the best available open-source reference (90.4% LongMem S, two-stage pipeline). Using it as reference and personal experiment is the highest-ROI approach. Its token efficiency data (5% median context) is a concrete Project H eval target.
**Rejected:** Replacing Project G entirely with Honcho in production; ignoring Honcho entirely; casual Honcho use without deliberate observation.

### D26 — Goal revised: solo contracting practice, not a studio or product company; Company Brain retained as technical depth and portfolio story only

**Decided:** The primary goal is a **solo contracting practice** — roughly 20 billable hours per week at senior AI engineering rates, with real schedule flexibility and time for music and family. This supersedes the earlier "Company Brain as a product to sell" framing established in D14–D19, though it does not invalidate the technical work those decisions describe. Specifically:

- **The Company Brain architecture** (D14–D19) is retained as technical depth and a portfolio demonstration of what a senior agentic engineer can design and build — not as an active product build or a business strategy. The architecture is still worth understanding and demonstrating; it just isn't being built with the intent to sell it as a product.
- **The one-brain-two-shells architecture** (D16–D18) is no longer load-bearing as a product design. The deployment-agnostic discipline it describes remains good engineering practice, but the Rust appliance shell is now personal ops tooling rather than an SMB delivery vehicle.
- **The privacy wedge and local-model thesis** (D19) remain interesting and worth proving via Project H — both for contracting differentiation and because the technical question is genuinely worth answering. But "never leaves the building" is no longer the anchor of a product pitch; it's a differentiator in contracting conversations where it's relevant.
- **Decisions D14–D25** are retained as historical record. Their technical reasoning remains sound. What changes is the *destination* they were pointed at.

**The contracting practice goal in concrete terms:** 1–2 retainer clients at $2,000–5,000/month each, plus occasional project work at $5,000–15,000 per engagement. Entry via Upwork (fastest path), Toptal (higher rates, worth pursuing once Project D ships), and LinkedIn/direct relationships. The competence checkpoint (walk into an unfamiliar SMB and name three automatable workflows in 30 minutes) remains the "ready to pitch" bar — unchanged.

**Why:** Brandon wants schedule flexibility, time for music, and income from interesting engineering work — not a company to run. The expertise-first project sequence builds the same skills either way; this revision removes the product overhead (the SMB wedge narrative, the enterprise expansion planning, the Rust appliance as delivery vehicle) that was adding complexity and cognitive load without serving the actual goal. A solo contracting practice is a complete, sustainable end state, not a stepping stone to something bigger. Treating it that way means the plan can stop at the right place.

**What is explicitly NOT rejected:** the project library itself (A–H), the technical architecture of the orchestration framework, the Company Brain's technical design as a portfolio story, the Honcho reference work for Project G, the model eval discipline of Project H, the testing standards, or the public narrative approach. The expertise is real and the work is the same; only the destination label and the product-build overhead change.

**Rejected:** Continuing to treat the contracting practice as a stepping stone toward a studio/product (adds scope and pressure without serving the goal); dropping the ambitious technical projects in favor of shallow gig work (undersells the expertise and leads to commodity rates); treating "flexible hours + music time" as something to be earned later rather than designed for now.

---
*To add a decision: append the next D-number with what / why / rejected. To reverse one: append a new entry superseding it by number; leave the original intact.*
*D1–D13: foundational sequencing and architecture decisions. D14–D25: Company Brain product architecture (retained as technical reference; superseded as primary goal by D26). D26: goal revised to solo contracting practice.*
