---
type: Handoff
created: 2026-06-20
---

# Handoff — Project A audited & buttoned-up; Project B is next

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why
This session did a post-ship coverage audit of **Phase 1, Project A** (`content_pipeline`,
shipped DONE on 2026-06-20, 295 tests green) before starting Project B. The verdict: coverage is
already strong — every node, the routers, fetch error paths, the digest renderer, and both
integration paths have real behavior-level tests. We did **not** manufacture a test-writing
effort. Instead we recorded a small, honest backlog and reconciled the cross-repo reuse spec
(`learn-ai/planning/5.1-reuse-for-project-a/tasks.md`) against what actually shipped. The repo is
otherwise clear to begin **Project B — the research agent** (thin cut first: one `ToolUseNode` +
Tavily, ~50 lines, raw tool loop; harden later when a real prospect pulls).

## Completed this session
- **Coverage audit of Project A** — mapped all 10 content_pipeline nodes + schema + model + graph
  endpoint to their tests; confirmed `uv run python -m pytest` = 295 passed, ruff clean.
- **Wrote `planning/phase1-projectA/follow-ups.md`** — the durable backlog (untracked, will be
  committed this session): 2 deferred tests, 2 reuse carryovers, 1 scope decision.
- **Updated `planning/status.md`** — refreshed `Last updated` line + added a visible "Project A
  open follow-ups (non-blocking)" callout block pointing at the follow-ups file.
- **Reconciled the reuse spec** — `learn-ai/planning/5.1-reuse-for-project-a/tasks.md` Notes
  section now records each spec item as Done / Carried-over / Decision-pending / Skipped. (That
  edit is in the **learn-ai** repo, a separate git repo — commit it there separately if desired;
  this session's `/commit` only covers the orchestration repo.)

## Remaining work
- **Start Project B (research agent)** — primary next task. Thin cut: one `ToolUseNode` + Tavily,
  ~50 lines, raw tool loop. New workflow dir alongside `customer_care`/`content_pipeline` per
  CLAUDE.md (workflow + nodes + schema + `.j2` prompts + tests + registry entry). Use
  `uv run createworkflow` to scaffold. Generate its task spec first (see first command below).
- **Project A follow-ups (non-blocking, do anytime)** — all in
  `planning/phase1-projectA/follow-ups.md`:
  - `_is_youtube_url` anti-spoof/subdomain test cases → `tests/workflows/content_pipeline/test_fetch_nodes.py`
  - document that `SelfCriticNode.approved` is intentionally inert → `tests/workflows/test_content_blog_branch.py`
  - transcript-corpus golden fixtures; cross-check `SummaryOutput` vs site summary template

## Open questions / choices
- **PT-BR translation prompt — scope decision needed before scheduling.** The reuse spec assumed a
  `translate_ptbr.j2` + translation `AgentNode`; it was never built (shipped pipeline is digest +
  optional EN blog only). Decide whether PT-BR translation belongs to Project A (a dropped MVP
  item) or to content-publishing (tied to the PT+EN brand cadence, likely later/elsewhere) before
  anyone builds it. Do **not** build it on autopilot. Details in `follow-ups.md` item 2.3.
- Otherwise clear to proceed on Project B.

## Context the next agent needs
- The framework instantiates nodes with **zero constructor args** (no DI seam) — nodes reach
  persistence via the `GenericRepository` + `db_session` factory, never constructor injection
  (CLAUDE.md rule 7). Project A's `storage_node.py` is the reference for this pattern.
- Standing rules that bite on a new workflow: every workflow ships with tests (rule 1); no
  hardcoded prompts — `.j2` only via `PromptManager` (rule 2); register in
  `app/workflows/workflow_registry.py` (rule 6); `customer_care` is frozen reference (rule 3).
- The reuse-spec reconciliation edit lives in the **learn-ai** repo, not this one — it won't appear
  in this repo's `/commit`.

## First command after `/prime`
`/generate-tasks` for Phase 1 Project B (research agent) — or `/feature` to plan the thin cut — then `uv run createworkflow` to scaffold the workflow dir.
