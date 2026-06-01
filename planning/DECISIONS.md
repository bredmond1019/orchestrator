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
**Why:** Durable agent memory with confidence decay and contradiction handling is frontier-adjacent, the thing most teams get wrong, and underpins two of the three product ideas. Given expertise-first, it's the capstone.
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
**Decided:** The Rust Harness CLI is the near-term Rust project (instant startup, single binary, daily use — keeps the skill warm through genuine use). A Rust local-inference *runtime* layer is kept in mind but **not** in scope; it gets built only if a measured limit makes off-the-shelf serving (Ollama et al.) insufficient.
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
**Decided:** The Python framework and all Python workflows (Projects A–H) live in **one monorepo** — every project is a workflow directory (workflow + nodes + prompts + tests) added alongside the existing ones, not a clone. Separate repos only for genuinely different languages/deploy lifecycles: the Rust CLI, the website, a future Rust runtime.
**Why:** The architecture is "framework as scaffold, projects as attached workflows," with heavy verbatim component reuse across projects. Clone-per-project would fragment the framework into divergent copies with no clean way to propagate fixes. Test for "new repo?": *does it share the Python framework's code/dependency tree?* If yes, same repo.
**Rejected:** Cloning the orchestration repo per project — optimizes for unwanted isolation at the cost of the reuse that is the whole design.

### D13 — Per-repo agent context (CLAUDE.md) and daily log (DEVLOG.md); just-in-time task specs
**Decided:** Each code repo carries its own `CLAUDE.md` (how an agent works in that repo — conventions, build/test commands, the tests-ship-with-every-workflow rule) and `DEVLOG.md` (append-only daily working log, repo-scoped). Per-block work orders are generated **just-in-time** into a `tasks/` folder when a block starts, each with explicit **acceptance criteria** — never pre-written for all blocks.
**Why:** Distinct jobs, no overlap: planning docs describe the endeavor; CLAUDE.md describes working in a repo; DEVLOG records repo history; STATUS rolls up cross-repo state; DECISIONS records why. Generating task specs just-in-time avoids planning-mode procrastination while a fixed template prevents rethinking the convention each time.
**Rejected:** Pre-writing all task specs up front (procrastination trap); a single global devlog (loses repo-local detail); reusing the planning CONTEXT.md as repo agent-context (different reader, different job — hence separate CLAUDE.md per repo).

---
*To add a decision: append the next D-number with what / why / rejected. To reverse one: append a new entry that supersedes it by number; leave the original intact.*
