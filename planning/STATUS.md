# STATUS — Current State & Progress

*The volatile companion to `CONTEXT.md`. Update this file as you go; leave the plans clean.*
*Pass this alongside CONTEXT + the relevant plan section when you want "what's next" or "tasks this week."*

**Last updated:** 2026-06-10 — Block D: Tasks 1, 2, 3, 4, 9, 11 merged; Tasks 5, 6, 7, 8, 10 escalated (docs/api-reference.md merge conflicts need manual resolution)
**Current focus:** Phase 0, Block D — Task 5 (escalated — resolve docs/api-reference.md merge conflict, then resume /sdlc-block phase0-blockD)

---

## How to Read / Update This File

- Status values: `Not started` · `In progress` · `Done` · `Blocked` · `Skipped`
- This table mirrors only the **names** of phases/blocks/projects from the plans — never their content. Content lives in the plans (single source of truth).
- When something changes, update the row's status and the **Current focus** line above, bump **Last updated**, and add a line to the **Decisions & Deviations Log** if reality diverged from the plan.
- Keep it terse. This file is meant to be cheap to pass to an LLM.

---

## Progress Table

### Phase 0 — Foundation
| Block | What | Status | Notes |
|---|---|---|---|
| A | Digital presence + codebase ownership | In progress | Tasks 1–2 done (core engine + support nodes read; architecture review docs generated); Tasks 3–9 paused — manual/personal tasks (LinkedIn, GitHub triage, etc.) deferred while agent-executable work proceeds |
| B | Mac Mini agentic harness + revive site | In progress | Public face DONE (Cloudflare Tunnel). Private face IN PROGRESS: Tailscale installed on the Mini with **unattended access** — FileVault off + auto-login + Tailscale connect-on-login, so it survives reboot/crash and is reachable hands-free at `brandons-mac-mini` (100.104.113.100), zero open ports; **MacBook Pro joined the tailnet and SSH verified**. Remaining to connect to the tailnet: Pixel tablet + phone (Kindle TBD); private tooling (personal feed, orchestration API, Celery) once those services exist; a **Claude Code remote-trigger path** over Tailscale and/or webhooks. See DECISIONS D23 |
| C | Test infra + core hardening + 4 bug fixes | Done | All 14 tasks complete: pytest scaffold; 4 production bugs fixed (`GenericRepository.exists()`, ghost-row, import-time side effects, router key coupling); full unit test suite written for `TaskContext`, `WorkflowSchema`, `WorkflowValidator`, `Workflow.run()`, `BaseRouter`/`RouterNode`, `ParallelNode`, `PromptManager`, `GenericRepository` CRUD; LinkedIn visibility post drafted; final validation confirmed `uv run pytest` passes with zero failures and all import checks clean |
| D | Shared services + first scaffold | In progress | Tasks 1, 2, 3, 4, 9, 11 merged; Tasks 5, 6, 7, 8, 10 escalated (docs/api-reference.md merge conflicts — resolve then resume /sdlc-block phase0-blockD) |

### Phase 1 — Sellable Competence
| Project | What | Status | Notes |
|---|---|---|---|
| A | Content pipeline (YouTube/Article → personal digest + optional blog) | Not started | Personal knowledge feed (static HTML on Mini) is the Day-1 win; digest-always, blog-on-flag; `FetchArticleNode` new. Ships with tests; deploy to Mini. See DECISIONS D21–D22 |
| B | Research agent (thin → hardened) | Not started | Thin cut first (~50 lines, raw tool loop) |
| C | Proposal generator | Not started | PT + EN; run on warm leads as practice |
| D | Document Q&A + session memory (RAG) | Not started | Reinforces proven Helpscout production pattern |

*→ Competence checkpoint review after Project D.*

### Phase 2 — Depth + First Paid Work
| Item | What | Status | Notes |
|---|---|---|---|
| E | Specialization refactor | Not started | Fix ParallelNode merge gap here |
| F | Semantic search over corpus | Not started | Mostly D's components |
| H | Model eval & routing harness | Not started | Flexible placement; needs real nodes (after D) |
| — | First paid diagnostic | Not started | Waits for competence checkpoint, not a date |

