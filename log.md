---
type: Log
title: Development Log
description: Chronological log of work completed for the python-orchestration-system.
---

# log — Orchestration Repo

*Append-only working log. One dated entry per session. Newest entries at the top.*

---

### 2026-06-26 (brain-rag-improvements Blocks E + F + G — pre-rebuild infrastructure complete)

Implemented the full pre-rebuild infrastructure for brain-rag-improvements: Blocks E (indexer rewrite), F (retrieval hardening), G (comprehensive test suite), plus documentation patches. Block E (`scripts/index_brain.py`): rewrote CORPUS list (dropped broken `planning/the-diagnostic` + out-of-repo `memory/`/`MEMORY.md`; added 13 new paths: `docs/diagnostic`, `CLAUDE.md`, `README.md`, `docs/index.md`, `docs/progress.md`, `docs/okf-frontmatter.md`, `docs/infrastructure.md`, `docs/integrations`, `docs/bastion`, `planning/bastion-product`, `planning/bastion-ui`, `planning/status.md`, `planning/archived`); fixed + case-normalized OKF vocabulary sets in `normalize_metadata` (lowercased layer/project/status for membership checks; added missing `infra`/`business`/`content`/`meta` layers, `brain`/`bella`/`amistad` projects, `superseded` status); added `_is_header_only_chunk()` helper that measures the **header-stripped body** (critical blocker: `chunk_by_section` prepends headers to all chunks, so testing on the combined text would flag every chunk uniformly) and populated `is_section_title`/`title`/`description` in the upsert (never `content_tsv`, which is generated). Block F (`retrieve_chunks_node.py` + `document_qa_schema.py`): wired `is_section_title_field` in brain corpus config, added `tsv_field` + `default_status_exclude="archived"`; added explicit `include_archived: bool = False` schema field and threaded it through `process → retrieve → _semantic_search` with NULL-safe archived filter logic; rewrote `_keyword_search` to dispatch graded FTS (dict[id→ts_rank], brain corpus) vs legacy ILIKE (set, content corpus) via `_keyword_search_fts`/`_keyword_search_ilike` helpers; implemented graded keyword fusion in `_fuse_and_rank` with named module-scope constants `_KW_WEIGHT=5.0`/`_KW_BOOST=1.0`, enabling higher `ts_rank` scores to flow through (not flat boost); enriched candidate and result dicts with `file_path`/`doc_id`/`title` provenance fields. Block G: +35 new tests across header-strip + guardrail, vocab case-normalization, CORPUS membership, column population, graded fusion, provenance, archived exclusion, FTS/legacy keyword-search shapes; updated 4 stale tests. `pyproject.toml`: bumped pylint `max-args 6→7` (retrieve now carries 6 positional args) + added `max-positional-arguments=6` with logged rationale. Documentation patches: `docs/api-reference.md` (BrainDocument columns table expanded, Stage 2 rewrite, `_keyword_search`/`_fuse_and_rank`/retrieve/schema sections updated), `docs/brain-rag.md` (FTS + `include_archived` + memory-out-of-corpus note + path fixes), `docs/workflows.md` (FTS + `include_archived` schema field). Validation: `uv run pytest` **790 passed / 8 skipped**; `ruff check app/` clean; `pylint app/` **10.00/10**. Real-world dry-run against live brain repo: **109 files resolve**, **zero vocabulary warnings**, **zero broken paths**, all by-design exclusions absent. Blocks C + D (committed in parallel @ `61d8559`) are integrated. Next: REVIEW Blocks E/F/G/docs against acceptance criteria, then Block H (live `--rebuild`).

```diff
app/schemas/document_qa_schema.py                  |   8 +
.../retrieve_chunks_node.py                        | 138 +++++++++--
docs/api-reference.md                              |  76 ++++--
docs/brain-rag.md                                  |  24 +-
docs/workflows.md                                  |   3 +-
pyproject.toml                                     |   8 +-
scripts/index_brain.py                             |  94 +++++++-
tests/test_index_brain.py                          | 266 ++++++++++++++++++++-
tests/workflows/test_retrieve_chunks_node.py       | 219 ++++++++++++++++-
10 files changed, 850 insertions(+), 151 deletions(-)
```

---

### 2026-06-26 (brain-rag-improvements Blocks C + D — FTS + ANN infrastructure)

Shipped the full brain-rag-improvements specification for Blocks C (FTS infrastructure) and D (model update) in a single implementation pass: migration `e2f3a4b5c6d7` adds three metadata columns (`is_section_title`, `title`, `description`) for weighted document ranking + a generated `content_tsv` tsvector column (GIN-indexed) for graded Postgres full-text search + an HNSW index on `embedding` for approximate nearest-neighbor search. The generated column formula weights title/keywords ('A') > description ('B') > content ('C') to amplify term frequency based on section granularity. Implementation note: used `array_to_tsvector()` (IMMUTABLE) instead of `array_to_string()` (STABLE) because Postgres rejects STABLE functions in generated columns; the trade-off is keywords match as exact tokens without stemming, which is correct for controlled OKF vocabulary (e.g., 'brain', 'engine', 'factory'). `BrainDocument` model updated to declare all four new columns (three regular, `content_tsv` as read-only FetchedValue). This infrastructure is the prerequisite for Block B (indexing the brain corpus) and Block E (retrieval ranking refinement). Final: 760 tests pass + 8 skipped; ruff clean; pylint 10.00/10.

```diff
app/alembic/versions/e2f3a4b5c6d7_brain_documents_fts_ann_and_metadata_columns.py | 86 ++++++++++++++++++++++
app/database/brain_document.py                                                      | 35 +++++++++
2 files changed, 121 insertions(+)
```

---

### 2026-06-25 (close-out doc sweep for frontmatter specs)

Patched developer reference docs after `frontmatter-indexer-enrich` and `frontmatter-retrieval-filters` shipped. Updated `docs/brain-rag.md` to clarify brain keyword OR-in (the `keywords` OKF column is ORed into Stage 2 keyword re-ranking) and added a new "Scoping retrieval with filters" subsection documenting the optional `filters` parameter with working curl example. Updated `docs/workflows.md` to add the `filters` field to the DOCUMENT_QA payload table with supported filter keys (`layer`, `project`, `status`). Updated `docs/app-architecture-overview.md` (line 163: expanded `BrainDocument` entry to detail the 6 new OKF columns + migration; line 249: test count bump 22→32 for `RetrieveChunksNode`, added brain keyword OR-in feature note and metadata filters feature summary; line 250: added `filters` field to `DocumentQAEventSchema` field list). No code changes — documentation-only close-out sweep to align developer reference with implemented features.

```diff
docs/app-architecture-overview.md | 7 ++++---
docs/brain-rag.md                 | 21 ++++++++++++++++++++-
docs/workflows.md                 |  1 +
3 files changed, 25 insertions(+), 4 deletions(-)
```

---

### 2026-06-25 (frontmatter-retrieval-filters — Block C keyword-boost + metadata filters)

Shipped the full `frontmatter-retrieval-filters` spec (2 tasks) in one pipeline pass: PASS on first review attempt. Extended `_CORPUS_CONFIG["brain"]` in `retrieve_chunks_node.py` with `"keyword_extra_fields": ["keywords"]` and `"filter_fields": {"layer": "array", "project": "scalar", "status": "scalar"}` — the `"content"` corpus entry is untouched. Added module-level `_apply_metadata_filters(query, model, filters, filter_fields)` helper that translates `{field: value}` pairs to WHERE clauses (scalar `==`, ARRAY `.overlap([value])`). Updated `_keyword_search` to OR-in `func.array_to_string(extra_col, " ").ilike(...)` per extra field per term; updated `_semantic_search` to accept and apply optional `filters: dict | None = None`; threaded `filters` from `process()` (via `getattr(event, "filters", None)`) through `retrieve()`. Added `filters: dict | None = Field(default=None)` to `DocumentQAEventSchema` so the filter surface is reachable end-to-end through the API. The `filters` parameter on `retrieve()` is keyword-only (via `*`) to satisfy pylint R0917; `max-args = 6` raised in `pyproject.toml`. Added 9 new tests across `TestProcess`, `TestKeywordExtraFields`, and `TestSemanticSearchFilters`; final count 755 passed + 8 skipped. Ruff clean, pylint 10.00/10. Docs patched: `docs/api-reference.md` (filters field, process()/retrieve()/_semantic_search()/_keyword_search()/_apply_metadata_filters descriptions, test count 23→32); `docs/app-architecture-overview.md` flagged NEEDS_REVIEW for the dense architecture timeline rows. Review: all 7 acceptance criteria MET, fresh gating checks all pass. Next: run `index_brain.py` against the actual brain corpus to populate the vector store (Block B population step), then Block O (corpus widening).

```
7d4996a docs: update docs for frontmatter-retrieval-filters
e8678a1 feat: implement frontmatter-retrieval-filters
d6314b0 chore: add spec for frontmatter-retrieval-filters (frontmatter Block C)
```

---

### 2026-06-25 (frontmatter-indexer-enrich — Block B frontmatter parse/strip/enrich)

Shipped the full `frontmatter-indexer-enrich` spec (3 tasks) in one pipeline pass: PASS on first review attempt. Added six nullable OKF frontmatter columns (`doc_id`, `layer`, `project`, `status`, `keywords`, `related`) to `BrainDocument` with GIN indexes on the ARRAY columns and btree indexes on `doc_id`/`project`/`status`, plus a new Alembic migration (`d1e2f3a4b5c6`) chaining to the confirmed `c4d5e6f7a8b9` head. `index_brain.py` gained three module-level functions: `parse_document` (strips YAML frontmatter using `python-frontmatter`), `normalize_metadata` (coerces bare-string `layer` to list, derives `doc_id` from filename stem when absent, warns on out-of-vocabulary values without raising), and `build_context_prefix` (builds a semantic prefix from `type`/`title`/`description`/`layer`/`project`/`keywords`, excluding `status`/`doc_id`/`related`). The indexer loop now chunks the clean body only (no YAML in stored `content`) while passing `prefix + chunk` to `embed_batch`. Docs patched: `docs/brain-rag.md` (column table updated) and `docs/scripts.md` (frontmatter handling subsection added). Test suite grew by 32 new tests across `TestParseDocument`, `TestNormalizeMetadata`, `TestBuildContextPrefix`, and `TestFrontmatterIntegration`; final count 746 passed + 8 skipped (753 collected). Ruff clean, pylint 10.00/10. Next: run `index_brain.py` against the actual brain corpus to populate the vector store with enriched frontmatter (Block B population step), then Block O (corpus widening).

```
2536799 docs: update docs for frontmatter-indexer-enrich
d417a07 feat: implement frontmatter-indexer-enrich
cbef759 chore: add spec for frontmatter-indexer-enrich (frontmatter Block B)
```

---

### 2026-06-25 (Bastion program alignment — D36)

Aligned the orchestrator planning + dev docs to the Bastion program (recorded as decision **D36**). The repo's `planning/master-plan.md` predated the brain's D24/D25/D26 reshape — it described an isolated "project library A–H" with no awareness that this repo is now Bastion's **Engine** + the **Python half of the Brain**, and its status table was stale (Projects A–D shown not-started though all shipped). Brandon chose the crosswalk approach: keep the A–H numbering, add a "Role in Bastion" section + a program-block crosswalk table, and append new blocks in `/generate-master-plan` block-contract format — no renumber. Added Blocks B (Brain semantic layer / `index_brain.py`), O (corpus widening), J (knowledge-graph structural retrieval), C (core hardening wave 2), P (Brain memory/entity), I (self-improving eval), L (Telegram conversation persistence), R (Brain-as-MCP-server), S (Brain memory / entity capability — formerly Project G) each with full block-contract specs. Reconciled the Phase Sequence table to reality (A–D Done, checkpoint Passed, brain-rag Layer 1 + expose-api-and-telegram-bot added). Updated `planning/status.md` (current focus flipped to demand-first Wave 0 = Block B + O; new Bastion Program table; Project E repositioned to Wave 4; deviation-log entry added). Updated `planning/context.md` (Role-in-Bastion note, project sequence, standing-rule + tech-stack + reuse-map reframes), `planning/index.md` (dead file refs fixed, Console framing, brain program pointer), and `CLAUDE.md` (Before-you-start Role-in-Bastion pointer; standing rule 5 reframed to cite D36). Updated `docs/brain-rag.md` (Layer 3 "Project F"→"Block R: Brain-as-MCP-server"; indexer roadmap note) and `docs/app-architecture-overview.md` (one-line Bastion role orientation). Created `planning/decisions/D36-bastion-engine-brain-role.md` + updated `planning/decisions/index.md`. Brain's `docs/projects/python-orchestration.md` synced in a prior commit.

