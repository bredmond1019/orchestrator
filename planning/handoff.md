---
type: Handoff
created: 2026-06-23
---

# Handoff — Build out the public-API + Telegram-bot plan

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why
This session produced a finished, approved implementation plan (no code yet) for a **new
workstream**, separate from the `phase1-projectE` focus shown in `status.md`. The goal: expose
the orchestration API publicly at `api.learn-agentic-ai.com` through the existing Cloudflare
Tunnel (the same one already serving the `learn-ai` frontend at `learn-agentic-ai.com` →
`localhost:3003`), gated by defense-in-depth auth, and add a **long-poll, fire-and-forget
Telegram bot** as the first client — Brandon sends a YouTube/article link from his phone, the
bot fires a `CONTENT_PIPELINE` run and replies "Queued ✅"; the digest is read later from the
static digest site (no result is returned to Telegram). The full plan, including verified
current-state facts and a "settled decisions, do not relitigate" section, lives at
`planning/plans/expose-api-and-telegram-bot.md`. Brandon explicitly asked that this be picked up
by a **fresh agent** who runs `/generate-tasks` against that plan.

## Completed this session
- Explored the codebase (API surface, Cloudflare Tunnel setup, data contract) and confirmed key
  facts now captured in the plan: no auth/CORS on the API today (`app/main.py`); `POST /events/`
  returns the Celery `task_id` **not** the `event_id`; `GET /events/{id}` is reserved-but-unbuilt
  (`docs/data-contract.md` §7); the `cloudflared` config lives on the Mac Mini outside the repos.
- Resolved the design with Brandon across two rounds of questions: **long-poll now / webhook
  later**, **fire-and-forget** (no result polling, so no `GET /events/{id}`, no response-shape
  change, **no data-contract shape bump**), **still expose the public API** (portfolio / future /
  `bastion`), **defense-in-depth auth** (Cloudflare Access edge token + in-app `X-API-Key`), and
  **bot lives in `integrations/telegram/`** (outside `app/`).
- Wrote the plan to `planning/plans/expose-api-and-telegram-bot.md` (OKF `type: Plan` frontmatter,
  matching the `price-scout-workflow.md` convention; no `index.md` added because that directory
  has never had one).

## Remaining work
1. **Run `/generate-tasks`** against `planning/plans/expose-api-and-telegram-bot.md` to produce a
   `tasks.md`, then execute (likely via `/sdlc-block` or `/sdlc-run`). This is the next action.
2. Implement per the plan's §1–§6: API auth + CORS (`app/api/security.py`, `app/main.py`,
   `app/api/endpoint.py`); the `integrations/telegram/` bot (long-poll, `/digest <url>`);
   `[telegram]` optional-deps group in `pyproject.toml`; the `telegram_bot` Docker service; env
   vars; tests; docs.
3. **Manual ops steps** (Brandon, on the Mac Mini — not agent-executable): cloudflared ingress
   rule + DNS route + tunnel restart, Cloudflare Access app + service token, and creating the bot
   via Telegram @BotFather. These are documented in the plan §4.

## Open questions / choices
None — clear to proceed. The core design decisions are settled and recorded in the plan's
"Open decisions already settled (do not relitigate)" section. Do not reopen long-poll-vs-webhook
or fire-and-forget.

## Context the next agent needs
- This workstream is **independent of `phase1-projectE`** (Specialization refactor), which is
  still the standing "current focus" in `status.md` and remains Not started. Confirm with Brandon
  which to drive if it's ambiguous — but this session's intent was clearly to kick off the
  API+bot plan next.
- **No data-contract version bump** is needed: auth is an operational change, not a shape change;
  `bastion` is a read-only Postgres observer that never POSTs, so it needs no re-pin (only a
  patch-level clarification note in `docs/data-contract.md`).
- Keep the API bound to `127.0.0.1:8080` — do **not** switch to `0.0.0.0` (cloudflared runs on the
  host and reaches localhost directly; localhost-only is more secure). An exploration agent
  suggested `0.0.0.0`; that was rejected.
- `CONTENT_PIPELINE` event schema is `{url, make_blog=false, ...}`; the digest summary lands in the
  `SummarizerNode` output within `task_context.nodes`.

## First command after `/prime`
`/generate-tasks` against `planning/plans/expose-api-and-telegram-bot.md`
