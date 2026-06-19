---
type: Log
title: Development Log
description: Chronological log of work completed for the python-orchestration-system.
---

# log — Orchestration Repo

*Append-only working log. One dated entry per session. Newest entries at the top.*

---

## 2026-06-19

Executed OKF Phase 2 (D27 → D29) in lockstep with adopting base-template's rewritten SDLC engines
(provenance `45504b5`). **Engines replaced** — `.claude/workflows/{sdlc-run,sdlc-task,sdlc-block}.js`
plus `harness.schema.json` and `templates/spec-template.md` — now the agnostic, zero-stack-default
engines carrying per-stage **token telemetry** and the **richer validation check kinds** (base-template
D6). Adopted the OKF-agnostic command set; pruned brain-level commands (`new-project`,
`scaffold-project`, `blog-idea`) and the one-off `review-and-merge-tasks-9-12.js` (kept project
workflows `health-check`, `test-planning`, `generate-new-docs`).

**Validation externalized to `planning/harness.json`** — the old hardcoded 8-check suite (CHECK 0–8.5)
is now expressed faithfully via the new kinds: `forbidden-pattern-scan` (CLAUDE.md standing rules),
`warning-scan` (Pydantic field-shadow warnings on app/worker import), `baseline-diff` (ruff net-new
violations vs a worktree-creation baseline), `count-delta` (pytest count must not regress), plus plain
commands (imports, pylint, full pytest = authoritative). No validation behavior lost.

**OKF renames** — `CONTEXT→context`, `STATUS→status`, `MASTER_PLAN→master-plan`, `DEVLOG→log`,
`planning/README→planning/index`; references updated. **Archived** the 153 finished files under
`planning/tasks/` to `archive/planning-tasks-pre-okf/`; new work uses the concept-folder model
(`planning/<concept>/tasks.md`, state under `<concept>/sdlc/`). D28 (node-level execution state) is
untouched — it lives in app/framework code, not the engines.

Verification: `node --check` passes on all three engines; `harness.json` parses (10 checks). Next:
run one `/sdlc-task` to capture the Phase-A token-telemetry **baseline**, then base-template's Phase B
trims. See base-template `planning/plans/sdlc-telemetry-updates.md` and `planning/decisions/D29`.

---

## 2026-06-17

Completed OKF Phase 1 for this repo — additive, workflow-safe documentation/structure changes only (no workflow JS touched, no load-bearing file renamed). Split the aggregate `planning/DECISIONS.md` into 26 atomic OKF files under `planning/decisions/` (one `D{N}-<kebab>.md` per decision, each `type: Decision`, Decided/Why/Rejected bodies and supersession notes preserved verbatim) plus a `type: Index` registry at `planning/decisions/index.md`; deleted the old aggregate and repointed the prose pointers in `CLAUDE.md`, `planning/context.md`, and `planning/index.md` to the new directory. Added OKF frontmatter to all 14 files under `docs/` (api-reference + configuration as `Reference`, app-architecture-overview as `Architecture`, the architecture_review/ and agentic-workflows/ docs as `Reference`) and created `docs/index.md`. Updated `.claude/commands/log-work.md` so settled choices are written as atomic decision files (next `D{N+1}` from the index, OKF frontmatter, registered in index.md) instead of appended to a single aggregate — ask-first guard kept intact. **Accepted seam (corrected in Phase 2, not an oversight):** the SDLC workflow scripts (`sdlc-run.js`, `sdlc-task.js`) still carry `notes`-field prompt strings that say "DECISIONS.md"; these are descriptive only (the workflows never read or write the file), so they were deliberately left untouched to keep this phase workflow-safe.

```diff
 planning/DECISIONS.md                          | 161 ---------------- (deleted)
 planning/decisions/*.md (26 decisions + index) | 366 ++++++++++++++++ (created)
 docs/*.md (14 files + index.md)                | 116 ++++++++++++++++
 CLAUDE.md / context.md / README.md (pointers)  |  20 +-
 .claude/commands/log-work.md                   |  12 +-
```

Infrastructure and tooling hardening session. Audited phase0-blockC and phase0-blockD execution reports via multi-agent workflow to identify failure patterns and silent passes. Enhanced SDLC orchestrator: `/sdlc-block` now detects already-merged tasks via git log (ALREADY_COMPLETE guard prevents duplicate runs), performs post-merge integrity audits (docs fence-balance check, DEVLOG fix-pass pattern scan), and aggregates NEEDS_REVIEW flags across all tasks. Clarified `docs/api-reference.md` as exclusive (not additive) to prevent corrupted TOC. Improved per-task runner: `/sdlc-task` now captures lint baseline at worktree creation (tracks net-new violations vs. baseline), implements RULE 0 already-complete stage (prevents pipeline re-runs on already-merged tasks), and expanded TEST_SCHEMA with `netNewViolations`, `pytestTestCount`, `pytestTestCountDelta` for better failure triage. Created new `/health-check` workflow: daily/midday live code checks (ruff, pylint, pytest, imports, DEVLOG fence-balance, DEVLOG format, test count trend, branch sync) + silent pattern scans (missing schema registrations, floating migrations, import ordering, test doubles). Auto-discovers active block and produces CRITICAL/WARNING/OK status report. Removed obsolete `planning/tasks/phase1-block1/tasks.md` (216 lines).

```diff
planning/tasks/phase1-block1/tasks.md | 216 ----------------------------------
 1 file changed, 216 deletions(-)
```

---

## 2026-06-10 (phase0-blockD — block completion + manual merge recovery)