### Phase 3 — The Differentiating Build
| Project | What | Status | Notes |
|---|---|---|---|
| G | Agent memory system — two-stage pipeline, multi-peer model | Not started | Read Honcho source first (D25). Two-stage: ingest-time fast extraction + dream-time consolidation. Multi-peer schema. NL query interface. The centerpiece. |

### Parallel Track
| Track | What | Status | Notes |
|---|---|---|---|
| Rust appliance shell | SMB single-binary delivery vehicle — the privacy promise made physical; commands + observes the Python brain over HTTP | Not started | Anytime after harness exists; start with one command (ingest + query + print cost). Formerly "Rust CLI" — see DECISIONS D17 |

---

## Business Development / Visibility (runs continuously, loosely)
| Item | Status | Notes |
|---|---|---|
| LinkedIn overhaul (case studies foregrounded) | Not started | Block A |
| GitHub triage (pin engine; de-feature slop repos) | Not started | Block A |
| Revive site + publish return post | In progress | Block B — site REVIVED (`learn-agentic-ai.com` live via Cloudflare Tunnel). Return posts still to publish: EN draft (`LinkedIn_Return_Post_Builders_Arc.docx`) and PT draft (`LinkedIn_Return_Post_Retorno_PT.docx`); review usage-note pre-publish checks before posting |
| Network: list of 10 warm contacts | Not started | During Project A |
| Research conversations (not pitches) | Not started | From Phase 1 |
| Job applications (São Paulo / SP-office roles) | Not started | Continuous |
| Content posts (cadence: ~1 per shipped project) | Not started | PT + EN |

---

## Decisions & Deviations Log

*Record anything where reality diverged from the plan, or a notable choice was made. Keeps the plans clean and stable.*

