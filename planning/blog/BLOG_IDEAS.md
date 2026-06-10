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

**Reach Your Mac Mini From Anywhere: Unattended Tailscale, and the FileVault Gotcha Nobody Mentions** `[Both]`
A real-world walkthrough of turning a home Mac Mini into a headless box you can SSH into from any device, from anywhere, with zero open ports. The hook is the part the tutorials skip: macOS can't run Tailscale before login (tailscale#987), and FileVault gates *all* networking at the pre-boot unlock screen — so VNC, SSH, and Tailscale are equally useless until the disk is unlocked. The honest fix (disable FileVault + auto-login + connect-on-login), the threat-model reasoning that makes it acceptable on a physically-secured box, and the encryption-preserving alternatives (`fdesetup authrestart`, an IP-KVM) for those who need them. Concrete, opinionated, reasoned — not a copy-paste recipe.
Reference: DEVLOG 2026-06-10 (Block B private face); DECISIONS D23

**Host Your Own Site From a Mac Mini at Home — Cloudflare Tunnel, Zero Open Ports** `[Both]`
How `learn-agentic-ai.com` got served to the public from a Mac Mini on a home network without forwarding a single port or exposing the home IP. The angle: a Cloudflare Tunnel (`cloudflared`, outbound-only) flips the usual self-hosting model — the origin reaches out to Cloudflare's edge instead of the internet reaching in, so DNS/TLS/DDoS sit in front and the box stays closed. Why this beats port-forwarded Caddy for a privacy-first setup, and why it's *not* the same as Tailscale Funnel (public vs. private faces, the right tool for each).
Reference: DECISIONS D23 (2026-06-10 amendment); DEVLOG 2026-06-10 (Block B public face)

---

## Suggested (not yet added — revisit after more projects are built)

- **The TaskContext Pattern: How to Pass State Through an Agentic Pipeline Without Going Insane** `[Both]` — Most tutorials show single-agent calls; real pipelines need shared mutable state. The `nodes` dict-as-ledger pattern, why it beats explicit parameter threading, and the one thread-safety trap to avoid. *(Want more projects built before writing this.)*

- **Local Models vs Frontier Models: An Honest Framework for "Runs on Your Hardware"** `[LI]` — The privacy claim is only honest if you know *which steps* can actually run locally. Walk through the classification: local-by-default for extraction/routing/classification, frontier for consolidation/synthesis/judgment. Practical decision table. *(Revisit when reaching Project H.)*

- **Event-Driven AI Pipelines: Why FastAPI → Celery → Workflow DAG Is the Right Architecture for Production** `[Blog]` — The accept-and-delegate pattern, why you don't want LLM calls blocking your HTTP response, and how a Workflow DAG gives you testability that a chain of function calls doesn't. *(Needs a few more projects built to have enough concrete examples.)*