Drove phase0-blockD to completion via the `/sdlc-block` orchestrator across three runs. **Run 1** aborted safely on a dependency-cycle guard: the auto-analysis left `app/services/__init__.py` off the additive allow-list, which — combined with task 4's real dependency on task 7 — created a 4↔7 contradiction (logical "4 after 7" vs. numeric conflict-serialization "7 after 4"). Fixed by hand-writing `planning/tasks/phase0-blockD/execution-plan.json`, marking the three append-only files (`app/services/__init__.py`, `app/core/nodes/__init__.py`, `app/workflows/workflow_registry.py`) additive. **Run 2** merged tasks 1, 2, 3, 9 cleanly; tasks 5, 6, 7, 8, 10 each PASSED their pipelines but escalated on additive merge conflicts in `docs/api-reference.md` / `docs/configuration.md` (every parallel pipeline appended a section to the same shared docs, plus each rewrote `app/services/__init__.py` with only its own export). Recovered them manually: a temporary `union` merge driver auto-reconciled the doc sections while I hand-resolved the cumulative `app/services/__init__.py`, then verified (201 tests pass, ruff clean) and removed the worktrees. **Run 3** ran the two remaining tasks — task 4 (TranscriptService, unblocked once ChunkingService landed on main) and task 11 (validation gate) — both PASS and merged clean. Final state: all 11 tasks merged, `uv run pytest` **210 passed**, `ruff check app/` clean, all import smoke-tests green. This supersedes the task-11 note below, which (written from stale context) claimed tasks 5–10 "remain escalated" — they were subsequently merged. **Block D is complete.** Next: Phase 1, Project A — Content pipeline.

```
1ab6038 chore: block orchestration report + status for phase0-blockD
(plus manual merge commits 2a2d082, 4f87709, 9c1073b for tasks 5/6/7 and ort merges for 8/10)
```

---

## 2026-06-10 (task 11 — validate all shared services, nodes, and API contract)

Task 11 ran the full validation suite for phase0-blockD: `uv run pytest` (all new service and node tests passing), `uv run ruff check app/` (zero errors), `uv run pylint app/` (no regression from baseline), and all import checks for `EmbeddingService`, `TranscriptService`, `ArticleExtractionService`, `SearchService`, `ChunkingService`, `ToolUseNode`, and `WorkflowRegistry.CONTENT_PIPELINE`. The `GET /health` endpoint and typed `TaskAcceptedResponse` response model were also verified. Review passed in a single attempt with a PASS verdict — no fixes required. Since task 11 is the final task in the block, the block sequence is complete, though tasks 5, 6, 7, 8, and 10 remain escalated due to docs/api-reference.md merge conflicts and task 4 remains blocked by that upstream escalation. Next: Phase 1, Project A — Content pipeline (scaffold workflow and implement ingestion nodes).

```
d1690b4 docs: update docs for phase0-blockD-task11
66d6d24 feat: implement phase0-blockD-task11
6915139 chore: init worktree phase0-blockd-task11
```

---

## 2026-06-10 (task 4 — TranscriptService)

Implemented `TranscriptService` in `app/services/transcript_service.py`. The service exposes `fetch_transcript(url: str) -> str` which extracts a YouTube video ID from a URL and returns clean joined transcript text, and `fetch_and_chunk(url: str, chunk_size: int, overlap: int) -> list[str]` which delegates to `ChunkingService` after fetching. Descriptive errors are raised on unsupported URL formats or unavailable transcripts — no silent empty-string returns. The service was exported from `app/services/__init__.py`. Tests in `tests/services/test_transcript_service.py` mock `youtube_transcript_api`, assert video ID extraction, assert chunk delegation, and assert that a bad URL raises. Review passed on the first attempt with no findings requiring remediation. Documentation was updated to reflect the new service. Next: Task 5 — ArticleExtractionService.

```
e9c9ae3 docs: update docs for phase0-blockD-task4
b8254c1 feat: implement phase0-blockD-task4
b7902ce chore: init worktree phase0-blockd-task4
```

---

## 2026-06-10 (task 10 — Clean API Contract)

Implemented task 10 of phase0-blockD: cleaned up the FastAPI API contract by replacing the hardcoded `CustomerCareEventSchema` in `app/api/endpoint.py` with a generic `EventPayload` dispatcher that looks up the correct schema from `WorkflowRegistry` and validates `data` against it, raising a `422 Unprocessable Entity` for unknown `workflow_type` values. Added a `GET /health` endpoint in `app/api/health.py` returning `{"status": "ok", "version": "0.1.0"}`. Added OpenAPI metadata (`title`, `description`, `version`) to `app/main.py`. Introduced a typed `TaskAcceptedResponse(task_id: str, message: str)` Pydantic model for the `202 Accepted` response instead of raw `dict`. Updated `tests/api/test_endpoint.py` to cover valid dispatch, unknown `workflow_type` → 422, and health check → 200. Review passed on the first attempt with no issues found. Next: Task 11 — Validate (run the full validation suite: pytest, ruff, pylint, and all import checks).

```
9c94552 docs: update docs for phase0-blockD-task10
e96ec2c feat: implement phase0-blockD-task10
5e873ba chore: init worktree phase0-blockd-task10
```

---

## 2026-06-10 (task 8 — ToolUseNode raw Anthropic SDK implementation)

Implemented `app/core/nodes/tool_use.py` — an abstract `ToolUseNode(Node)` base class that runs a bounded Anthropic tool-use loop. Subclasses define `tools: list[dict]` (Anthropic tool definitions) and implement `handle_tool_call(tool_name, tool_input, task_context) -> str`; the base `process()` method drives the loop, dispatching tool calls and appending `tool_result` blocks until `stop_reason == "end_turn"` or `max_iterations` (default 10) is reached. The model is read from `TOOL_USE_MODEL` env var (default `claude-haiku-4-5-20251001`), keeping the node deployment-agnostic per D18. Tests in `tests/core/test_nodes_tool_use.py` mock `anthropic.Anthropic().messages.create` and assert correct loop termination on `end_turn`, correct guard on `max_iterations`, and correct dispatch to `handle_tool_call`. Review passed on first attempt with no findings. Next: Task 9 — Scaffold Project A (run `createworkflow content_pipeline` and register in `WorkflowRegistry`).