```diff
 CLAUDE.md                         |   7 +-
 docs/app-architecture-overview.md |   2 +
 docs/brain-rag.md                 |   6 +-
 planning/context.md               |  35 ++--
 planning/decisions/index.md       |   2 +
 planning/index.md                 |  13 +-
 planning/master-plan.md           | 374 ++++++++++++++++++++++++++++++++++++--
 planning/status.md                |  33 +++-
 8 files changed, 424 insertions(+), 48 deletions(-)
```

### 2026-06-24 (harness pull from base-template — b8ebbf7)

Pulled the current `base-template` harness (commit `b8ebbf71c20445de65195037aa24bfe00bbf080b`) into
`.claude/`. Added the **`/sdlc-flow`** engine (D30–D33; shared-worktree sequential flow, one end
review, PR wrap-up) and **`/generate-master-plan`** plus the **block-definition planning seam** (D34):
`/generate-tasks --from <path>`, `/plan` as a standalone block definition, and the hardened block
skeleton. Also the **plan-quality floor** (D35) — planning commands clarify-or-abort rather than
fabricate. `harness.schema.json` refreshed. Project-specific `health-check.js` engine **preserved**.
All five engines `node --check` clean; shared command/engine files byte-identical to base.
`planning/harness.json` untouched. Added `planning/.template-version` (provenance was previously
unstamped).

### 2026-06-23 (post-merge cleanup — docs and Telegram deployment guide)

Merged expose-api-telegram-bot branch to main (commit 207ccdf, 53 files across 5 commits) consolidating the public API exposure + Telegram bot workstream. Ran `/update-docs --patch` to refresh documentation baselines and capture the full scope of the work: README test count increased 549→712 (163 new tests from the full spec: 5 API security tests, 92 Telegram integration tests, 24 cross-test import/schema-registry checks, 42 E2E and misc), integrations/ directory added to directory map in docs/index.md, two new rows added to app-architecture-overview.md ("What shipped" table) covering api/security.py (auth and CORS infrastructure) and integrations/telegram/ (long-poll bot, config, client layer). Expanded integrations/telegram/README.md with a comprehensive Mac Mini deployment guide covering three sections: (1) long-poll topology primer explaining the phone→Telegram→bot→localhost architecture, no-inbound-port design, when to switch to webhook; (2) Docker Compose deployment instructions with `telegram_bot` service config, restart:unless-stopped policy, and env var reference; (3) launchd plist template for running the bot outside Docker on macOS (auto-launch on login, log redirection, clean shutdown); (4) first-time BotFather setup steps and chat-ID allowlist configuration; (5) three network topology scenarios (Cloudflare Tunnel for public API access, Tailscale private ingress with the 127.0.0.1→0.0.0.0 binding note, same-machine default localhost:8080 for development). Handoff written for projectE. Validation: 712 tests pass, ruff clean, pylint 10.00/10.

```diff
planning/handoff.md | 39 ++++++++++++++++++++-------------------
 1 changed, 20 insertions(+), 19 deletions(-)
```

---

### 2026-06-23 (D23/D24 harness validation — expose-api-and-telegram-bot)

Post-run analysis of the lean sdlc-block against D23/D24 behavioral expectations. The expose-api-and-telegram-bot spec shipped PASS via `/sdlc-block` across two invocations (first PARTIAL, second PASS after manual recovery), totaling 1,875,465 subagent tokens and ~89 minutes. All 5 tasks landed; 705 tests pass. Root cause analysis: baseline-snapshot writes `planning/expose-api-and-telegram-bot/sdlc/reports/net-new-lint-baseline.json` to the working tree but does not commit it, which blocked worktree merges when tasks 2 and 3 attempted to integrate — the untracked file triggered the merge safety check. Manual recovery committed the file; re-run completed. The restart cost ~531k tokens (almost entirely wasted). Full harness review written to `planning/expose-api-and-telegram-bot/harness-update-review.md` identified three bugs: **P0 (baseline-snapshot):** file write with no commit — fix by committing atomically in setup, low effort; **P1 (test-agent emoji false gate):** test agent invented an emoji-prohibition check not in `harness.json`, failing on spec-required `✅` character in reply — review correctly overrode it, but fix is to harden test prompt to enumerate only harness.json checks; **P2 (cross-invocation resume):** no state persistence across invocations, forcing redundant setup/config/analyze on restart — medium-effort state file solution. D23/D24 behavioral validations that DID pass: shared setup (harness-config + baseline-snapshot) ran once per invocation (twice total due to restart, but once within each), width-1 tasks (4, 5) ran in-place with no worktree setup, width-≥2 waves (1, 2, 3) ran in parallel worktrees, one consolidated back-half (test → review → fix → document → wrap-up), per-task review off by default.

```diff
 planning/expose-api-and-telegram-bot/sdlc/reports/block-workflow.md | 54 ++++++++++++----------
 1 file changed, 29 insertions(+), 25 deletions(-)
```

---

### 2026-06-23 (expose-api-and-telegram-bot — full spec shipped, PASS)

