---
type: Reference
title: orchestrator Memory
description: Repo-scoped durable memory for orchestrator — episodic notes, preferences, superseded facts. Committed and portable.
doc_id: memory
layer: [factory]
project: orchestrator
status: active
keywords: [memory, episodic, preferences, durable, portable]
related: [knowledge, context, status, planning-index]
---

# Memory — orchestrator

Repo-scoped **durable memory**: episodic notes, operator preferences, and superseded facts that
must survive a handoff and travel with the repo. Committed and portable — distinct from the global
`~/.claude/.../memory/` auto-memory (which is operator-level and stays on one machine).

Use this for project facts worth remembering across sessions. Promote durable "how it works"
knowledge to `knowledge.md`; promote settled choices to `decisions/`. Do not duplicate the global
auto-memory here.

## Notes

_Dated episodic entries — what was tried, what was decided in-flight, what to remember next time._

- **sdlc-block baseline-snapshot writes an untracked file that blocks worktree merges**
  The `baseline-snapshot` stage writes `planning/<concept>/sdlc/reports/net-new-lint-baseline.json` to the working tree but does not commit it. When subsequent tasks attempt to merge their worktrees, the git safety check blocks on the untracked file. Cost: required a full second block invocation (~531k wasted tokens). Fix: commit the baseline file atomically in setup ("chore: sdlc baseline"). Until fixed, manual recovery is to commit the file and re-run `/sdlc-block`.
  source: planning/archive/expose-api-and-telegram-bot/harness-update-review.md · date: 2026-06-23 · supersedes: — · freshness: 2026-06-27

- **sdlc-block has no cross-invocation resume: restart re-runs harness-config + analyze from scratch**
  On restart, the block re-runs the expensive Opus `analyze` stage to reconstruct task state from git log. No `sdlc/state.json` is persisted between invocations. Three fix options: (1) commit the baseline file in setup to eliminate the restart trigger; (2) persist a `state.json` with task status + worktree paths; (3) leverage `resumeFromRunId` in the Workflow tool. Fix (1) is the highest-priority blocker.
  source: planning/archive/expose-api-and-telegram-bot/harness-update-review.md · date: 2026-06-23 · supersedes: — · freshness: 2026-06-27

- **Test agent invented an emoji-prohibition gate not in harness.json**
  During expose-api-and-telegram-bot, the test agent flagged a spec-required `✅` character as an emoji violation — a check not defined in `harness.json`. The review agent correctly overrode it. Root cause: test agent was not explicitly constrained to enumerate only harness.json checks. Harden the test prompt to enumerate only the defined gating checks.
  source: planning/archive/expose-api-and-telegram-bot/harness-update-review.md · date: 2026-06-23 · supersedes: — · freshness: 2026-06-27

- **Four parallel tasks each appending to app-architecture-overview.md row 232 caused merge conflicts**
  Project C shipped 8 tasks including 4 parallel tasks that each appended a row to the same "What shipped" table in `docs/app-architecture-overview.md`. The SDLC orchestrator escalated (correctly refused to union-merge duplicates); all four conflicts resolved with ~30-second manual merges. Pattern: when multiple tasks write to the same doc location, plan a serial documentation pass or designate one task to own the doc update.
  source: log.md (2026-06-22 phase1-projectC post-merge coverage audit) · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **AgentNode key contract bug: tests seeding raw dicts instead of {"result": ...} pass silently**
  Discovered in Project C post-merge audit: 6 test fixtures in `test_proposal_review_router.py` seeded upstream nodes with raw dicts instead of the `{"result": ...}` wrapper. Tests passed silently (agent was mocked) but proved the wrong key contract. This is now Standing Rule 9 in CLAUDE.md. Common post-merge hardening task: audit test fixtures for this pattern after every workflow ships.
  source: log.md (2026-06-22 phase1-projectC post-merge coverage audit) · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **Ghost-row commit ordering bug fixed in Phase 0 Block C — preserve the flush() guard**
  The original `api/endpoint.py` committed the DB row before `send_task()`; a `send_task` failure left an orphaned row. Fixed with `session.flush()` (not commit) inside the open transaction — the DB gets the `id` but the row is not committed until `send_task` succeeds. Do not simplify this back to commit-first.
  source: CLAUDE.md (Core Hardening table) · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **SQLAlchemy 2.x dropped the model.query interface — always use session.query()**
  `self.model.query.filter_by(...).exists()` raises in SQLAlchemy 2.x. `GenericRepository.exists()` was fixed to use `self.session.query(self.model).filter_by(**kwargs).first() is not None`. This is the preserved guard — do not introduce `Model.query` anywhere.
  source: CLAUDE.md (Core Hardening table) · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **Project A content pipeline shipped first and established the self-critic→revise pattern**
  `SelfCriticNode.approved` field is intentionally inert in the linear blog branch (writer→critic→revise always runs regardless of `approved`). The field is a structural placeholder, not a routing gate. Document this in tests to prevent future readers from treating the unused field as a bug. The PT-BR translation node was a dropped MVP item that was built anyway — `claude-opus-4-8` was used per D35 and flagged as a Project H downgrade candidate.
  source: planning/archive/phase1-projectA/follow-ups.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

- **Voyage free tier forced the switch to local embeddings before Project H eval**
  D35 committed to "top-tier first, then local via Project H." The Voyage rate limit wall (3 RPM / 10K TPM, no payment path) forced the local embedding step forward narrowly for embeddings only — not for chat models. D37 records this as an explicit pull-forward of the Project H local-embedding step. The D35 posture (prefer strong models for reasoning) is unchanged.
  source: planning/decisions/D37-local-embeddings-mxbai.md · date: 2026-06-26 · supersedes: Voyage AI as default embedder · freshness: 2026-06-27

- **Competence checkpoint passed 2026-06-23: Projects A–D complete, 712 tests**
  Phase 1 competence checkpoint: ingest SMB documents, answer questions over them, maintain conversation history — confirmed. Projects A (content pipeline), B (research agent thin cut), C (proposal generator), D (document Q&A + RAG) all shipped. Telegram bot + public API exposure also shipped. Total test count at checkpoint: 712 passing, ruff clean, pylint 10.00/10.
  source: log.md (2026-06-23 post-merge cleanup) · date: 2026-06-23 · supersedes: — · freshness: 2026-06-27

## Preferences

_Project-specific preferences (tooling, style, workflow) the operator has expressed._

- **Run linters as `uv run python -m ruff` / `uv run python -m pylint`, not bare `uv run ruff`**
  Bare `uv run pylint` can resolve to a global uv-tool install missing this repo's dependencies. Always use `python -m <tool>` to ensure the project venv's tool runs.
  source: CLAUDE.md (Build/test/run section) · date: 2026-06-24 · supersedes: — · freshness: 2026-06-27

- **Use trafilatura-first for single article extraction; Firecrawl only as fallback (D24)**
  `ArticleExtractionService` defaults to trafilatura (free, local, fast). Firecrawl is the fallback for JS-heavy/paywalled pages. Firecrawl's `/crawl` endpoint powers `CrawlSiteNode` for multi-page ingestion. Stay on free tier (500 credits/month) until a real crawl demands upgrade. Always add `max_calls` guard when Firecrawl runs inside an agent tool loop.
  source: planning/decisions/D24-firecrawl-role.md · date: 2026-06-22 · supersedes: — · freshness: 2026-06-27

---

*Episodic + portable. For durable "how it works" knowledge see `knowledge.md`.*