```
21246ba docs: update docs for phase0-blockD-task8
df5f01e feat: implement phase0-blockD-task8
48c9899 chore: init worktree phase0-blockd-task8
```

---

## 2026-06-10 (task 7 — ChunkingService)

Implemented `app/services/chunking_service.py` with the `ChunkingService` class providing two methods: `chunk_text` uses `tiktoken` (`cl100k_base` encoding) to split text into overlapping token-boundary chunks (configurable `chunk_size` and `overlap`, returns empty list for empty input), and `chunk_document` dispatches `text/plain` to direct decode and `application/pdf` to `pymupdf` (`fitz`) text extraction before chunking, raising a descriptive `ValueError` for unsupported mime types. `ChunkingService` was exported from `app/services/__init__.py` with a module docstring and explicit `__all__`. Tests in `tests/services/test_chunking_service.py` cover all six required cases (short text, empty input, token overlap verification, plain-text dispatch, PDF dispatch via patched `fitz.open`, unsupported mime-type error). Review returned PASS on the first attempt with all 14 acceptance criteria met; `uv run pytest` (176 passed), `ruff check app/` (zero errors), and `pylint` (10.00/10) all clean. Next: Task 8 — ToolUseNode (raw Anthropic SDK).

```
1e4bfb1 docs: update docs for phase0-blockD-task7
7e67fb2 feat: implement phase0-blockD-task7
f67620c chore: init worktree phase0-blockd-task7
```

---

## 2026-06-10 (task 6 — SearchService implementation)

Implemented `app/services/search_service.py` with the `SearchService` class, which wraps the Tavily API to provide structured web search results for use in agent tool loops. The service reads `TAVILY_API_KEY` from env, exposes a `search(query: str, max_results: int = 5) -> list[SearchResult]` method, and returns clean Pydantic `SearchResult` models (`title`, `url`, `content`, `score`). The service was exported from `app/services/__init__.py`. Tests were written in `tests/services/test_search_service.py` covering Tavily client mocking, result schema validation, and `max_results` enforcement. All tests passed on the first run and code review resulted in a PASS verdict with no required fixes. Next: Task 7 — ChunkingService.

```
db19499 docs: update docs for phase0-blockD-task6
c3d4595 feat: implement phase0-blockD-task6
d4b2419 chore: init worktree phase0-blockd-task6
```

---

## 2026-06-10 (task 5 — ArticleExtractionService)

Implemented `ArticleExtractionService` in `app/services/article_extraction_service.py`. The service uses a two-path extraction strategy: trafilatura as the default (free, local, fast for clean articles) with Firecrawl as the fallback for JS-rendered pages where trafilatura returns empty or junk content. The `ArticleResult` Pydantic model captures `text`, `title`, and `fetch_status` (`"ok"` / `"fallback_used"` / `"failed"`). On total failure the service returns a `failed` status rather than raising, keeping pipelines alive. The Firecrawl API key is read from the `FIRECRAWL_API_KEY` env var and silently disabled if absent — no hardcoded keys, no deployment conditionals in the service layer. Tests in `tests/services/test_article_extraction_service.py` mock both trafilatura and the Firecrawl client, covering the fallback trigger and graceful-failure paths. All tests passed, ruff and pylint reported no new errors, and the review returned a PASS verdict on the first attempt. Next: Task 6 — SearchService.

```
3f281c2 docs: update docs for phase0-blockD-task5
2e1de69 feat: implement phase0-blockD-task5
096da10 chore: init worktree phase0-blockd-task5
```

---

## 2026-06-10 (task 3 — EmbeddingService)

Implemented `EmbeddingService` in `app/services/embedding_service.py` with `embed_text` and `embed_batch` methods backed by the Voyage AI client. The service is designed as a config-swap seam: provider, model name, and output dimensions are constructor parameters (defaulting to `voyage-2` / 1024), so a local embedding model such as Qwen3-Embedding via Ollama can slot in without code changes — this is the integration point Project H will evaluate. The API key is read from the `VOYAGE_API_KEY` environment variable. Tests in `tests/services/test_embedding_service.py` mock the Voyage client and assert correct dimensionality and batch delegation. The single review attempt awarded a PASS verdict with no blocking findings. Documentation was updated to reflect the new service and its exported interface. Next: Task 4 — TranscriptService.

```
503a158 docs: update docs for phase0-blockD-task3
a9a23c4 feat: implement phase0-blockD-task3
d2571c2 chore: init worktree phase0-blockd-task3
```

---

## 2026-06-10 (task 9 — scaffold Project A content_pipeline workflow)

Scaffolded the `content_pipeline` workflow for Project A by running `uv run createworkflow` and registering `WorkflowRegistry.CONTENT_PIPELINE` in `app/workflows/workflow_registry.py`. The first test+review pass failed due to two ruff lint violations introduced in adjacent files: UP042 (`ModelProvider(str, Enum)` → `ModelProvider(StrEnum)` in `app/core/nodes/agent.py`) and UP046 (`GenericRepository(Generic[T])` → PEP 695 `GenericRepository[T]` in `app/database/repository.py`). Fix pass 2 resolved both; all 170 tests passed, ruff reported zero errors, and pylint scored 10.00/10. The workflow stub (workflow file, nodes package, schema, and registry entry) is in place with no logic — ready for Project A implementation. Docs updated to reflect the new `WorkflowRegistry.CONTENT_PIPELINE` entry and the two type-syntax fixes. Next: Task 10 — Clean API Contract.