Completed the expose-api-and-telegram-bot workstream via a full SDLC pipeline run (implement → test → review → document). Implemented all four spec tasks across parallel worktrees (wave 1: tasks 1/2/3; wave 2: task 4 docs; wave 3: task 5 validate): `app/api/security.py` gates `POST /events/` with `require_api_key` (fail-closed 503 when unset, 401 on mismatch, `hmac.compare_digest` for timing-attack safety); `CORSMiddleware` with env-driven `ALLOWED_ORIGINS` mounted in `app/main.py`; full `integrations/telegram/` package (config, client, bot — long-poll, fire-and-forget `/digest <url>` command, chat-id allowlist enforcement, "Queued ✅" reply); `python-telegram-bot` as optional extra with `importorskip`-gated handler tests; `telegram_bot` Docker Compose service with `Dockerfile.telegram`; env vars documented in both `.env.example` files and `docs/configuration.md`; `docs/data-contract.md` patched to v1.0.1 (clarification only — no shape change, bastion needs no re-pin). Test(#1) flagged emoji-prohibition on the spec-required "Queued ✅" reply string, which is not a harness.json gate and was correctly overridden by review(#1); review PASS confirmed all 8 acceptance criteria met and all 7 gating checks pass (pylint 10.00/10, 705 tests passed, 8 skipped, ruff clean). UI-test skipped (uiTest disabled). Document pass confirmed all three affected docs current; `docs/app-architecture-overview.md` flagged NEEDS_REVIEW for `api/security.py` and `integrations/telegram/` coverage (non-blocking). Cross-repo manual steps still required: `cloudflared` ingress rule, DNS record, Cloudflare Access app + service token, `@BotFather` token — tracked in brain repo `docs/infrastructure.md`. Next: phase1-projectE — Specialization refactor.

```
a0785b6 docs: update docs for expose-api-and-telegram-bot
15995e8 chore: consolidated implement report for expose-api-and-telegram-bot
82e17cd feat: implement expose-api-and-telegram-bot-task5
a5ced4d feat: implement expose-api-and-telegram-bot-task4
cbe76c4 Merge branch 'expose-api-and-telegram-bot-task3' into expose-api-telegram-bot
```

---

## 2026-06-23

Documentation sweep for human readability. Wrote four new docs: `docs/getting-started.md` (local dev via Homebrew scripts + OrbStack/Docker path, first event, API key explainer), `docs/workflows.md` (all 5 workflows with DAG diagrams, payload fields, and curl examples), `docs/scripts.md` (all 4 developer scripts), and `docs/brain-rag.md` (BrainDocument model, index_brain.py, querying via DOCUMENT_QA). Patched `README.md` (fixed broken curl — was hitting `/` instead of `/events/`, added X-API-Key, expanded docs table from 2 to 10 entries). Fixed `docs/index.md` (removed 3 dead links to deleted agentic-workflows docs, added new docs and Integrations section). Updated `requests/send_event.py` to read API key from app/.env automatically. Added `requests/send_workflow.py` — an interactive CLI for triggering any of the 5 workflows by name without hand-crafting JSON. Added shared-secret explanation paragraph to getting-started.md. Archived 340 old planning/task report files (pre-OKF era) to `archive/` for a clean planning/ tree. All merged; phase1-projectE is the standing focus.

```diff
README.md                                          |   26 +-
docs/index.md                                      |   15 +-
requests/send_event.py                             |   89 +-
340 files changed, 87 insertions(+), 26330 deletions(-)
```

---

### 2026-06-23 (public API exposure + Telegram bot plan)

Planning-only session: wrote the implementation plan for exposing the orchestration API publicly at `api.learn-agentic-ai.com` (via the existing Cloudflare Tunnel, gated by Cloudflare Access + an in-app X-API-Key) and adding a long-poll, fire-and-forget Telegram bot in `integrations/telegram/` as the first client. The bot design: send link in Telegram → bot hits `POST /telegram/submit` → fires `CONTENT_PIPELINE` workflow → acks 'Queued' in chat. Defense-in-depth auth: Cloudflare Access at the perimeter (zero-trust on all origins) + in-app `X-API-Key` header validation per request (lightweight, cacheable, revokable without redeploying infrastructure). Architecture settled: no data-contract bump (existing TaskContext + Events table suffice), long-poll now (fire-and-forget webhook support deferred to Phase 2), no new shared service (bot is a thin integrations module). Plan saved to `planning/plans/expose-api-and-telegram-bot.md` with design decisions, scope, and edge cases documented. No code written; next step is a fresh agent running `/generate-tasks` against the plan to produce a task spec and kick off implementation. This is a **separate workstream** from phase1-projectE (which remains the standing focus); both proceed in parallel once tasks are generated.

*Plus untracked: planning/plans/expose-api-and-telegram-bot.md (14 KB) and planning/handoff.md (new session handoff file).*

---

### 2026-06-23 (phase1-projectD post-merge hardening)

Post-merge quality audit of phase1-projectD uncovered 4 test coverage gaps, the most critical a live functional bug in `RetrieveChunksNode._keyword_search()` where punctuation like "?" was not stripped from query terms before ILIKE matching, causing keyword boost to silently never fire for question-form queries. Fixed with `re.sub(r"\W+", "", t)` to strip all non-word characters from each term. Also added: (1) Pydantic output path test for `UpdateSessionMemoryNode` (when node constructs a new `ChatSession` and returns via `model_dump()`), (2) `TestAnswerNodeTelemetry` (3 tests covering success + error telemetry recording), (3) two end-to-end smoke test files (`test_document_ingest_e2e.py` with 14 tests for parse→chunk→embed→store pipeline, `test_document_qa_e2e.py` with 18 tests for embed→retrieve→assemble→answer pipeline) covering cross-node key contracts in isolation. Surgical update-docs pass on `api-reference.md`: updated `_keyword_search` description to document the punctuation fix, updated `RetrieveChunksNode` test count from 22→23, added "Test coverage" sections to both workflow docs. Validation: ruff clean, pylint 10.00/10, 689 tests pass (7 skipped). Final test count +15 over task 7 (674→689). Competence checkpoint: ingest an SMB's documents, answer questions over them, maintain conversation history — confirmed ready for phase1-projectE (Specialization refactor).

```
 .../digest_renderer.py                             |  49 +++++++-
 .../retrieve_chunks_node.py                        |   4 +-
 docs/api-reference.md                              |  18 ++-
 planning/handoff.md                                | 135 +++++++++++----------
 tests/workflows/test_document_qa_nodes.py          | 112 +++++++++++++++++
 tests/workflows/test_retrieve_chunks_node.py       |  45 +++++++
 6 files changed, 289 insertions(+), 74 deletions(-)
```

*Plus 2 untracked e2e test files: test_document_ingest_e2e.py (14 tests, 6 KB) + test_document_qa_e2e.py (18 tests, 8 KB).*

---

### 2026-06-22 (task 7 — validate phase1-projectD)

Task 7 was a validation-only gate: all implementation work (tasks 1–6) was already complete. Enabled the tests directory in sparse checkout, ran all eight validation commands, and confirmed clean results: 674 tests collected (667 passed, 7 skipped, 0 failed), pylint 10.00/10, ruff clean, all gating checks pass. Both workflows (DOCUMENT_INGEST and DOCUMENT_QA) are registered in both workflow_registry.py and schema_registry.py, and TestSchemaRegistryCompleteness passes. The two-stage hybrid retrieval, section-title weighting, NaN-safe sorting, corpus switching, RAG + session-memory assembly, and prompt-via-PromptManager requirements were all verified in source and test coverage. The test count of 674 exceeds the 549 baseline by 125. Competence checkpoint: ingest an SMB's documents, answer questions over them, maintain conversation history — confirmed. Next: phase1-projectE — Specialization refactor.

```
285a823 docs: update docs for phase1-projectD-task7
3d4538e feat: validate phase1-projectD-task7
457137c chore: init worktree phase1-projectd-task7
```

---

### 2026-06-22 (task 6 — documentation)

Updated `docs/app-architecture-overview.md` with "What shipped" rows for Project D Tasks 3 (RetrieveChunksNode) and 4 (DocumentQAWorkflow); confirmed `docs/api-reference.md` already contains all 13 new TOC entries (39–51) and complete `##` sections added by prior document agents. All 7 harness gating checks pass (standing-rules, imports, ruff, pylint, pytest-count, pytest). Test count is 674 (well above 549 baseline); 667 passed, 7 skipped. Review verdict: PASS. The test agent flagged pre-existing emojis in app-architecture-overview.md, but emoji-gate is not a harness-defined gating check, so it does not block completion. Next: Task 7 — Validate (run the Validation Commands from the spec and confirm all pass with test count ≥ 549).

```
828863e docs: update docs for phase1-projectD-task6
9e7ddbe docs: update app-architecture-overview for phase1-projectD-task6
cf78bc1 chore: init worktree phase1-projectd-task6
```

---

### 2026-06-22 (task 5 — Register both workflows + integration)

Registered `DOCUMENT_INGEST` and `DOCUMENT_QA` workflows in both `app/workflows/workflow_registry.py` (enum members) and `app/api/schema_registry.py` (schema map entries), completing CLAUDE.md rule 6. All import smoke checks passed cleanly, `TestSchemaRegistryCompleteness` enforced the dual-registry requirement automatically, pylint scored 10.00/10, ruff was clean, and the full test suite reported 674 collected with no regressions. Documentation updated to reflect the new registry entries. Verdict: PASS. Next: Task 6 — Documentation.

```
92e449e docs: update docs for phase1-projectD-task5
937ebeb feat(registry): register DocumentIngest and DocumentQA workflows
98fcd59 chore: init worktree phase1-projectd-task5
```

---

### 2026-06-22 (task 4 — Document Q&A query workflow)

Implemented the full 5-node Document Q&A workflow (Embed → Retrieve → AssembleContext → Answer → UpdateSessionMemory) with comprehensive test coverage. EmbedQuestionNode embeds the query; AssembleContextNode combines retrieved chunks (with section titles and relevance scores) with prior ChatSession turns into a unified context; AnswerNode answers grounded in that context using the `document_qa_answer.j2` system prompt via PromptManager; UpdateSessionMemoryNode persists new conversation turns to the session. All 5 acceptance criteria for the Task 4 scope were MET on first review: DocumentQAEventSchema validates properly, the linear 5-node DAG wires correctly per WorkflowValidator, both RAG context and session memory appear in the assembled prompt, new turns persist, and all code-style / CLAUDE.md rules are met. Test suite grew from 610 to 674 tests (64 new); all gating checks pass. Next: Task 5 — Register both workflows + integration.

```
9a77738 docs: update docs for phase1-projectD-task4
58a920a feat(rag): implement Document Q&A workflow (Task 4)
8ca08d2 chore: init worktree phase1-projectd-task4
```

---

### 2026-06-22 (task 3 — RetrieveChunksNode with two-stage hybrid retrieval)

Task 3 ships `RetrieveChunksNode`, a carefully-built retrieval component reused verbatim in downstream projects (F, and beyond). Implements the proven two-stage hybrid pattern from the Rust RAG engine: semantic pgvector cosine-distance (Stage 1, top-20 candidates) filtered to valid embeddings, ILIKE keyword re-rank scoped only to those candidate IDs (Stage 2), and additive score fusion with section-title 2× weight. Supports corpus dispatch (`"content"` → `content_chunks`, `"brain"` → `brain_documents`) for multi-source retrieval. NaN-safe sorting prevents crashes on invalid distances. 22 tests cover ordering, keyword fusion weighting, section-title boost, threshold/k enforcement, corpus switching, and TaskContext contract (seeded with real `{"result": ...}` structure per CLAUDE.md rule 9). All gating checks pass: ruff clean, pylint 10.00/10, 603 tests passed (7 skipped), test count up to 610 (from baseline 549). Review verdict: PASS. Next: Task 4 — Document Q&A query workflow.

```
8278c5a docs: update docs for phase1-projectD-task3
e46619c feat(rag): add RetrieveChunksNode with two-stage hybrid retrieval
06e4e30 chore: init worktree phase1-projectd-task3
```

---

### 2026-06-22 (task 2 — Document ingestion workflow: Parse → Chunk → Embed → Store)

Task 2 shipped the complete document ingestion workflow: `ParseDocumentNode` normalizes event content (plain text or base64-decoded text/PDF via `fitz`); `ChunkDocumentNode` splits text into 500-token chunks with 50-token overlap and detects markdown headers (`#`/`##`/`###`), emitting standalone `is_section_title=True` chunks for each heading and tagging body chunks with their parent `section_title` for later weighting; `EmbedChunksNode` batches all chunks into a single Voyage `embed_batch` call and zips vectors back onto chunk objects; `StoreChunksNode` persists `ContentChunk` ORM objects via `GenericRepository` with embeddings written at storage time. The workflow is wired linearly (Parse → Chunk → Embed → Store, no router). Tests include 22 node-level and 12 workflow-level tests covering chunking boundaries, section tagging, position ordering, batched embedding, and ORM persistence. Review verdict PASS: all task 2 acceptance criteria met, all 10 gating checks passed (618 tests collected, +30 over task 1; 611 passed, 7 skipped; ruff and pylint clean; no violations introduced). Documentation patched: 6 new sections in `api-reference.md` (schema, 4 nodes, workflow) + 1 row in architecture overview; no NEEDS_REVIEW flags. Next: Task 3 — RetrieveChunksNode (two-stage hybrid retrieval).

```
bd740c7 docs: update docs for phase1-projectD-task2
9ba1468 feat(ingest): implement document ingestion workflow (Task 2)
bb644c3 chore: init worktree phase1-projectd-task2
```

---

### 2026-06-22 (task 1 — ContentChunk + ChatSession data models)

Shipped foundational data models for the document Q&A workflow: `ContentChunk` SQLAlchemy model with pgvector `Vector(1024)` embedding column, indexed `doc_id`, section awareness (`section_title`, `is_section_title`), and `ChatSession` model with JSON `turns` and `topics_covered` for multi-turn conversation memory. Alembic migration `c4d5e6f7a8b9` creates both tables with correct down_revision (`020c9f7f89e2`). All 18 ContentChunk + 14 ChatSession model tests pass (schema shape + round-trip); collection count 588 tests (well above 549 baseline). Review: PASS — all 27 in-scope acceptance criteria MET. Ruff, pylint (10.00/10), and full pytest suite clean. One minor deviation noted for future work: D31 directs that Vector-column tests be marked `skip` under SQLite; the tests pass in practice but lack the marker. Next: Task 2 — Document ingestion workflow.

```
091d651 docs: update docs for phase1-projectD-task1
6aa0788 feat(database): add ContentChunk and ChatSession models + migration
e570a17 chore: init worktree phase1-projectd-task1
```

---

## 2026-06-22 (phase1-projectC post-merge coverage audit + CLAUDE.md rule 9)

Phase 1 Project C shipped all 8 tasks successfully; the post-merge cleanup resolved a common orchestration challenge. Four parallel tasks (3–6) each modified the shared `docs/app-architecture-overview.md` file, each appending a row to the "What shipped" table at row 232. The SDLC orchestrator correctly refused to union-merge duplicate rows and escalated; all four conflicts were hand-resolved with ~30-second manual merges (keep both rows). Coverage audit of the complete proposal_generator workflow found 6 test fixtures in `test_proposal_review_router.py` that seeded upstream nodes with raw dicts instead of the `{"result": ...}` wrapper that actual `AgentNode.update_node()` produces—tests passed silently against mocked agents but proved the wrong key contract. All 6 were fixed, surfacing the pattern as a common post-merge hardening task. Added CLAUDE.md Standing Rule 9 to document the pattern: `AgentNode` stores output via `update_node(node_name=..., result=output)`, which produces `{"result": output}` in `task_context.nodes`; tests that seed an upstream node must mirror this structure. Final: all 8 tasks merged, 549 tests pass, ruff clean, pylint 10.00/10.

```diff
 CLAUDE.md                                      |  1 +
 tests/workflows/test_proposal_review_router.py | 14 ++++++++------
 2 files changed, 9 insertions(+), 6 deletions(-)
```

---

## 2026-06-22 (task 8 — validation pass for proposal_generator workflow)

Task 8 is a pure validation task—no new source files were created or modified. All acceptance criteria for the complete proposal_generator workflow (tasks 1–7) were verified passing: the workflow runs end-to-end through both pass and revise routes, producing a valid `AutomationRoadmap` with candidates sorted by composite score descending and `top_profiles` capped at 3. The composite scoring formula `(frequency × 0.35) + (time_cost × 0.40) + (buildability × 0.25)` was confirmed embedded in the opportunity identifier prompt template (`app/prompts/proposal_opportunity_identifier.j2`), not hardcoded in Python. Dual-language support (PT and EN) was exercised in both the writer and review nodes. Registry entries confirmed present in both `workflow_registry.py` and `app/api/schema_registry.py`. The `CompanyResearchNode` reused from Project B without modifications to Project B's source. A sparse checkout issue in the worktree (tests/ directory excluded) was fixed, enabling the full test suite to run: all 549 tests pass, 7 skipped, pylint rated 10.00/10, ruff found zero violations. All 7 gating checks passed (standing-rules, db-session-import, db-repository-import, net-new-lint, pylint, pytest-count, pytest). The review verdict is PASS—phase1-projectC is complete and ready to merge. Next: phase1-projectD (Document Q&A + RAG) begins.

```
9606efa docs: update docs for phase1-projectC-task8
0bd72fb chore: validate phase1-projectC-task8 — all checks pass
ac02088 chore: init worktree phase1-projectc-task8
```

---

## 2026-06-22 (task 7 — wire proposal_generator workflow DAG + integration test)

Wired the full seven-node proposal_generator workflow DAG (CompanyResearch → OpportunityIdentifier → ProposalWriter → ProposalReview → ProposalReviewRouter → {Storage | Revise→Storage}), marked the router with `is_router=True`, and deleted the initial_node scaffold. Fixed key contract mismatches discovered during integration: OpportunityIdentifierNode now writes output under `"result"` (matching framework convention), ProposalReviewNode and ReviseNode serialize their outputs consistently, and StorageNode reconstructs the final roadmap correctly from both pass and revise paths. Created comprehensive integration test covering both routes end-to-end with mocked agents and diagnostic constraint validation (candidates sorted composite-desc, top_profiles ≤ 3, PT/EN bodies populated). All six acceptance criteria met. Review verdict: PASS (1 of 1 attempt). Test suite: 549 passed, 7 skipped (556 total, +87 from task 6). Ruff and pylint clean. Docs updated: corrected task 3 and task 6 key references, added task 7 full DAG description. Next: Task 8 — Validate (final command suite gate).

```
1abd662 docs: update docs for phase1-projectC-task7
47c5cda feat(phase1-projectC): wire proposal_generator workflow DAG + integration test (task 7)
965e2b9 chore: init worktree phase1-projectc-task7
```

---

## 2026-06-22 (task 2 — CompanyResearchNode reuse for proposal pipeline)

Task 2 implemented `ProposalCompanyResearchNode` as a subclass of Project B's `CompanyResearchNode`, reusing the base tool definitions, loop logic, and `ResearchBriefOutput` validation without modifying the parent file. The node overrides `_build_initial_messages` to consume all four `ProposalGeneratorEventSchema` fields (company_name, industry, description, intake_notes) and loads a dedicated `proposal_research_brief.j2` template via `PromptManager` — no hardcoded system prompts. Added 17 comprehensive unit tests covering subclass identity, prompt template selection, context field forwarding, loop termination, and evidence written to `TaskContext`. All 10 SDLC checks passed: standing rules clean (no f-strings in logging, no unencoded open(), no parameters named id), app/worker/db imports succeed, ruff reports zero new violations, pylint scores 10.00/10, test collection increased by 17 (478 total), full pytest suite passed (471 passed, 7 skipped). Review verdict: PASS. Documentation updated with new node entry in app-architecture-overview.md; no NEEDS_REVIEW flags. Next: Task 3 — OpportunityIdentifierNode scoring candidates against the diagnostic rubric (frequency/time_cost/buildability axes, composite formula, top-3 selection).

```
71a070e docs: update docs for phase1-projectC-task2
1918449 feat(proposal-generator): ProposalCompanyResearchNode reuse (Task 2)
3a732f9 chore: init worktree phase1-projectc-task2
```

---

## 2026-06-22 (task 1 — schemas + scaffold + registration)

Task 1 delivered the foundational schemas for the proposal_generator workflow: ProposalGeneratorEventSchema (company_name, industry, description, language, intake_notes, artifact_id, timestamp), ScoredCandidate with composite scoring formula validator, WorkflowProfile, and AutomationRoadmap with candidates-sort and top_profiles-cap validators. Workflow scaffold created with stub ProposalGeneratorWorkflow and initial_node placeholder. Registered in both workflow_registry.py and schema_registry.py (regression guard from Project B). 26 new tests cover field validation, composite math, sort invariants, registry presence, and standing rules. Fix pass 2 wrapped an overlong doc= string in brain_document.py to satisfy pylint C0301. All 454 tests pass with pylint at 10.00/10 (up from 427). Next: Task 2 — CompanyResearchNode reuse from Project B, adapting input schema and adding tool-use research loop to the proposal pipeline.

```
f8bdf92 docs: update docs for phase1-projectC-task1
3848326 fix: fix pass 2 for phase1-projectC-task1
48b417c feat(proposal-generator): schemas + scaffold + registry (Task 1)
767cf28 chore: init worktree phase1-projectc-task1
```

---

## 2026-06-22

Shipped Phase 1 Project B (research agent thin cut) via /sdlc-run in a single PASS attempt. Implemented `CompanyResearchNode` as a `ToolUseNode` subclass with a raw Anthropic tool loop exposing two tools: `web_search` (dispatches to `SearchService`/Tavily) and `submit_research_brief` (validates into `ResearchBriefOutput` with enforced non-empty `likely_time_sinks`). System prompt lives exclusively in `app/prompts/research_agent_brief.j2` loaded via `PromptManager`. `ResearchAgentWorkflow` wired as a single-node DAG; registered as `WorkflowRegistry.RESEARCH_AGENT`. Output schema shaped toward `DiagnosticIntakeOutput` per diagnostic-alignment notes, ready for the hardened version to extend. Initial 19 tests added (tool-result injection, web_search dispatch, structured-brief capture, end_turn termination, max_iterations guard, diagnostic-alignment output check); 417 tests passing. Post-merge coverage audit: fixed 2 bugs discovered (schema_registry missing `RESEARCH_AGENT` entry; `_handle_submit_brief` crashes on Pydantic ValidationError with no retry), added 10 new tests covering Pydantic event path, ValidationError retry loop, SearchService exception, unknown tool, and multi-tool responses. Final: 427 tests pass. No Celery, storage, or embedding work introduced — deferred to the hardened version when a real prospect demands it. Next: Phase 1 Project C (Proposal generator).

```diff
 app/api/schema_registry.py                         |   2 +
 app/workflows/company_research_node.py             |   8 +-
 planning/handoff.md                                | 147 ++++++++-------
 tests/workflows/test_company_research_node.py      | 207 ++++++++++++++++++++-
 tests/workflows/test_research_agent_workflow.py    |   7 +
 5 files changed, 303 insertions(+), 68 deletions(-)
```

---

## 2026-06-22

Shipped brain-rag Layer 1 via /sdlc-run: BrainDocument model + Alembic migration + index_brain.py CLI indexer (chunk/embed/upsert); 38 new tests, 398 passing. Fixed Alembic dual-head conflict (brain_documents + events both branched from learning_artifacts) by generating a merge migration and updating the .gitignore whitelist. Added D31 (SQLite ARRAY exclusion) and D32 (lazy-import CLI scripts) to planning/decisions/. Brain corpus is now semantically queryable at write-time; Layer 2 (RetrieveChunksNode corpus param) and Layer 3 (MCP endpoint) are scoped for Project D and Project F respectively. Next: Phase 1 Project B (Research agent).

```diff
 .gitignore                                         |   8 +-
 app/alembic/env.py                                 |   1 +
 ...f89e2_merge_brain_documents_and_events_heads.py |  26 ++
 .../b3c4d5e6f7a8_create_brain_documents_table.py   |  39 +++
 app/database/__init__.py                           |   6 +
 app/database/brain_document.py                     |  78 +++++
 docs/api-reference.md                              |  88 ++++-
 docs/app-architecture-overview.md                  |   3 +-
 log.md                                             |  11 +
 planning/brain-rag/sdlc/reports/document.md        |  31 ++
 planning/brain-rag/sdlc/reports/implement.md       | 103 ++++++
 planning/brain-rag/sdlc/reports/review.md          |  95 ++++++
 planning/brain-rag/sdlc/reports/test.md            |  96 ++++++
 planning/brain-rag/sdlc/reports/workflow.md        |  70 ++++
 planning/brain-rag/tasks.md                        | 223 +++++++++++++
 planning/decisions/D31-sqlite-array-exclusion.md   |  30 ++
 planning/decisions/D32-lazy-import-cli-scripts.md  |  33 ++
 planning/decisions/index.md                        |   2 +
 planning/diagnostic-alignment/notes.md             | 129 ++++++++
 planning/index.md                                  |   1 +
 planning/master-plan.md                            |   8 +
 planning/phase1-projectD/notes.md                  |  23 ++
 planning/status.md                                 |   7 +-
 scripts/index_brain.py                             | 313 ++++++++++++++++++
 tests/api/test_endpoint.py                         |   8 +-
 tests/conftest.py                                  |  13 +-
 tests/database/test_brain_document.py              | 158 +++++++++
 tests/fixtures/brain_docs/brand.md                 |  11 +
 tests/fixtures/brain_docs/career.md                |  21 ++
 tests/fixtures/brain_docs/no_headers.md            |   3 +
 tests/test_index_brain.py                          | 362 +++++++++++++++++++++
 31 files changed, 1989 insertions(+), 11 deletions(-)
```

---

## 2026-06-22 (brain-rag Layer 1 — BrainDocument model + brain corpus indexer)

Shipped the brain-rag workstream (Layer 1) through the full SDLC pipeline (implement → test → review → document) in a single attempt, PASS verdict. Implemented `BrainDocument` SQLAlchemy model (`app/database/brain_document.py`) with UUID PK, file_path, doc_type, section, content, Vector(1024) embedding, indexed_at, nullable client_slug and workflow_patterns ARRAY; exported it from `app/database/__init__.py`; generated a hand-crafted Alembic migration (`b3c4d5e6f7a8_create_brain_documents_table.py`). Created `scripts/index_brain.py` — a standalone CLI with `--brain-path`, `--rebuild`, and `--dry-run` args that walks a 60-file brain corpus (decisions, projects, career, brand, business, content, diagnostic, memory), chunks by H2/H3 section, embeds via Voyage AI in batches, and upserts into brain_documents with incremental mtime-based skip. 38 brain-specific tests (25 indexer unit tests + 13 model schema tests); 7 round-trip tests marked skip with clear reason (SQLite ARRAY incompatibility). Full suite: 398 passed, 7 skipped. Ruff clean, pylint 9.99/10 (one advisory C0301 line-length). Docs updated: new BrainDocument section in `docs/api-reference.md` (full column reference + indexer CLI args); `docs/app-architecture-overview.md` updated to list BrainDocument as shipped. Layer 2 (RetrieveChunksNode corpus parameter) is scoped for Project D via `planning/phase1-projectD/notes.md`; Layer 3 (MCP server / `/brain/search`) is scoped for Project F. Next: Phase 1 Project B (Research agent).

```
c1f3b1a docs: update docs for brain-rag
42ff61e feat: implement brain-rag Layer 1 — BrainDocument model + index_brain.py
```

---

## 2026-06-22 (Project A live run on the Claude Code SDK + bug fix)

Ran Project A (`content_pipeline`) end-to-end for the first time against a real LLM through the newly-landed `CLAUDE_CODE_SDK` provider, feeding it `https://www.youtube.com/watch?v=DzbqeO_diOQ` digest-only (`make_blog=false`), and used the recent per-node observability work to watch every step. The full trace and verdict are captured in a new run log, `planning/test-runs/phase1-projectA-test-run1.md`. The run validated the SDK path (real Sonnet structured `SummaryOutput`, Voyage embedding persisted, digest HTML written — ~79s for the Summarizer) and surfaced one real production bug. Outcomes: (1) per Brandon's call, switched all five content_pipeline LLM nodes (`summarizer`, `blog_writer`, `self_critic`, `revise`, `translate_ptbr`) from `ModelProvider.ANTHROPIC` / `claude-opus-4-8` to `CLAUDE_CODE_SDK` / `sonnet` as the new default (revert per-node when metered-API billing is wanted). (2) Fixed a `StorageNode` `DetachedInstanceError` the run exposed: `_persist()` commits and closes its session (SQLAlchemy `expire_on_commit`), then `process()` read `artifact.id` afterward — fixed by capturing the id from the event before persisting. The existing StorageNode tests monkeypatch `_persist`, so this real-session path had zero coverage; added a regression test that guards it. (3) Made SDK token accounting meaningful — `ClaudeAgentSdkBackend` now sums `input_tokens` + `cache_read_input_tokens` + `cache_creation_input_tokens`, since the SDK reports most prompt tokens as cache (the run showed a misleading `input_tokens=4` for a full transcript). Also aligned three stale node-config tests to the SDK/sonnet default, added a cache-token test, and gitignored the `_digest/` runtime output. Final validation: 360 tests pass, ruff clean, pylint 10.00/10. Note for local runs: the real `VOYAGE_API_KEY`/`ANTHROPIC_API_KEY` live in the root `.env.local`, which nothing auto-loads — export it (`set -a; source ../.env.local; set +a`) before launching the worker from `app/`. Next: Phase 1 Project B (Research agent).

```diff
 .gitignore                                         |   3 +
 app/services/claude_code/sdk_backend.py            |  22 +++-
 app/workflows/content_pipeline_workflow_nodes/blog_writer_node.py    |   4 +-
 app/workflows/content_pipeline_workflow_nodes/revise_node.py         |   4 +-
 app/workflows/content_pipeline_workflow_nodes/self_critic_node.py    |   4 +-
 app/workflows/content_pipeline_workflow_nodes/storage_node.py        |  13 +-
 app/workflows/content_pipeline_workflow_nodes/summarizer_node.py     |   4 +-
 app/workflows/content_pipeline_workflow_nodes/translate_ptbr_node.py |   4 +-
 planning/test-runs/phase1-projectA-test-run1.md    | 133 +++++++++++++++++++++
 tests/services/test_claude_code_sdk_backend.py     |  28 +++++
 tests/workflows/content_pipeline/test_storage_node.py                |  35 ++++++
 tests/workflows/content_pipeline/test_summarizer_node.py             |   6 +-
 tests/workflows/content_pipeline/test_translate_ptbr_node.py         |   6 +-
 tests/workflows/test_content_blog_branch.py        |   6 +-
 14 files changed, 249 insertions(+), 23 deletions(-)
```

## 2026-06-22 (Docs housekeeping — OKF frontmatter + External SDK references)

Added OKF frontmatter (type/title/description) to `docs/voyage_ai.md` and `docs/claude-agent-sdk.md` to align with project documentation standards. Updated `docs/index.md` to add a new "External SDK references" section with entries for both documents, improving the navigation index. Pure documentation changes; no schema or code changes. Project A remains fully complete; Project B (research agent) is next.

```diff
 docs/claude-agent-sdk.md | 6 ++++++
 docs/index.md            | 7 +++++++
 2 files changed, 13 insertions(+)
```

---

## 2026-06-22 (Project A follow-ups — golden-corpus fixtures + PT-BR translation node)

Closed all open Project A (content_pipeline) follow-ups. Item 1: vendored two real transcripts into `tests/fixtures/transcripts/` + added `load_transcript()` fixture in `conftest.py` + wrote two realistic fetch/summarize tests. Item 2: confirmed `SummaryOutput`'s lean schema (title + summary) is intentional vs the site template (no change). Item 3: Brandon decided PT-BR translation belongs to Project A as a dropped MVP item, then built it — ported claude-translator.ts into `app/prompts/translate_ptbr.j2` + `TranslatePtBrNode` (terminal node of the blog branch, ReviseNode → TranslatePtBrNode, inherits make_blog gate). Tests + docs (api-reference.md, app-architecture-overview.md) updated. 358 tests pass, ruff clean, pylint 10.00/10. Not a block status change — Project A was already Done; this is follow-up hardening. Next: Phase 1 Project B (Research agent).

```diff
 app/workflows/content_pipeline_workflow.py         |  19 ++-
 docs/api-reference.md                              |  56 ++++++++-
 docs/app-architecture-overview.md                  |   1 +
 planning/handoff.md                                | 136 +++++++-----------
 planning/phase1-projectA/follow-ups.md             |  45 ++++---
 tests/conftest.py                                  |  22 +++-
 tests/workflows/content_pipeline/test_fetch_nodes.py |  19 +++
 tests/workflows/content_pipeline/test_summarizer_node.py |  21 ++++
 tests/workflows/test_content_pipeline_workflow.py  |  26 ++--
 9 files changed, 241 insertions(+), 104 deletions(-)
```

Untracked files added: `app/prompts/translate_ptbr.j2`, `app/workflows/content_pipeline_workflow_nodes/translate_ptbr_node.py`, `tests/fixtures/transcripts/` (fixture directory), `tests/workflows/content_pipeline/test_translate_ptbr_node.py`.

---

## 2026-06-22 (session wrap-up — feature-claude-code-session-provider)

Session wrap-up for feature-claude-code-session-provider: drove the spec to a full PASS via `/sdlc-block` (all 5 tasks merged, 353 tests, ruff clean, pylint 10/10). CLAUDE_CODE_SESSION provider + BastionSessionBackend reuse the SDK seam and shell out to bastion ask with pinned v0.1.0 flags. Both Claude Code provider modes (SDK + session) are now complete. Two infra fixes unblocked the run: (1) symlinked the built bastion v0.1.0 binary onto PATH (~/.local/bin/bastion), enabling bastion-side discovery at `worker/config.py` initialization; (2) gitignored `/scripts/` (task agents were regenerating machine-specific local dev helpers that tripped the pre-flight/merge guards — now marked non-tracked per infrastructure precedent). Confirmed bastion-side Block G (bastion ask) is DONE and contract-aligned verbatim: config-from-env (BASTION_BIN, CLAUDE_CODE_TMUX_SESSION, CLAUDE_CODE_WORKDIR, CLAUDE_CODE_IO_DIR, CLAUDE_CODE_SESSION_TIMEOUT_SECONDS), writes prompt + schema (if structured), calls `bastion ask` with pinned flags, parses answers (JSON or markdown), returns None for token/cost. Remaining: operator-run subscription-host e2e gates on both modes (need claude CLI logged into subscription for real billing verification). Wrote planning/handoff.md.

```diff
 app/core/nodes/agent.py                            |  14 +-
 app/services/claude_code/__init__.py               |   2 +
 app/services/claude_code/bastion_backend.py        | 192 ++++++++++++++
 docs/api-reference.md                              | 108 +++++++-
 docs/configuration.md                              |   5 +
 log.md                                             |  65 +++++
 .../sdlc/reports/block-workflow.md                 |  36 +--
 .../sdlc/reports/task1-log.md                      |   2 +-
 .../sdlc/reports/task2-document.md                 |  29 +++
 .../sdlc/reports/task2-implement.md                |  64 ++++++
 .../sdlc/reports/task2-log.md                      |  40 +++
 .../sdlc/reports/task2-review.md                   |  46 ++++
 .../sdlc/reports/task2-test.md                     | 181 +++++++++++++
 .../sdlc/reports/task2-workflow.md                 |  95 +++++++
 .../sdlc/reports/task3-document.md                 |  27 ++
 .../sdlc/reports/task3-implement.md                |  51 ++++
 .../sdlc/reports/task3-log.md                      |  33 +++
 .../sdlc/reports/task3-review.md                   |  45 ++++
 .../sdlc/reports/task3-test.md                     | 160 ++++++++++
 .../sdlc/reports/task3-workflow.md                 |  71 +++++
 .../sdlc/reports/task4-document.md                 |  16 ++
 .../sdlc/reports/task4-implement.md                |  50 ++++
 .../sdlc/reports/task4-log.md                      |  33 +++
 .../sdlc/reports/task4-net-new-lint-baseline.json  |   1 +
 .../sdlc/reports/task4-review.md                   |  59 +++++
 .../sdlc/reports/task4-test.md                     | 138 ++++++++++
 .../sdlc/reports/task4-workflow.md                 |  66 +++++
 .../sdlc/reports/task5-document.md                 |  29 +++
 .../sdlc/reports/task5-implement.md                |  87 +++++++
 .../sdlc/reports/task5-log.md                      |  36 +++
 .../sdlc/reports/task5-net-new-lint-baseline.json  |   1 +
 .../sdlc/reports/task5-review.md                   |  63 +++++
 .../sdlc/reports/task5-test.md                     | 155 +++++++++++
 .../sdlc/reports/task5-workflow.md                 | 104 ++++++++
 planning/status.md                                 |   7 +-
 tests/core/test_claude_code_provider_routing.py    |  74 +++++-
 tests/services/test_claude_code_bastion_backend.py | 286 +++++++++++++++++++++
 37 files changed, 2431 insertions(+), 40 deletions(-)
```

---

## 2026-06-22 (task 5 — validation gate)

Task 5 validated the complete feature-claude-code-session-provider spec. Tasks 1–4 (config surface, BastionSessionBackend implementation, CLAUDE_CODE_SESSION provider routing, docs) were already merged into this worktree; Task 5 corrected the sparse-checkout to include `tests/` and ran the full validation suite. All acceptance criteria verified: a node with `model_provider=ModelProvider.CLAUDE_CODE_SESSION` successfully routes to `BastionSessionBackend`, which shells out to `bastion ask` with the exact pinned v0.1.0 flags (--session, --prompt-file, --out, --dir, --timeout), handles structured (JSON-schema) output by parsing the `.json` answer file into `ClaudeResult.structured`, handles free-text output by returning the markdown answer as `text`, returns None for all token/cost fields with `model` recorded, cleans temp files in all paths (success and error), and raises descriptive errors carrying bastion's stderr on non-zero exit, missing answer, or timeout. Review verdict: PASS — all 6 acceptance criteria met, all 7 gating checks pass (ruff clean, pylint 10.00/10, 353 tests pass including 22 session-mode tests, no net-new lint violations, no standing-rule violations, no test count regression). The spec is complete and ready for merge.

```
0b8837e docs: update docs for feature-claude-code-session-provider-task5
4becde5 feat: implement feature-claude-code-session-provider-task5
078560f chore: init worktree feature-claude-code-session-provider-task5
```

## 2026-06-22 (task 4 — docs: api-reference.md coverage for CLAUDE_CODE_SESSION)

Task 4 completed the documentation coverage for `ModelProvider.CLAUDE_CODE_SESSION` and `BastionSessionBackend` in `docs/api-reference.md`. The implementation stage added an external-dependency note pinning `bastion ask` to v0.1.0 with exact flag surface and a cross-link to the SDK-mode feature. All seven gating checks passed: standing rules clean, ruff and pylint both clean (10.00/10), 353 tests pass with no regression, and no emoji in modified markdown. Review verdict: PASS. All acceptance criteria for Task 4 are met, confirming the documentation is complete and accurate. Next: Task 5 — Validate (run final gating checks and manual e2e test with bastion).

```
adfe096 docs: update docs for feature-claude-code-session-provider-task4
3d1e346 feat: implement feature-claude-code-session-provider-task4
78f66cd chore: init worktree feature-claude-code-session-provider-task4
```

### 2026-06-22 (task 3 — wire CLAUDE_CODE_SESSION into provider factory)

Completed Task 3: wired `ModelProvider.CLAUDE_CODE_SESSION` into the `AgentNode` provider factory in `app/core/nodes/agent.py` additively alongside the existing `CLAUDE_CODE_SDK` routing. Added the enum value, `case` arm in `__get_model_instance`, and a new `__get_claude_code_session_model` method that returns `ClaudeCodeModel(backend=BastionSessionBackend(), ...)`. Extended `tests/core/test_claude_code_provider_routing.py` with three new routing tests covering the enum value, model construction over the faked backend, and verification that `usage.model` is recorded while token fields remain `None` (session-mode limitation). All gating checks passed (ruff clean, pylint 10.00/10, 353 pytest pass with +3 new tests); document phase updated `docs/api-reference.md` with provider routing details. Review verdict: PASS — all six acceptance criteria met. Next: Task 4 — Docs (add `ModelProvider.CLAUDE_CODE_SESSION` + `BastionSessionBackend` to the api-reference.md reference section).

```
429bfe4 docs: update docs for feature-claude-code-session-provider-task3
dd63b45 feat: implement feature-claude-code-session-provider-task3
017fb4c chore: init worktree feature-claude-code-session-provider-task3
```

## 2026-06-22 (task 2 — BastionSessionBackend implementation and testing)

Task 2 implemented the `BastionSessionBackend` class as a second implementation of the `ClaudeCodeBackend` protocol, enabling LLM calls to execute on the live interactive Claude Code session via the `bastion ask` command. The backend resolves config from environment (`BASTION_BIN`, `CLAUDE_CODE_TMUX_SESSION`, `CLAUDE_CODE_WORKDIR`, `CLAUDE_CODE_IO_DIR`, `CLAUDE_CODE_SESSION_TIMEOUT_SECONDS`), writes a prompt file containing the system + user prompt plus a JSON-schema instruction when structured output is requested, invokes `bastion ask` with the pinned v0.1.0 flags off the event loop via `run_in_executor` to avoid blocking, parses the answer file (JSON for structured requests, raw markdown for free text), and returns a `ClaudeResult` with token/cost fields set to `None` as documented. Errors (non-zero exit, missing answer file, timeout) raise descriptive `RuntimeError` exceptions carrying `bastion ask`'s stderr for debugging. All temp files are cleaned up in a `finally` block. Comprehensive unit tests (15 tests) verify binary resolution, prompt-file writing with schema instructions, answer-file parsing, error paths, and cleanup. Review passed all 7 gating checks; 350 tests passing total (from 0 baseline), ruff and pylint clean, all standing rules met. Next: Task 3 — Wire CLAUDE_CODE_SESSION into the provider factory in agent.py and extend routing tests.

```
f26c6ec docs: update docs for feature-claude-code-session-provider-task2
86c82f5 feat: implement feature-claude-code-session-provider-task2
83f09bc chore: init worktree feature-claude-code-session-provider-task2
```

## 2026-06-21 (task 1 — config surface for session mode)

Task 1 implemented the configuration surface for Claude Code session mode: added a `# Claude Code — session mode (bastion)` block to `app/.env.example` with all five env vars and defaults, and documented the new session mode in `docs/configuration.md` with a dedicated section covering prerequisites (bastion binary on PATH, tmux session logged into Claude Code subscription, pre-trusted workdir, IO dir on same host) and the documented limitations (no token usage surfaced → `usage` tokens are `None`; per-turn model is advisory only since the session's model is fixed at launch in v0.1.0). Review verdict is PASS: all files correctly updated, all gating checks passed (ruff, pylint, db imports, no test count decrease). Next: Task 2 — BastionSessionBackend.

```
4acb61d docs: update docs for feature-claude-code-session-provider-task1
e0ac042 feat: implement feature-claude-code-session-provider-task1
c27e342 chore: init worktree feature-claude-code-session-provider-task1
```

---

## 2026-06-22

Added local dev scripts: `scripts/dev-setup.sh` (one-time Homebrew Postgres/Redis install, local DB creation, pgvector extension, .env generation, Alembic migrations) and `scripts/dev.sh` (two-pane tmux launcher — FastAPI on top, Celery worker on bottom). Also generated missing Alembic migration `app/alembic/versions/cc3ad971094e_create_events_table.py` for the events table schema that existed only in Docker previously. Both scripts and the migration are local development helpers (not tracked in git, ignored by `.gitignore`). Updated `.gitignore` to explicitly ignore `/scripts/` with a comment explaining they are machine-specific and regenerated on demand by tooling. Infrastructure/tooling work only — no schema changes, no product code affected. Prerequisite for unblocking feature-claude-code-session-provider after bastion Block G ships.

```diff
 .gitignore | 6 +++++-
 1 file changed, 5 insertions(+), 1 deletion(-)
```

*(plus untracked local files: `scripts/dev-setup.sh`, `scripts/dev.sh`, `app/alembic/versions/cc3ad971094e_create_events_table.py`)*

---

## 2026-06-21 (session — /sdlc-block orchestration of CLAUDE_CODE_SDK + handoff)

Ran `/sdlc-block feature-claude-code-sdk-provider` to a full PASS: all 7 tasks merged across 5 dependency-ordered waves with zero escalations on first attempt. Shipped `ModelProvider.CLAUDE_CODE_SDK` — a subscription-billed Claude Code provider mode via the `claude-agent-sdk` CLI integration, with env-scrub to blank `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` at call time, forcing billing to the user's Max/Pro subscription. Implemented a reusable `ClaudeCodeBackend` protocol + `ClaudeResult` dataclass (text, structured, usage, cost) and a pydantic-ai 0.1.5 `ClaudeCodeModel` seam that both the immediate subscription-mode feature and the later session-persistence feature will use interchangeably. Independent verification: ruff clean, pylint 10.00/10, 335 tests pass (+40 Claude-specific, covering full env-scrub/error-path spectrum, structured output, 2-tuple return contract). Pre-flight security fix: added `.env.local` to `.gitignore` (was leaking `ANTHROPIC_API_KEY`); committed specs + vendored SDK reference doc (0f7396b). Outstanding gate: manual operator-run subscription-host e2e (billing confirmation via real token usage reported in `NodeRun.usage`) deferred and recorded in spec Notes. Next: `feature-claude-code-session-provider` (Task 1: Bastion session backend + routing), currently blocked on bastion Block G shipping. Wrote `planning/handoff.md` to frame the session-provider feature and its bastion dependency.

## 2026-06-21 (task 7 — Validation gate: CLAUDE_CODE_SDK provider acceptance suite)

Task 7 completed the final validation gate for the `CLAUDE_CODE_SDK` provider feature. Tasks 1–6 implemented the full feature (backend protocol, SDK backend with env-scrub, ClaudeCodeModel with both text and structured output paths, provider routing); Task 7 ran the acceptance suite to confirm all acceptance criteria are met and the codebase remains healthy. All validation commands passed: SDK import succeeds, ruff reports zero violations, pylint scored 10.00/10, and 335 tests pass (33 Claude-specific). The review gate confirmed all six acceptance criteria are MET, including the backend protocol reusability for later session-mode feature. The manual e2e (subscription host with real token billing verification) remains as operator-run gate before production. Next: Task 1 of feature-claude-code-session-provider — Bastion session backend integration.

```
307f0b1 docs: update docs for feature-claude-code-sdk-provider-task7
3c32c2b feat: implement feature-claude-code-sdk-provider-task7
c6dc983 chore: init worktree feature-claude-code-sdk-provider-task7
```

## 2026-06-21 (task 6 — Docs)

Completed Task 6: filled remaining documentation gaps for the `CLAUDE_CODE_SDK` provider. Earlier tasks' per-task `/document` stages had already added bulk Claude Code coverage (env-var table rows, `ModelProvider.CLAUDE_CODE_SDK` enum, `app/services/claude_code` package reference) to both `docs/configuration.md` and `docs/api-reference.md`. Task 6 closed the final gaps: expanded configuration.md §3 with explicit host prerequisites (`claude-agent-sdk` installed + `claude` CLI present and logged into a Max/Pro subscription), subscription billing note (blanks `ANTHROPIC_API_KEY` and `ANTHROPIC_AUTH_TOKEN` in spawned CLI env), usage-reporting note (SDK mode returns real `input_tokens`/`output_tokens` + `total_cost_usd` flowing into `NodeRun.usage`), and cross-link to the brain coordination doc; also added "Cross-repo coordination" subsection to api-reference.md §package, explaining that `ClaudeCodeBackend` + `ClaudeCodeModel` are reused unchanged by the later `CLAUDE_CODE_SESSION` mode and cross-linking the brain doc and configuration.md. Review verdict: PASS (all 8 gating checks pass, 335 tests green, pylint 10/10, ruff clean, no issues). All acceptance criteria met: configuration.md documents the four env vars with descriptions, host prerequisites, API key scrub, and real-token reporting; api-reference.md adds `ModelProvider.CLAUDE_CODE_SDK`, the full package surface, and cross-repo coordination notes. Next: Task 7 — Validate (run validation commands on a subscription-authenticated host and record manual e2e result showing subscription-mode billing and real token usage).

```
6f3c8d6 docs: update docs for feature-claude-code-sdk-provider-task6
2aedc0e feat: implement feature-claude-code-sdk-provider-task6
e49494f chore: init worktree feature-claude-code-sdk-provider-task6
```

## 2026-06-21 (task 5 — Wire CLAUDE_CODE_SDK into the provider factory)

Completed Task 5: wired `ModelProvider.CLAUDE_CODE_SDK` into the AgentNode factory via a new `__get_claude_code_sdk_model` method that constructs `ClaudeCodeModel` with `ClaudeAgentSdkBackend`. Added four routing tests following the `StubAgentNode` pattern to verify enum value dispatch, factory construction, real usage stamping in `run_agent_recorded`, and the pydantic-ai 0.1.5 tuple return contract. All 7 gating checks pass (335 tests collected, +15 net new; ruff clean; pylint 10.0/10). Documentation was patched by the document stage (configuration.md + api-reference.md updated with `CLAUDE_CODE_SDK` enum value, provider table row, env var documentation, and package export reference). Review verdict: PASS — all acceptance criteria met, no issues found. Next: Task 6 — Docs (full documentation completion + cross-linking to brain coordination doc) and Task 7 — manual subscription-mode e2e validation.

```
3280a25 docs: update docs for feature-claude-code-sdk-provider-task5
a0473cb feat: implement feature-claude-code-sdk-provider-task5
f29b758 chore: init worktree feature-claude-code-sdk-provider-task5
```

## 2026-06-21 (task 4 — Shared `ClaudeCodeModel` pydantic-ai Model)

Implemented `ClaudeCodeModel` as the pydantic-ai 0.1.5 `Model` subclass, handling both text and structured output paths via a pluggable `ClaudeCodeBackend` protocol. The `request()` method correctly returns the pinned 0.1.5 2-tuple `(ModelResponse, Usage)`, emits `ToolCallPart` when `output_tools` is non-empty (extracting the first tool's JSON schema and calling the backend with structured-output mode), and falls back to `TextPart` for free-text output. Properties (`model_name`, `system`, `base_url`) and abstract methods (`customize_request_parameters`, `_get_instructions`, `request_stream`) are all implemented; `request_stream` raises `NotImplementedError` as documented future work. Review passed with all acceptance criteria met; 320 tests collected and passed (net +10). The model is exported from `app/services/claude_code/__init__.py` so the provider factory (Task 5) can import and instantiate it. Next: Task 5 — Wire `CLAUDE_CODE_SDK` into the provider factory.

```
d46a0ad docs: update docs for feature-claude-code-sdk-provider-task4
69e2938 feat: implement feature-claude-code-sdk-provider-task4
44dbf9f chore: init worktree feature-claude-code-sdk-provider-task4
```

## 2026-06-21 (task 3 — SDK backend ClaudeAgentSdkBackend)

Implemented `ClaudeAgentSdkBackend` class reading `CLAUDE_CODE_*` env vars at call time, constructing `ClaudeAgentOptions`, blanking `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` to force subscription billing, draining `query()` async generator to terminal `ResultMessage`, raising descriptive `RuntimeError` on non-success/error/timeout, and mapping successful results into `ClaudeResult` with proper field mapping (result→text, structured_output→structured, usage tokens, total_cost_usd, session_id). Wrote 11 comprehensive unit tests covering option building, env scrub, result mapping (text, structured, missing fields), and all error paths, monkeypatching `claude_agent_sdk.query` to avoid network/CLI calls. All tests pass (321 total, +11 new); ruff, pylint, and standing-rules checks all clean. Review verdict: PASS — all in-scope Task 3 criteria met. Next: Task 4 — Shared ClaudeCodeModel (pydantic-ai 0.1.5 Model).

```
312798e docs: update docs for feature-claude-code-sdk-provider-task3
0201da7 feat: implement feature-claude-code-sdk-provider-task3
5ad6568 chore: init worktree feature-claude-code-sdk-provider-task3
```

## 2026-06-21 (task 2 — backend protocol + result type)

Implemented the `ClaudeCodeBackend` protocol and `ClaudeResult` dataclass for the Claude Code SDK provider feature. Created `app/services/claude_code/` package with `backend.py` defining a `@runtime_checkable` typing.Protocol with one async method (`run`) and a dataclass carrying the LLM response shape (text, structured output, token counts, cost, model name, session ID). Added `__init__.py` re-exports for clean package seams. Wrote eight unit tests pinning the contract: construction, field set, protocol conformance (isinstance checks), and async execution via `asyncio.run`. All gating checks pass: ruff clean, pylint 10.00/10, 310 tests collected (increased from baseline). Review confirmed all Task 2 in-scope criteria met; tasks 3–5 criteria appropriately deferred. Docs: `api-reference.md` updated with `ClaudeResult` and `ClaudeCodeBackend` references; `app-architecture-overview.md` flagged NEEDS_REVIEW for later when full integration is complete. Next: Task 3 — SDK backend implementation (`ClaudeAgentSdkBackend`).

```
7a3da46 docs: update docs for feature-claude-code-sdk-provider-task2
a100628 feat: implement feature-claude-code-sdk-provider-task2
97b89fe chore: init worktree feature-claude-code-sdk-provider-task2
```

## 2026-06-21 (task 1 — Add the dependency + config surface)

Task 1 completed successfully: added `claude-agent-sdk>=0.1.0` to `pyproject.toml` (resolved to 0.2.106) and ran `uv sync`; added `# Claude Code — SDK mode (subscription)` block to `app/.env.example` with four config variables (`CLAUDE_CODE_BIN`, `CLAUDE_CODE_CWD`, `CLAUDE_CODE_PERMISSION_MODE`, `CLAUDE_CODE_SDK_TIMEOUT_SECONDS`); documented the new variables in `docs/configuration.md` section 2. All 9 gating checks passed (302/302 tests, ruff clean, pylint 10.00/10). Review verdict: PASS. Next: Task 2 — Backend protocol + result type.

```
8e6ac47 docs: update docs for feature-claude-code-sdk-provider-task1
d0c7c05 feat: implement feature-claude-code-sdk-provider-task1
0191b7c chore: init worktree feature-claude-code-sdk-provider-task1
```

## 2026-06-20

Post-ship coverage audit of Phase 1, Project A (`content_pipeline`) before opening Project B. The verdict was that coverage is already strong — `uv run python -m pytest` stays at 295 green, and every node (source/blog routers, both fetch nodes with their error paths, summarizer, storage + digest renderer, the linear blog branch), the schema, the LearningArtifact model, and both end-to-end integration paths carry real behavior-level tests. So rather than manufacture a test-writing effort, I recorded an honest, non-blocking backlog in `planning/phase1-projectA/follow-ups.md`: two deferred tests (anti-spoof/subdomain cases for `_is_youtube_url`, and a test documenting that `SelfCriticNode.approved` is intentionally inert because the blog branch is a one-shot linear writer→critic→revise, not a loop), two low-effort reuse carryovers (wire the site's transcript corpus as golden fixtures; cross-check `SummaryOutput` against the site summary template), and one scope decision (the PT-BR `translate_ptbr.j2` + translation AgentNode from the reuse spec was never built — the shipped pipeline is digest + optional EN blog only — so whether translation is a Project A or a content-publishing concern needs deciding before it's scheduled). Also reconciled the cross-repo reuse spec `learn-ai/planning/5.1-reuse-for-project-a/tasks.md` against what actually shipped (Done / carried-over / decision-pending / correctly-skipped per item), added a follow-ups callout to `status.md`, and wrote `planning/handoff.md` for the next session. No product code changed; Project B (research agent) is next.

```diff
 planning/status.md | 4 +++-
 1 file changed, 3 insertions(+), 1 deletion(-)
```
*(plus new untracked: `planning/phase1-projectA/follow-ups.md`, `planning/handoff.md`)*

---

## 2026-06-20

Shipped Phase 1, Project A — the content_pipeline workflow — driving all 8 tasks of its spec to completion through three /sdlc-block orchestrator segments. The pipeline turns a YouTube or article URL into a categorized, embedded LearningArtifact plus a static-HTML personal digest (always), and an opt-in self-corrected blog draft when make_blog=true. The wired DAG runs SourceRouterNode → {FetchTranscriptNode | FetchArticleNode} → SummarizerNode → StorageNode → BlogDecisionRouterNode → BlogWriterNode → SelfCriticNode → ReviseNode. New this project: a LearningArtifact SQLAlchemy model with a pgvector(1024) embedding column and its Alembic migration; embeddings written at write time; a pure-function digest_renderer for static HTML pages + category indexes; the reusable FetchArticleNode (trafilatura-first, Firecrawl-fallback); and a 9-field SummaryOutput schema. The storage node persists via the GenericRepository + db_session factory seam because the framework instantiates nodes with zero constructor args (no injection point) — this was surfaced by an authoring-time /breakdown and kept the node deployment-agnostic per rule 7. Three of eight tasks needed a human touch: tasks 4 and 6 escalated on the same additive-doc merge conflict (parallel rows appended to docs/app-architecture-overview.md), each resolved by hand in seconds; the rest auto-merged. 295 tests pass (up from 244), ruff clean. Project B (research agent) is next.

```diff
 app/alembic/env.py                                 |   1 +
 ...a1b2c3d4e5f6_create_learning_artifacts_table.py |  40 ++
 app/core/nodes/router.py                           |   4 +-
 app/database/learning_artifact.py                  |  74 ++++
 app/prompts/blog_reviser.j2                        |  24 ++
 app/prompts/blog_self_critic.j2                    |  28 ++
 app/prompts/blog_writer.j2                         |  34 ++
 app/prompts/content_summarizer.j2                  |  45 ++
 app/schemas/content_pipeline_schema.py             |  28 +-
 app/workflows/content_pipeline_workflow.py         |  95 ++++-
 app/workflows/content_pipeline_workflow_nodes/blog_decision_router_node.py |  31 ++
 app/workflows/content_pipeline_workflow_nodes/blog_writer_node.py |  38 ++
 app/workflows/content_pipeline_workflow_nodes/digest_renderer.py | 107 +++++
 app/workflows/content_pipeline_workflow_nodes/fetch_article_node.py |  28 ++
 app/workflows/content_pipeline_workflow_nodes/fetch_transcript_node.py |  41 ++
 app/workflows/content_pipeline_workflow_nodes/initial_node.py |   7 -
 app/workflows/content_pipeline_workflow_nodes/revise_node.py |  49 +++
 app/workflows/content_pipeline_workflow_nodes/self_critic_node.py |  47 +++
 app/workflows/content_pipeline_workflow_nodes/source_router_node.py |  48 +++
 app/workflows/content_pipeline_workflow_nodes/storage_node.py | 110 +++++
 app/workflows/content_pipeline_workflow_nodes/summarizer_node.py |  89 ++++
 docs/api-reference.md                              | 457 ++++++++++++++++++++-
 docs/app-architecture-overview.md                  |  16 +-
 tests/core/test_nodes_router.py                    |  12 +
 tests/database/test_learning_artifact.py           | 135 ++++++
 tests/workflows/content_pipeline/test_fetch_nodes.py | 131 ++++++
 tests/workflows/content_pipeline/test_storage_node.py | 150 +++++++
 tests/workflows/content_pipeline/test_summarizer_node.py | 110 +++++
 tests/workflows/test_content_blog_branch.py        | 182 ++++++++
 tests/workflows/test_content_pipeline_workflow.py  | 260 +++++++++++-
 33 files changed, 2388 insertions(+), 41 deletions(-)
```

---

## 2026-06-20 (task 8 — Validate)

Final validation of the complete content pipeline: all lint, test, import, and database migration checks passed. The workflow graph is fully wired (SourceRouterNode → fetch nodes → SummarizerNode → StorageNode → BlogDecisionRouterNode → blog branch), all prompts are externalized to `.j2` files, embedding generation is integrated at write time, and 1024-dim Voyage vectors are persisted to pgvector. Digest-only and blog-generation paths both tested end-to-end with mocked agents and services. The implementation enforces deployment-agnostic design: all persistence and service calls are injected, no hardcoded paths or credentials. Next: Phase 1, Project B — Research agent (thin → hardened).

```
2673cfd docs: update docs for phase1-projectA-task8
6ceb01f feat: implement phase1-projectA-task8
f9e7078 chore: init worktree phase1-projecta-task8
```

---

## 2026-06-20 (task 7 — Workflow wiring + integration tests)

Task 7 delivered the complete content_pipeline workflow assembly: rewrote `ContentPipelineWorkflow.workflow_schema` with `SourceRouterNode` as start, wired both fetch nodes through the summarizer and storage, added the blog decision router branching to the writer→critic→revise chain, marked routers with `is_router=True` in NodeConfig, deleted the scaffold initial_node.py, and confirmed workflow validator passes with no cycles. Rewrote the integration test suite with two end-to-end paths (digest-only and blog-inclusive), verified both services and agents mock cleanly, and confirmed net test count increased. All code follows Python 3.10+ syntax, module docstrings on line 1, prompts via PromptManager, and no deployment logic inside nodes — repository injection confirmed at the workflow/worker boundary matching Task 5's design. Review passed on first attempt with PASS verdict. Next: Task 8 — Validate - Run the full validation commands (ruff, pylint, pytest, imports, migration apply) to confirm all gates pass.

```
139dc00 docs: update docs for phase1-projectA-task7
a45128d feat: implement phase1-projectA-task7
de068db chore: init worktree phase1-projecta-task7
```

---

## 2026-06-20 (task 5 — Storage node with embedding and HTML digest)

Implemented the storage layer: `StorageNode(Node)` persists `LearningArtifact` rows with real-time 1024-dim Voyage embeddings via `EmbeddingService`, writes static HTML digests per category with index regeneration, and uses injected `GenericRepository` for deployment-agnostic persistence (no session logic inside nodes per standing rule 7). Full pipeline now chains cleanly from source router → fetch nodes → summarizer → storage, with embeddings written at write time. Tests cover embedding service integration, repository CRUD, and HTML rendering. Review passed with PASS verdict. Next: Task 6 — Blog branch with writer, self-critic, and reviser agents.

```
0633435 docs: update docs for phase1-projectA-task5
77ef050 feat: implement phase1-projectA-task5
1d7a066 chore: init worktree phase1-projecta-task5
```

---

## 2026-06-20 (task 3 — Source router + fetch nodes)

Implemented `SourceRouterNode` to classify YouTube vs article URLs and route to the appropriate fetch node. `FetchTranscriptNode` calls `TranscriptService.fetch_transcript()` for YouTube content, and `FetchArticleNode` calls `ArticleExtractionService.extract()` for article URLs with trafilatura-first/Firecrawl-fallback logic. Both nodes gracefully handle failures by storing `fetch_status` without crashing the pipeline. All three nodes (source router + two fetch nodes) were added to `app/workflows/content_pipeline_workflow_nodes/` with full unit tests covering YouTube routing, article routing, unknown-URL fallback, and graceful error handling. Test suite passes with PASS verdict on first review attempt. Router classification and fetch logic are ready; next is the `SummarizerNode` to process extracted content.

```
51093ec docs: update docs for phase1-projectA-task3
f2df0c4 feat: implement phase1-projectA-task3
34bb691 chore: init worktree phase1-projecta-task3
```

---

### 2026-06-20 (task 2 — LearningArtifact model + migration)

Implemented the `LearningArtifact` SQLAlchemy model with pgvector `Vector(1024)` embedding column, Alembic migration from the pgvector baseline, and test suite covering model instantiation and repository round-trip persistence. Completed event schema from Task 1 in prior session. Review passed PASS on first attempt; all validation gates confirmed (migration applies cleanly, imports succeed, test count increased per spec). Next: Task 3 — Source router + fetch nodes (YouTube/article classification + dual-fetch path).

```
0ddded0 docs: update docs for phase1-projectA-task2
1c8d320 feat: implement phase1-projectA-task2
fdb543f chore: init worktree phase1-projecta-task2-11
```

---

### 2026-06-20 (task 1 — event schema + field validation)

Completed Task 1 of the content_pipeline spec: implemented `ContentPipelineEventSchema` with required `url: str`, optional `make_blog: bool = False`, and identity fields (`artifact_id: UUID`, `timestamp`). Replaced the scaffold smoke test with a real validation test asserting all new fields and the `make_blog` default while keeping registration and graph smoke tests intact. Pipeline passed all review gates (lint, test, import checks, `WorkflowValidator` on stub graph). Review verdict: PASS on first attempt. Next: Task 2 — `LearningArtifact` model + migration (SQLAlchemy table with pgvector embedding column, Alembic migration, repository round-trip tests).

```
78a6651 docs: update docs for phase1-projectA-task1
e34220c feat: implement phase1-projectA-task1
e1d7771 chore: init worktree phase1-projecta-task1
```

---

## 2026-06-20 — incremental-execution-observability spec complete

Completed the incremental-execution-observability spec via `/sdlc-block` (8 tasks, 6 parallel dependency-ordered waves, all PASS, auto-merged). The three phases — (1) node-level status/timing envelope on TaskContext with framework-stamped node_context and injected on_progress callback, (2) per-node token/cost capture in AgentNode and ToolUseNode helper classes, and (3) read-only workflow graph introspection endpoint (GET /workflows, GET /workflows/{type}/graph) — all landed across the eight merged tasks. 238 tests pass (+15 from baseline). Also fixed CLAUDE.md and planning/harness.json to use `uv run python -m <tool>` consistently so project venv tools run instead of global uv-tool installs (bare `uv run pytest` can resolve to a global missing this repo's deps). Next: Phase 1, Project A — `content_pipeline` workflow implementation.

```diff
CLAUDE.md             | 10 ++++++----
planning/harness.json | 12 ++++++------
app/api/graph.py      | 42 ++++++++
app/api/models.py     |  9 +
app/api/router.py     |  3 +-
app/core/nodes/agent.py     | 28 +++++++
app/core/nodes/tool_use.py  | 15 +++
app/core/task.py      | 18 ++-
app/core/workflow.py   | 52 ++++++++-
app/worker/tasks.py    | 15 +-
docs/api-reference.md  | 177 ++++++++++++++++++++++++
docs/architecture_review/agent_node.md      | 31 +++-
docs/architecture_review/task_context.md    | 12 ++
docs/architecture_review/workflow.md        | 101 ++++++++++++++--
tests/api/test_graph.py  | 45 +++++++
tests/core/test_nodes_usage.py      | 202 +++++++++++++++++++++++++++
tests/core/test_observability.py    | 177 ++++++++++++++++++++++++
tests/core/test_workflow.py         | 139 +++++++++++++++++-
tests/worker/test_tasks.py          | 118 +++++++++++++++
4 files changed, 12 insertions(+), 10 deletions(-)
```

---

## 2026-06-20 (task 8 — validate all gates and confirm spec complete)

Ran the full validation suite for the incremental-execution-observability spec: import smoke tests (`main`, `worker.config`, `database.session`, `database.repository`), ruff lint, pylint, pytest collection, and pytest full run. All eight acceptance criteria confirmed green — `TaskContext.node_runs` with `NodeStatus`/`NodeRun` (including `usage`) survives `model_dump(mode="json")`; `Workflow.node_context` stamps `RUNNING`/`SUCCESS`/`FAILED` and timestamps without any node being edited; `Workflow.run()` backward-compatible with `on_progress` callback firing at each node boundary; worker persists `task_context` incrementally via flush inside the open transaction; `AgentNode` and `ToolUseNode` populate `NodeRun.usage`, non-LLM nodes leave it `None`; `GET /workflows` and `GET /workflows/{type}/graph` return correct nodes/edges for `customer_care`, unknown type returns 404; no "bastion" string in `app/`; new test count strictly greater than baseline. Review passed on the first attempt. Spec is closed — all three phases (1 incremental persistence, 2 token capture, 3 graph introspection) landed across 8 tasks. Next: Phase 1, Project A — `content_pipeline` workflow implementation.

```
0274018 docs: update docs for incremental-execution-observability-task8
2edfc4a feat: implement incremental-execution-observability-task8
dd2f5dd chore: init worktree incremental-execution-observability-task8
```

---

## 2026-06-20 (task 7 — workflow graph introspection endpoint, Phase 3)

Implemented the read-only workflow graph introspection API (Phase 3 of the incremental execution observability spec). Added `GET /workflows` listing all registered workflow types from `WorkflowRegistry` and `GET /workflows/{workflow_type}/graph` returning the static node/edge topology serialized from each workflow's `WorkflowSchema`. Introduced a new `app/api/graph.py` module and added typed Pydantic response models (`WorkflowListResponse`, `WorkflowGraphResponse`) to `app/api/models.py`. The endpoint uses node class `__name__` as identity, consistent with the `task_context.nodes` and `node_runs` keys established in earlier tasks. Unknown workflow type returns 404. Tests cover the correct node/edge set for `customer_care` (read-only introspection of the frozen reference workflow) and the 404 path. Review passed on the first attempt with all acceptance criteria met and no regressions to existing tests. Next: Task 8 — run the full validation suite (`import` smoke tests, ruff, pylint, pytest collect + run) and confirm all gates pass with no bastion references in `app/`.

```
c066cd7 docs: update docs for incremental-execution-observability-task7
42ba989 feat: implement incremental-execution-observability-task7
1127c51 chore: init worktree incremental-execution-observability-task7
```

---

## 2026-06-20 (task 6 — per-node token + cost capture)

Implemented Phase 2 of the incremental execution observability spec: per-node token and cost capture in the framework-owned `AgentNode` and `ToolUseNode` base classes. A `usage: dict | None` field was added to `NodeRun` in `app/core/task.py`, and both `app/core/nodes/agent.py` and `app/core/nodes/tool_use.py` were updated to populate `NodeRun.usage` with `{input_tokens, output_tokens, model}` from the provider response after each LLM call. Non-LLM nodes leave `usage` as `None`. Tests assert that a stubbed provider response yields the expected token counts on the `NodeRun`, and that non-LLM nodes record no usage. The review passed on the first attempt with all validation commands green. Next: Task 7 — Workflow graph introspection endpoint (Phase 3).

```
aa833a0 docs: update docs for incremental-execution-observability-task6
31ec381 feat: implement incremental-execution-observability-task6
939b0fe chore: init worktree incremental-execution-observability-task6
```

---

## 2026-06-20 (task 5 — Phase 1 test suite)

Implemented the full test suite for the Phase 1 observability layer. Tests cover the complete `NodeRun` lifecycle: `PENDING → RUNNING → SUCCESS` transitions on a happy-path workflow, `FAILED` state (with non-null `error` and `completed_at`) when a node raises — confirming the exception still propagates. An `on_progress` spy asserts the callback fires once before the first node (all `PENDING`) and once per node boundary (correct total call count and ordering). The default `on_progress=None` path is validated against the existing test suite to confirm no behavioral regression. A mid-run `model_dump(mode="json")` snapshot test confirms the observability guarantee: a partial execution produces a mix of `SUCCESS` and `PENDING` entries in `node_runs`. The review passed on the first attempt with no defects raised. Next: Task 6 — Per-node token + cost capture (Phase 2).

```
f336fc8 docs: update docs for incremental-execution-observability-task5
a037ba5 feat: implement incremental-execution-observability-task5
978cd46 chore: init worktree incremental-execution-observability-task5
```

---

## 2026-06-20 (task 4 — worker wires persistence at each boundary (Phase 1d))

Task 4 wired the `on_progress` callback in `app/worker/tasks.py` so that the worker — which already owns the DB session — persists `db_event.task_context` incrementally at every node boundary. Inside the existing `db_session` transaction, a closure captures the repository and the `db_event` row; on each invocation it assigns `db_event.task_context = task_context.model_dump(mode="json")` and issues a flush (not a commit) so the JSON snapshot is durable mid-run without prematurely closing the transaction. The terminal authoritative `repository.update(...)` call is preserved as the final write after `workflow.run()` returns. No DB or session code was added to `workflow.py` or any node — the brain remains fully agnostic, keeping D18 and D7 intact. `customer_care` and all its nodes are unchanged. Review passed on the first attempt with no blocking findings. Next: Task 5 — Tests for Phase 1.

```
106132e docs: update docs for incremental-execution-observability-task4
2afe0f7 feat: implement incremental-execution-observability-task4
d4f5da4 chore: init worktree incremental-execution-observability-task4
```

---

## 2026-06-20 (task 3 — injected progress callback on Workflow.run())

Task 3 added the `on_progress: Callable[[TaskContext], None] | None = None` parameter to `Workflow.run()` in `app/core/workflow.py`. Before the first node executes, the framework seeds every node in the schema as `PENDING` in `node_runs` and invokes `on_progress` once so callers can observe the full DAG in its initial state. After each node boundary (success or failure), `on_progress(task_context)` is called again, enabling incremental snapshots as execution proceeds. The default `None` path is fully backward-compatible — existing behavior and all prior tests are unaffected. The signature accepts a single `TaskContext` arg, keeping the seam broad enough for a future Phase 5 publisher without changing the brain. No node was edited; `customer_care` and its nodes remain frozen. Tests confirmed: callback fires once before the first node and once per boundary (call count/order with a spy), the `None` default leaves terminal `task_context` unchanged, and a mid-run `model_dump(mode="json")` snapshot contains the expected mix of `SUCCESS` and `PENDING` entries. Review passed on the first attempt with no blocking issues. Next: Task 4 — Worker wires persistence at each boundary (Phase 1d).

```
e009aa9 docs: update docs for incremental-execution-observability-task3
b296bd4 feat: implement incremental-execution-observability-task3
b4bf700 chore: init worktree incremental-execution-observability-task3
```

---

## 2026-06-20 (task 2 — framework stamps the envelope in node_context)

Task 2 extended `Workflow.node_context` in `app/core/workflow.py` to stamp the per-node `NodeRun` envelope as execution flows through the DAG. On node entry, the framework sets the node's `NodeRun` to `RUNNING` with an ISO-8601 UTC `started_at` timestamp; on clean exit it records `SUCCESS` and `completed_at`; in the exception branch it records `FAILED` with `error` (str of the exception) and `completed_at` before re-raising. The `TaskContext` is threaded through from `run()` — already in scope at the call site — so no node was edited, keeping `customer_care` fully frozen. Tests confirmed the `PENDING → RUNNING → SUCCESS` happy-path transition, the `FAILED` path with non-null `error` and exception propagation, and that existing tests are unaffected. Review passed on the first attempt with no blocking issues. Next: Task 3 — Injected progress callback on Workflow.run() (Phase 1c).

```
18b7de7 docs: update docs for incremental-execution-observability-task2
03d35e1 feat: implement incremental-execution-observability-task2
498aadd chore: init worktree incremental-execution-observability-task2
```

---

## 2026-06-20 (task 1 — status/timing envelope on TaskContext)

Task 1 implemented the foundational observability data model for incremental execution tracking. Added `NodeStatus(StrEnum)` with `PENDING`/`RUNNING`/`SUCCESS`/`FAILED` values, `NodeRun(BaseModel)` capturing `status`, `started_at`, `completed_at`, `error`, and `usage` fields, and a `node_runs: dict[str, NodeRun]` field on `TaskContext` — all in `app/core/task.py`. The implementation is purely additive: existing `nodes` dict and `get_node_output()` semantics are untouched, and `customer_care` was not modified. Tests confirmed `model_dump(mode="json")` round-trips the new field correctly with enum values serializing to strings. Review passed on the first attempt with no blocking issues. Next: Task 2 — Framework stamps the envelope in node_context (Phase 1b).

```
4ece897 docs: update docs for incremental-execution-observability-task1
6aef302 feat: implement incremental-execution-observability-task1
152ba04 chore: init worktree incremental-execution-observability-task1
```

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
