# Blog / LinkedIn Post Ideas

Capture ideas here mid-session; sweep into Google Tasks or the blog repo when drafting.
Format: **Title idea** — one-line hook. Tag the output target: `[LI]` = LinkedIn, `[Blog]` = long-form, `[Both]`.

---

## Queued

**Welcome Back: The Builder's Arc** `[LI]`
EN and PT drafts already written (`LinkedIn_Return_Post_Builders_Arc.docx`, `LinkedIn_Return_Post_Retorno_PT.docx`). Pre-publish de-identification check required before posting — see CONTEXT.md public-narrative rule and DECISIONS D10.

**I Automated My Entire Dev Lifecycle with Claude Code Slash Commands** `[Both]`
Walkthrough of the `/generate-tasks → /implement → /test → /review-task → /document → /log-work` pipeline built in `.claude/commands/`. Each command is a markdown file that drives a fresh agent context; together they form a repeatable, file-traced SDLC. Angle: meta-level AI tooling — using AI to build AI systems more reliably.
Reference: `.claude/commands/README.md`

**Testing Agentic Systems: What's Actually Worth Testing (and What Isn't)** `[Both]`
Under-discussed topic. Three layers: (1) unit tests for the plumbing — routing logic, context propagation, schema validation, with the LLM mocked; (2) e2e tests for the full pipeline — things agents overlook when writing unit tests only (silent routing misses, context key collisions, parallel node merge gaps); (3) how the SDLC slash commands enforce the discipline — the `/test` and `/review-task` steps run a fresh suite as an authoritative gate, not a vibe check. The four production bugs in this project's Block C make good concrete examples of what slips through without this.

---

## Suggested (not yet added — revisit after more projects are built)

- **The TaskContext Pattern: How to Pass State Through an Agentic Pipeline Without Going Insane** `[Both]` — Most tutorials show single-agent calls; real pipelines need shared mutable state. The `nodes` dict-as-ledger pattern, why it beats explicit parameter threading, and the one thread-safety trap to avoid. *(Want more projects built before writing this.)*

- **Local Models vs Frontier Models: An Honest Framework for "Runs on Your Hardware"** `[LI]` — The privacy claim is only honest if you know *which steps* can actually run locally. Walk through the classification: local-by-default for extraction/routing/classification, frontier for consolidation/synthesis/judgment. Practical decision table. *(Revisit when reaching Project H.)*

- **Event-Driven AI Pipelines: Why FastAPI → Celery → Workflow DAG Is the Right Architecture for Production** `[Blog]` — The accept-and-delegate pattern, why you don't want LLM calls blocking your HTTP response, and how a Workflow DAG gives you testability that a chain of function calls doesn't. *(Needs a few more projects built to have enough concrete examples.)*