- **2026-06-05 — Block A partially paused; Block C started out of sequence.** Block A tasks 3–9 are personal/manual tasks (LinkedIn, GitHub triage, site work) that can't be delegated to an agent. Block C was started ahead of Block A completion because it is fully agent-executable. This is intentional — the sequencing principle is dependency order, and Block C has no dependency on the Block A personal tasks.
- **2026-06-10 — Mac Mini Tailscale unattended access (Block B private face, first slice).** Installed the Tailscale standalone app on the Mini, joined the tailnet (MagicDNS `brandons-mac-mini`, IP `100.104.113.100`), and made it reachable hands-free after any reboot or crash; MacBook Pro joined and SSH-verified. macOS has no true before-login Tailscale (open issue tailscale#987), and FileVault gates *all* networking at the pre-boot unlock screen — so unattended recovery required **disabling FileVault** + enabling **auto-login** + Tailscale **connect-on-login**. FileVault-off is an accepted tradeoff: the threat model here is network exposure (handled by Tailscale + zero open ports), not theft of a physically-secured home box; the encryption-preserving alternatives (`fdesetup authrestart` for planned reboots only; an IP-KVM for unplanned crashes) were noted and deferred. **Possible DECISIONS entry (Brandon to confirm):** record the FileVault-off-for-unattended-access tradeoff as a new D-number. Remaining for the private face: add Pixel tablet/phone (Kindle TBD); bind the orchestration API/Celery/personal feed once they exist; stand up a Claude Code remote-trigger path over Tailscale and/or webhooks. Ops/infrastructure work — no repo code changed.
- **2026-06-10 — Block B public face live; Tailscale next; SDLC orchestration tooling added.** Stood up `learn-agentic-ai.com` to the public on the Mac Mini via **Cloudflare Tunnel + Cloudflare DNS** (not the originally-noted Caddy path — the tunnel removes the need to open inbound ports, which fits the privacy-first posture). This completes Block B's public face / site-revival half. Remaining Block B work is the **private face**: Tailscale on the Mini + all devices, with the personal feed, orchestration API, and Celery behind it. Per user, Block B (Tailscale) and Block D (shared services) now proceed **in parallel**. Separately, added `.claude/workflows/sdlc-block.js` — a block-level SDLC orchestration workflow that drives an entire `tasks.md` to completion across dependency-ordered waves of parallel `/sdlc-task` pipelines, each in its own git worktree, with bounded retries, failure triage, escalation, and ordered additive-union merges. This is agentic harness tooling (the engine that ran Block C), not a planning block.
- **June 2026 — Honcho research + D25.** Reviewed Honcho (Plastic Labs, open-source reasoning-first memory, 90.4% LongMem S). Decisions: Honcho as Project G reference architecture (two-stage pipeline, multi-peer entity model, NL query interface all adopted); personal knowledge feed will use Honcho as a validation/competitive-intelligence experiment when the memory smart-layer arrives (Phase 3 upgrade); Company Brain memory layer built custom (domain-tuned, privacy-first, fully traceable). Project G schema evolved to multi-peer (`Peer`/`AgentEpisode`/`SemanticMemory`). Ingest-time extraction added as a separate (fast, local-model candidate) stage. Honcho benchmark data (5% median context, ingest-model + query-model split) added as Project H design targets. Updated: Agentic plan (Project G section, Project A personal feed section, model reference, components table, portfolio one-liner), Master Plan (Block 8), DECISIONS (D25), CONTEXT, this file. Two-face Mini architecture settled: Caddy+Cloudflare for public site (learn-agentic-ai.com, accessible to anyone with the URL), Tailscale for all private tooling (personal feed, API, Celery, etc. — your devices only, no open ports). Critical distinction: Tailscale alone cannot serve a public portfolio site. Firecrawl adopted with defined role: trafilatura-first for single article extraction, Firecrawl as fallback for JS-heavy pages, `CrawlSiteNode` for Company Brain site ingestion. `trafilatura` added to deps. Updated: Master Plan (Block B, Block D), Agentic plan (tech stack, Project A build notes, components table, Company Brain assembly), CONTEXT, this file. Reframed from "YouTube→blog" to a dual-input (YouTube/article), dual-output (personal digest always + blog on flag) pipeline — a personal knowledge feed served as static HTML on the Mini, readable on tablet/phone/Kindle. It's the one-person dogfood of the Company Brain; `FetchArticleNode`/`ArticleExtractionService` reused by the real product. MVP boundary set: ingestion + store + dumb display now; search/"what I know" via Projects F/G later over the same embeddings. New dep: `trafilatura`. Updated: Projects Plan (Project A, shared services, reference tables), Master Plan (Block 1), CONTEXT, this file. Still Not started.
- **June 2026 — Major planning revision (no code moved).** Strategy session produced decisions D14–D20. Destination now named: the **Company Brain** (privacy-first, SMB-wedge at 30–80-person inflection, enterprise welcomed later). Architecture settled: one deployment-agnostic Python brain, two shells (Rust SMB appliance + future enterprise cloud). Rust track upgraded from ops-CLI to the SMB appliance shell (D17). Self-improvement boundary established: evolve-what's-gated / new-capability-by-PR / never-self-approve-the-gates (D20). Local-model privacy wedge confirmed viable now with honest qualifier: local-by-default, frontier-for-the-named-few-steps (D19). All plan documents updated (Master Plan, Projects Plan, CONTEXT, CLAUDE, README, STATUS); Test Plan unchanged. **EN and PT LinkedIn return posts drafted and ready to publish** — pending pre-publish checks in usage notes. No phase/block status changed; all work remains Not started.

---

## Quick Self-Check Before Asking "What's Next"

1. Is the **Current focus** line above accurate?
2. Are any rows `In progress` that are actually `Done`?
3. Is anything `Blocked` that needs flagging?

If yes to accuracy, pass CONTEXT + this file + the relevant plan section and ask away.

---

*State only. For what things mean, see the plans. For orientation, see `CONTEXT.md`.*