```
4c8b809 docs: update docs for phase0-blockD-task9
18a232b fix: fix pass 2 for phase0-blockD-task9
ef0cfff feat: implement phase0-blockD-task9
90c9db1 chore: init worktree phase0-blockd-task9
```

---

## 2026-06-10 (task 2 — pgvector Migration)

Created an Alembic migration to enable the pgvector extension in Postgres. The migration adds `CREATE EXTENSION IF NOT EXISTS vector;` in `upgrade()` and the corresponding `DROP EXTENSION IF EXISTS vector;` in `downgrade()`. No model changes were introduced in this task — vector columns are deferred to Projects A and D when their data models are defined. The initial test run failed due to a pre-existing environment issue but was resolved; the final review awarded a PASS verdict with no blocking findings. Documentation was updated to reflect the migration file and its intended use. Next: Task 3 — EmbeddingService.

```
2561740 docs: update docs for phase0-blockD-task2
52cdcdf feat: implement phase0-blockD-task2
38b4adf chore: init worktree phase0-blockd-task2
```

---

## 2026-06-10 (task 1 — add new runtime dependencies)

Task 1 of phase0-blockD added all required runtime dependencies for the shared services layer using `uv add`: `voyageai` (EmbeddingService), `youtube-transcript-api` (TranscriptService), `trafilatura` (ArticleExtractionService default), `firecrawl-py` (ArticleExtractionService fallback), `tavily-python` (SearchService), `anthropic` (explicit pin), and `pymupdf` (PDF parsing for ChunkingService and Project D). The import verification check `uv run python -c "import voyageai, tavily, trafilatura, anthropic, fitz"` was confirmed passing. The first review attempt failed due to missing import verification details, but the second review returned a PASS verdict after confirming all imports resolved correctly and `pyproject.toml` / `uv.lock` were committed. Next: Task 2 — pgvector Migration.

```
639888c docs: update docs for phase0-blockD-task1
da3bad2 fix: fix pass 2 for phase0-blockD-task1
548e772 feat: implement phase0-blockD-task1
5887ad1 chore: init worktree phase0-blockd-task1
```

---

## 2026-06-10 (Block B private face — Mac Mini Tailscale unattended access)

Set up the Mac Mini's private face and connected it to my MacBook Pro. Installed the Tailscale standalone app, signed in, and put the Mini on my tailnet as `brandons-mac-mini` (`100.104.113.100`) with MagicDNS; then joined the MacBook Pro to the same tailnet and confirmed I can SSH into the Mini from it. The real work was making access survive a reboot or crash with nobody touching the machine. macOS doesn't support true before-login Tailscale — it can't run as a system service yet (tailscale#987) — and more decisively, **FileVault gates all networking at the pre-boot unlock screen**: until the disk is unlocked at the physical machine, the OS hasn't booted and nothing (SSH, Screen Sharing, VNC, Tailscale) can be running. VNC doesn't get around this for the same reason — it's an in-OS tool and the unlock screen sits below the OS. So unattended recovery meant **disabling FileVault, enabling auto-login for brandon, and turning on Tailscale's launch- and connect-on-login**. Verified end to end: rebooted the Mini and reconnected over SSH from the MacBook Pro without touching the box. The Mini's power settings were already correct for a headless machine (no system sleep, auto-restart after power failure, wake-on-network) and Remote Login was already on. Accepted tradeoff: FileVault is off, so the disk isn't encrypted at rest — acceptable because the threat model here is network exposure (handled by Tailscale + zero open ports), not theft of a physically-secured home box; the encryption-preserving alternatives (`fdesetup authrestart` for planned reboots, an IP-KVM for unplanned crashes) were considered and deferred. **Still to connect to the tailnet:** my remaining devices (Pixel tablet and phone; Kindle TBD), the private tooling itself (orchestration API, Celery, personal knowledge feed) once those services are running, and a **Claude Code remote-trigger path** so I can kick off agent runs on the Mini from other devices over Tailscale and/or via webhooks. Infrastructure/ops work on the Mini — no repository code changed this session.

```diff
(no repository changes — infrastructure/ops work on the Mac Mini; git diff --stat empty)
```

---

## 2026-06-10 (Block B public face + SDLC block orchestration)

Two threads landed today. First, the **public face of Block B is done**: `learn-agentic-ai.com` is now live to the public, served from the Mac Mini through a **Cloudflare Tunnel** with Cloudflare DNS in front. The tunnel approach means no inbound ports are opened on the Mini — the site is reachable by anyone with the URL while the box itself stays closed, which is the right shape for a privacy-first harness. This completes the site-revival half of Block B; the remaining work is the **private face** — installing Tailscale on the Mini and all my devices (Pixel tablet, phone, Kindle, laptop) and putting the personal knowledge feed, orchestration API, and Celery behind it with no open ports. Per the two-face architecture (DECISIONS D23), Tailscale alone can't serve the public site, which is exactly why the public side went through Cloudflare. I'll work Block B (Tailscale) and Block D (shared services) in parallel from here. Second, I built `.claude/workflows/sdlc-block.js` — a block-level SDLC orchestration workflow that drives an entire `planning/tasks/<blockId>/tasks.md` to completion by fanning out many parallel `/sdlc-task` pipelines, each in its own git worktree, across dependency-ordered waves. An Opus analysis agent proposes a dependency graph with evidence and an additive-file allow-list; deterministic JS computes the topological waves and conflict serialization; each wave runs with bounded retries plus failure triage (RETRYABLE → clean-slate re-run, MAJOR → escalate and poison only the dependent subtree); merges happen in task-number order with additive-only union fallback; and STATUS/DEVLOG are applied exactly once at the end. The same commit set also ported three-tier model assignment (Opus for planning, Sonnet for review/merge, Haiku for mechanical steps) into `sdlc-run` and `sdlc-task`, and added the `sdlc-orchestration` / `sdlc-dynamic-workflows` docs. This is the agentic harness machinery that actually ran Block C — tooling, not a planning block.

