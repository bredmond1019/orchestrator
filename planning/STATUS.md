# STATUS — Current State & Progress

*The volatile companion to `CONTEXT.md`. Update this file as you go; leave the plans clean.*
*Pass this alongside CONTEXT + the relevant plan section when you want "what's next" or "tasks this week."*

**Last updated:** June 2026 — Project A extended to personal knowledge feed (D21–D22)
**Current focus:** Not yet started — beginning Phase 0, Block A

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
| A | Digital presence + codebase ownership | Not started | LinkedIn overhaul, GitHub triage, read core engine, 5 orientation questions |
| B | Mac Mini agentic harness + revive site | Not started | Two-face architecture: Caddy+Cloudflare (public site) + Tailscale (private tooling). Install Tailscale on Mini + all devices; revive `learn-agentic-ai.com` on public face. See DECISIONS D23 |
| C | Test infra + core hardening + 4 bug fixes | Not started | Option A scope; fix the 4 documented bugs |
| D | Shared services + first scaffold | Not started | pgvector, Embedding/Transcript/Search/Chunking services; scaffold Project A |

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
| G | Agent memory system (episodic→semantic) | Not started | The centerpiece; consolidation prompt is the hard part |

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
| Revive site + publish return post | Not started | Block B — EN draft written (`LinkedIn_Return_Post_Builders_Arc.docx`) and PT draft written (`LinkedIn_Return_Post_Retorno_PT.docx`); review usage-note pre-publish checks before posting |
| Network: list of 10 warm contacts | Not started | During Project A |
| Research conversations (not pitches) | Not started | From Phase 1 |
| Job applications (São Paulo / SP-office roles) | Not started | Continuous |
| Content posts (cadence: ~1 per shipped project) | Not started | PT + EN |

---

## Decisions & Deviations Log

*Record anything where reality diverged from the plan, or a notable choice was made. Keeps the plans clean and stable.*

- *(none yet — project not started)*
- **June 2026 — Tailscale + Firecrawl adopted (D23–D24).** Two-face Mini architecture settled: Caddy+Cloudflare for public site (learn-agentic-ai.com, accessible to anyone with the URL), Tailscale for all private tooling (personal feed, API, Celery, etc. — your devices only, no open ports). Critical distinction: Tailscale alone cannot serve a public portfolio site. Firecrawl adopted with defined role: trafilatura-first for single article extraction, Firecrawl as fallback for JS-heavy pages, `CrawlSiteNode` for Company Brain site ingestion. `trafilatura` added to deps. Updated: Master Plan (Block B, Block D), Agentic plan (tech stack, Project A build notes, components table, Company Brain assembly), CONTEXT, this file. Reframed from "YouTube→blog" to a dual-input (YouTube/article), dual-output (personal digest always + blog on flag) pipeline — a personal knowledge feed served as static HTML on the Mini, readable on tablet/phone/Kindle. It's the one-person dogfood of the Company Brain; `FetchArticleNode`/`ArticleExtractionService` reused by the real product. MVP boundary set: ingestion + store + dumb display now; search/"what I know" via Projects F/G later over the same embeddings. New dep: `trafilatura`. Updated: Projects Plan (Project A, shared services, reference tables), Master Plan (Block 1), CONTEXT, this file. Still Not started.
- **June 2026 — Major planning revision (no code moved).** Strategy session produced decisions D14–D20. Destination now named: the **Company Brain** (privacy-first, SMB-wedge at 30–80-person inflection, enterprise welcomed later). Architecture settled: one deployment-agnostic Python brain, two shells (Rust SMB appliance + future enterprise cloud). Rust track upgraded from ops-CLI to the SMB appliance shell (D17). Self-improvement boundary established: evolve-what's-gated / new-capability-by-PR / never-self-approve-the-gates (D20). Local-model privacy wedge confirmed viable now with honest qualifier: local-by-default, frontier-for-the-named-few-steps (D19). All plan documents updated (Master Plan, Projects Plan, CONTEXT, CLAUDE, README, STATUS); Test Plan unchanged. **EN and PT LinkedIn return posts drafted and ready to publish** — pending pre-publish checks in usage notes. No phase/block status changed; all work remains Not started.

---

## Quick Self-Check Before Asking "What's Next"

1. Is the **Current focus** line above accurate?
2. Are any rows `In progress` that are actually `Done`?
3. Is anything `Blocked` that needs flagging?

If yes to accuracy, pass CONTEXT + this file + the relevant plan section and ask away.

---

*State only. For what things mean, see the plans. For orientation, see `CONTEXT.md`.*