```diff
 .claude/commands/README.md                       |  29 +
 .claude/commands/review-workflow.md              |   2 +-
 .claude/workflows/sdlc-block.js                  | 707 +++++++++++++++++++++++
 .claude/workflows/sdlc-run.js                    |  79 ++-
 .claude/workflows/sdlc-task.js                   |  85 ++-
 docs/agentic-workflows/sdlc-dynamic-workflows.md |  47 ++
 docs/agentic-workflows/sdlc-orchestration.md     | 215 +++++++
 7 files changed, 1145 insertions(+), 19 deletions(-)
```

---

## 2026-06-09 (task 14 — validate)

Ran the full validation pass for Phase 0 Block C: executed `uv run pytest --collect-only` and `uv run pytest -v` to confirm the entire test suite collects and passes with zero failures and zero errors, and verified the four import checks (`from main import app`, `from worker.config import celery_app`, `from database.session import Base, db_session`, `from database.repository import GenericRepository`) all run cleanly without triggering connection attempts. All acceptance criteria from the Block C task spec were confirmed met: the SQLAlchemy 2.x `AttributeError` regression test passes, the ghost-row test correctly shows an empty `Event` table when `send_task` raises, `TaskContext.get_node_output("MissingNode")` raises a `KeyError` with the diagnostic message, `WorkflowValidator` correctly detects cycles and unreachable nodes, `Workflow.run()` handles linear and router-branch pipelines in tests, `ParallelNode` documents the known shared-context gap with a "fixed in Project E" comment, `PromptManager` tests run against a fixture template without touching real prompts, and the full `GenericRepository` CRUD suite passes on in-memory SQLite. The initial test run returned a FAILED verdict on attempt 1, which was resolved before review; the review returned a PASS verdict on the first submission. This closes all 14 tasks in Phase 0 Block C — the orchestration framework now has a trustworthy, fully tested core before any client-facing workflow is built on it. Next: Phase 0, Block D — Shared services + first scaffold (pgvector, Embedding/Transcript/Search/Chunking services; scaffold Project A).

```
a03627c docs: update docs for phase0-blockC-task14
b42044c feat: implement phase0-blockC-task14
f62d6d1 chore: wrap up phase0-blockC-task13
e6c24f8 docs: update docs for phase0-blockC-task13
926dcb1 feat: implement phase0-blockC-task13
```

---

## 2026-06-09 (task 13 — prepare the LinkedIn visibility post)

Drafted the Block C LinkedIn visibility post in `planning/` covering why an untested orchestration core is a production liability and how the four bugs found in Block C — the SQLAlchemy 2.x `AttributeError` in `GenericRepository.exists()`, the ghost-row risk from committing before `send_task`, the import-time side effects in `session.py` and `worker/config.py`, and the silent router `KeyError` — each had concrete failure modes that could hit users. The post follows the public-narrative rule (subject-on-you throughout, no company names) and frames each bug around what could go wrong in production before presenting the fix. The initial test run failed (FAILED verdict on attempt 1), which was resolved before review; the review returned a PASS verdict on the first submission. Pipeline ran: implement → test(#1 FAILED) → review(#1 PASS) → document. No architectural decisions were made; this was a drafting task over Block C's bug narrative. Next: Task 14 — validation (run the full test suite and import checks, confirm all acceptance criteria are met).

```
e6c24f8 docs: update docs for phase0-blockC-task13
926dcb1 feat: implement phase0-blockC-task13
057a705 chore: apply task log for phase0-blockc-task12
36dd40e chore: wrap up phase0-blockC-task12
7c0c943 docs: update docs for phase0-blockC-task12
```

---

## 2026-06-08 (task 12 — write `GenericRepository` CRUD tests)

Expanded `tests/database/test_repository.py` with the full CRUD test suite for `GenericRepository`. A minimal `TestModel` was defined in the test file (avoiding dependency on the `Event` model) and backed by an in-memory SQLite engine via the session-scoped `db_engine` fixture from `conftest.py`. Tests covered `create()`, `get()`, `get_all()`, `update()`, `delete()`, `get_latest()`, `count()`, and the fixed `exists()` method — including the regression test ensuring the SQLAlchemy 2.x `AttributeError` is no longer raised. The initial test run failed due to a fixture scoping issue (the `db_session` fixture conflicted with the module-level `db_session` name imported from `database.session`), which was resolved by renaming the fixture. Review returned a PASS verdict on the first submission after the fix was in place. Next: Task 13 — Prepare the LinkedIn visibility post.

```
56911e1 docs: update docs for phase0-blockC-task12
48845d1 feat: implement phase0-blockC-task12
55f41bb chore: init worktree phase0-blockc-task12
```

---

## 2026-06-08 (task 11 — write `PromptManager` service tests)

Implemented `tests/services/test_prompt_loader.py` with full coverage of the `PromptManager` service using a temporary directory fixture to avoid any dependency on real `app/prompts/` files. Tests cover correct Jinja2 template rendering with variable substitution, YAML frontmatter parsing when the `PromptManager` exposes metadata, a missing template name raising a clear `FileNotFoundError` or `KeyError`, and a template with an undefined variable raising Jinja2's `UndefinedError` rather than silently producing an empty string. The test run initially failed due to a test collection issue that was resolved before the review cycle. The review returned a PASS verdict on the first attempt with no required fixes. Next: Task 12 — Write `GenericRepository` CRUD tests.

```
751671e docs: update docs for phase0-blockC-task11
287fb52 feat: implement phase0-blockC-task11
a77001c chore: init worktree phase0-blockc-task11
```

---

## 2026-06-08 (task 10 — write `ParallelNode` unit tests)

Implemented `tests/core/test_nodes_parallel.py` covering the full `ParallelNode` behavior: all parallel nodes run and write unique keys to `task_context`, concurrent execution is verified, and exception propagation from a failing parallel node is tested. A key finding was the known design gap where parallel nodes write directly to the shared `task_context` and the results list is discarded — the test documents current behavior with an explicit comment noting this is deferred to Project E where parallelism is first genuinely needed. The test(#1) run initially failed due to a threading timing sensitivity in the concurrency assertion, which was resolved before review. The review passed on the first verdict with no required fixes, validating that the test suite accurately captures both working behavior and the documented gap without introducing false failures. Next: Task 11 — Write `PromptManager` service tests.

```
8fd2c31 docs: update docs for phase0-blockC-task10
ebae9a3 feat: implement phase0-blockC-task10
a967ca9 chore: init worktree phase0-blockc-task10
```

---

## 2026-06-08 (task 9 — write `BaseRouter` and `RouterNode` unit tests)

Implemented the full `BaseRouter` and `RouterNode` unit test suite in `tests/core/test_nodes_router.py`. Tests cover `BaseRouter.process()` writing `{"next_node": <name>}` to `task_context.nodes`, first-match-wins behavior when multiple routes could match, fallback node selection when no routes match, the no-fallback/no-match case returning `None`, `RouterNode.determine_next_node()` returning `None` being correctly skipped, and the `KeyError` propagation from `task_context.get_node_output("Missing")` flowing out with a clear diagnostic message rather than being swallowed by `route()`. The initial test run failed due to import path issues, which were resolved before review. The review returned a PASS verdict on the first attempt. Next: Task 10 — Write `ParallelNode` unit tests.

```
359189a docs: update docs for phase0-blockC-task9
cdbfc81 feat: implement phase0-blockC-task9
ad58abc chore: init worktree phase0-blockc-task9
```

---

## 2026-06-08 (session 7)

Completed Task 8 of Phase 0 Block C: wrote `Workflow.run()` unit tests in `tests/core/test_workflow.py`. The tests cover the full set of scenarios from the task spec: a linear three-node pipeline verifying that each stub node's output lands in `task_context.nodes` in the correct order; a router workflow that branches on prior node output and asserts only the correct branch ran; `event_schema` parsing asserting that a raw dict is converted to the Pydantic schema object before `run()` begins; `node_context` logging verified via `caplog` for both node start and finish messages; a node that raises `RuntimeError` asserting the exception propagates out of `run()`; and a check that `task_context.metadata` is cleaned up after a completed run. The initial test run failed on the first attempt (FAILED verdict), which triggered a fix pass; the review verdict was PASS on attempt 1 after the fix. Pipeline ran: implement → test(#1 FAILED) → review(#1 PASS) → document. No new architectural decisions were made; this was a targeted coverage exercise over the existing `Workflow.run()` execution loop. Next: Task 9 — write `BaseRouter` and `RouterNode` unit tests.

```
3685173 docs: update docs for phase0-blockC-task8
ac075d2 feat: implement phase0-blockC-task8
b9e36f2 feat: add /sdlc-task workflow and enhance /clean-worktree for parallel task execution
9aa87ee Reviewed the workflows ran for task 6 and 7
76423d7 feat: add /init-worktree and /clean-worktree slash commands
```

---

## 2026-06-08 (session 6)

Completed Task 7 of Phase 0 Block C: wrote `WorkflowValidator` unit tests in `tests/core/test_validate.py`. The tests cover all the required scenarios from the task spec: a valid linear workflow (A → B → C) passes with no error; cycle detection raises `ValueError` with "cycle" in the message; an unreachable node raises `ValueError` with "unreachable" in the message; a non-router node with multiple connections raises `ValueError`; a router node with multiple connections passes. Direct tests of the private helpers `_has_cycle()` and `_get_reachable_nodes()` were also included to lock down the validator's graph-traversal internals. Stub `Node` subclasses (3–4 lines each) were defined in the test file to satisfy the `Node` ABC without introducing logic. The initial test run failed (FAILED verdict on the first attempt), which triggered a fix pass; the review verdict was PASS on attempt 1 after the fix. Pipeline ran: implement → test(#1 FAILED) → review(#1 PASS) → document. No architectural decisions were made; this was a straightforward coverage exercise over the existing `WorkflowValidator` public API. Next: Task 8 — write `Workflow.run()` unit tests.

```
cdeab7e docs: update docs for phase0-blockC-task7
f49d648 feat: implement phase0-blockC-task7
6ce9869 chore: wrap up phase0-blockC-task6
953632a docs: update docs for phase0-blockC-task6
efe7f37 feat: implement phase0-blockC-task6
```

---

## 2026-06-08 (session 5)

Completed Task 6 of Phase 0 Block C: wrote unit tests for `TaskContext` and `WorkflowSchema`. `tests/core/test_task.py` was expanded with tests covering `TaskContext` creation with `event`, `nodes`, and `metadata` fields; `update_node()` for single-key, multi-key, and merge-into-existing-key scenarios; and `get_node_output()` for both the present-node and missing-node branches (the latter already covered by Task 5). `tests/core/test_schema.py` was created with tests covering `NodeConfig` default values (`connections=[]`, `is_router=False`) and override values, `WorkflowSchema` construction with stub `Node` subclasses asserting `start`, `nodes`, and `event_schema` are stored correctly, and the `is_router=True` flag round-trip. The initial test run failed (FAILED verdict), which triggered a fix pass before the final review — review verdict was PASS on attempt 1 after the fix. The pipeline ran implement → test(#1 FAILED) → review(#1 PASS) → document. No architectural decisions were made during this task; the implementation was a straightforward coverage exercise over existing public API. Next: Task 7 — write `WorkflowValidator` unit tests.

```
953632a docs: update docs for phase0-blockC-task6
efe7f37 feat: implement phase0-blockC-task6
758c5e2 Added a /review-workflow slash command
00b8c0d docs: document TaskContext.get_node_output() in architecture overview
7fae3a9 chore: wrap up phase0-blockC-task5
```

---

## 2026-06-08 (session 4)

Completed Task 5 of Phase 0 Block C: fixed the router key coupling bug by adding `TaskContext.get_node_output(node_name)` as an additive helper in `app/core/task.py`. The original issue was that router nodes accessing `task_context.nodes["SomeNode"]` raised a bare `KeyError` with no context about which router needed the output or what the workflow ordering problem was. The fix raises a descriptive `KeyError` that names the missing node and lists all nodes completed so far, making workflow ordering errors immediately diagnosable. The change is strictly additive — existing `customer_care` router nodes are untouched per CLAUDE.md Rule 3. Also fixed the module docstring position in `task.py` (moved above imports per style rules). 9 tests were written in `tests/core/test_task.py` covering both the missing-node and present-node branches; all 14 tests in the suite pass. The initial test run failed on a ruff violation (pre-existing docstring position issue), which was resolved in the same pipeline run; review verdict was PASS on the first attempt. Pylint false-positive `E1101 no-member` errors from Pydantic `Field` annotations are suppressed with inline comments — a pre-existing pattern in this file. Docs were updated to reflect the new method. Next: Task 6 — write unit tests for `TaskContext` and `WorkflowSchema`.

```
c02fbd4 docs: update docs for phase0-blockC-task5
499ff22 feat: implement phase0-blockC-task5
dc23006 chore(lint): exclude customer_care reference files, auto-fix ruff violations, document style rules
4a92e96 docs(phase0-blockC): update api-reference and add task4 document report
e0229ec docs(phase0-blockC): add task4 test report
```

---

## 2026-06-08 (session 3)

Completed and documented Task 4 of Phase 0 Block C: fixed the ghost-row bug in `app/api/endpoint.py`. The original code called `repository.create()` (which committed the `Event` row immediately) before `celery_app.send_task()` — meaning a Redis failure would leave an orphaned, unprocessable row in the DB. The fix stages the row with `session.add()` + `session.flush()` (assigns `event.id` without committing), enqueues the Celery task, and only commits on success; if `send_task` raises, the `db_session()` generator's existing rollback path cleans up automatically. The endpoint now bypasses `GenericRepository.create()` for this two-phase commit pattern, which is intentional — the generic method doesn't model the enqueue dependency. SDLC pipeline ran cleanly: implement → test → review → document, with reports landing in `planning/tasks/phase0-blockC/reports/`. Also extended `pyproject.toml` to exclude the reference-only `customer_care` workflow files from ruff and pylint checks — these files are frozen and should not generate lint noise. Additionally, reorganized the `/planning/tasks/` directory from a flat layout into per-block subdirectories (e.g. `phase0-blockC/tasks.md` + `phase0-blockC/reports/`) and updated SDLC commands and workflows to match the new file organization. All four bug fixes from Block C's task spec are now done and documented. Next: Tasks 5–12, the comprehensive unit test suite for `TaskContext`, `WorkflowSchema`, `WorkflowValidator`, `Workflow.run()`, `BaseRouter`/`RouterNode`, `ParallelNode`, `PromptManager`, and `GenericRepository` CRUD.

```diff
 docs/api-reference.md                                    |  8 ++++++-
 planning/tasks/phase0-blockC/reports/task4-document.md  | 66 ++++++++++++++++++++++++++++++++++++
 planning/tasks/phase0-blockC/reports/task4-review.md    | 47 ++++++++++++++++++++++++++
 planning/tasks/phase0-blockC/reports/task4-test.md      | 53 +++++++++++++++++++++++++++++
 app/api/endpoint.py                                      | 14 +++-----
 pyproject.toml                                           | 17 +++++++++++++--
```

---

## 2026-06-08 (session 2)

Ran the full SDLC pipeline (implement → test → review → fix → document) on Phase 0, Block C, Task 3: fixed the import-time side effects in `app/database/session.py` and `app/worker/config.py`. `session.py` previously called `create_engine()` at import time (line 15), which caused a live DB connection attempt any time the module was imported in tests or other non-production contexts. Replaced the module-level `engine` and `SessionLocal` with a `_ENGINE = None` sentinel and a lazy `_get_engine()` initialiser, so the engine is only created on first use. `worker/config.py` previously called `Celery("tasks")` followed by `celery_app.config_from_object(get_celery_config())` at import time — the `config_from_object` call silently produced a malformed broker URL if `REDIS_URL` or `PROJECT_NAME` were unset. Replaced with a single `Celery(...)` constructor call passing broker/backend/serializer config as kwargs, which does not attempt a connection. Expanded `tests/conftest.py` with session-scoped `db_engine` and function-scoped `db_session` SQLite fixtures required by the test suite. Initial test run returned FAIL on ruff (73 pre-existing issues across the whole codebase, all unrelated to Task 3) and pylint (exit 30, pre-existing violations in untouched files); the two Task 3 files themselves rated 10.00/10 after a fix pass that renamed `_engine` → `_ENGINE` (C0103), added an inline `# pylint: disable=global-statement` (W0603), and removed trailing whitespace (C0303). Final review verdict: PASS — all 10 acceptance criteria met, 3/3 pytest tests passing, import checks clean. Docs updated in `docs/api-reference.md` (lazy `_get_engine()` documented) and `docs/app-architecture-overview.md` (stale `SessionLocal` reference removed). Also created the `sdlc-run.js` Claude Code workflow (and refined it) to automate the full implement→test→review→document→wrap-up cycle for future tasks.

```diff
 .claude/workflows/sdlc-run.js     | 148 +++++++++++++++++++++++++-------------
 app/database/session.py           |  24 +++++++++++-------------
 app/worker/config.py              |  14 +++++++++++---
 docs/api-reference.md             |   6 +-
 docs/app-architecture-overview.md |   2 +-
 tests/conftest.py                 |  23 +++++-
 6 files changed, 149 insertions(+), 68 deletions(-)
```

---

## 2026-06-08

Ran the full SDLC pipeline (implement → test → review → document) on Phase 0, Block C, Task 2: fixed the `GenericRepository.exists()` SQLAlchemy 2.x compatibility bug in `app/database/repository.py`, replacing the legacy `self.model.query.filter_by(**kwargs).exists()` pattern (which raises `AttributeError` in SQLAlchemy 2.x) with the correct `self.session.query(self.model).filter_by(**kwargs).first() is not None`. Wrote three regression tests in `tests/database/test_repository.py` using a self-contained `_SimpleModel` backed by SQLite (avoiding the PostgreSQL UUID type incompatibility that would block SQLite-based tests). All 3 tests pass. Review verdict: PASS. Docs were patched in `docs/api-reference.md` to reflect the corrected `exists()` signature. Also logged Task 1 as fully reviewed and complete — the pytest deps + test scaffold from the 2026-06-05 session passed review without issues (commit 602da5b). Additionally, the full SDLC slash command set was built out this sprint: new commands for project initialization (`/new-project`, `/scaffold-project`), session orientation (`/recap`, `/status`, `/process-tasks`), block setup (`/start-block`), and the complete pipeline (`/generate-tasks`, `/breakdown`, `/implement`, `/update-task`, `/commit`, `/test`, `/review-task`, `/document`, `/log-work`). The entire SDLC workflow is now documented end-to-end in `docs/sdlc-workflow.md`. Next: Task 3 — fix import-time side effects in `app/database/session.py` and `app/worker/config.py`.

```diff
 app/database/repository.py |  6 +++---
 docs/api-reference.md      | 15 +++++++--------
 2 files changed, 10 insertions(+), 11 deletions(-)
```

## 2026-06-05 (session 2)

Started Phase 0 Block C (test infra + core hardening), completing Task 1: added `pytest`, `pytest-mock`, `httpx`, `freezegun`, and `pytest-env` to `pyproject.toml`'s dev dependency group, ran `uv sync`, and scaffolded the test directory tree (`tests/` with `core/`, `database/`, `api/`, `services/` sub-packages and a stub `conftest.py`) plus a `pytest.ini` at the repo root. Block A tasks 3–9 were intentionally paused — those are personal/manual tasks (LinkedIn, GitHub triage, site work) that can't be delegated to an agent; Block C was pulled forward because it is fully agent-executable and has no dependency on the Block A personal tasks. Also created new slash commands `implement` and `review-task` (and updated related agents) to support structured task execution and review going forward. Next step: run `/review-task planning/tasks/phase0-blockC.md 1` to verify Task 1 before proceeding to Task 2 (fix `GenericRepository.exists()`).

```diff
 pyproject.toml |  5 ++++
 uv.lock        | 87 ++++++++++++++++++++++++++++++++++++++++++++++++++++++++--
 2 files changed, 89 insertions(+), 3 deletions(-)
```

## 2026-06-05

Generated a full suite of architecture review documents in `docs/architecture_review/` — one per core abstraction: `workflow.md`, `task_context.md`, `agent_node.md`, `parallel_node.md`, `router_node.md`, `workflow_schema.md`, `workflow_validator.md`, and `prompt_manager.md`. These are the output of Phase 0 Block A, Task 1 (read `workflow.py` and `task.py`) and the start of Task 2 (read `AgentNode` and support nodes). Task 1 is complete; Task 2 is in progress — the node docs are generated, covering `AgentNode`, `ParallelNode`, `RouterNode`, `WorkflowSchema`, and `WorkflowValidator`, which spans most of Task 2's reading scope. Also did a significant planning session: updated the Master Plan and Agentic Engineering Projects plan with important architectural and strategic detail, all captured as new entries in `planning/DECISIONS.md`. No code changed; all work this session was documentation, planning, and codebase orientation.

```diff
 .claude/commands/generate-tasks.md                 |   90 +
 .claude/commands/log-work.md                       |   38 +-
 .claude/commands/update-specific-task.md           |   57 +
 docs/architecture_review/agent_node.md             |  290 +++
 docs/architecture_review/parallel_node.md          |  148 ++
 docs/architecture_review/prompt_manager.md         |  209 +++
 docs/architecture_review/router_node.md            |  175 ++
 docs/architecture_review/task_context.md           |   23 +-
 docs/architecture_review/workflow.md               |   25 +-
 docs/architecture_review/workflow_schema.md        |  164 ++
 docs/architecture_review/workflow_validator.md     |  219 +++
 uv.lock                                            | 1877 ++++++++++----------
 12 files changed, 2384 insertions(+), 931 deletions(-)
```
