---
type: Handoff
created: 2026-06-22
---

# Handoff — Project A follow-ups closed; Project B is next

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why
This session closed out the last open **Project A (`content_pipeline`) follow-ups** from
`planning/phase1-projectA/follow-ups.md` — small deferred items found after Project A shipped.
All items in that doc are now `[x]`. The one substantive build was the **PT-BR translation
node**: Brandon decided (this session) that PT-BR translation belongs to Project A as a dropped
MVP item, so it was ported from the site's `learn-ai/lib/services/translation/claude-translator.ts`
into a new terminal node on the blog branch. With this, Project A is fully complete and the next
planned product unit is **Phase 1 Project B (Research agent)** — the standing current focus in
`status.md`. Nothing here blocks Project B.

## Completed this session
- **Item 1 — golden corpus fixtures (done):** vendored two real transcripts into
  `tests/fixtures/transcripts/` (`software-is-evolving-backwards.txt`,
  `the-new-code-sean-grove-openai.txt`) — copied in, **no cross-repo path dependency**. Added a
  `load_transcript` fixture in `tests/conftest.py`, and two realistic tests that run against the
  full untruncated transcript: `test_fetch_transcript_propagates_full_corpus_text`
  (`tests/workflows/content_pipeline/test_fetch_nodes.py`) and
  `test_reads_full_corpus_transcript_as_source` (`.../test_summarizer_node.py`).
- **Item 2 — `SummaryOutput` vs site template (done, no code change):** confirmed the lean
  `SummaryOutput` schema is intentional; every durable-value section of the heavyweight
  `youtube-transcript-summary-template.md` maps to a field, and `SummaryOutput` *adds*
  `connections_to_my_work`. Conclusion recorded in `follow-ups.md`.
- **Item 3 — PT-BR translation (DECIDED = Project A item, then BUILT):**
  - New `app/prompts/translate_ptbr.j2` (EN→pt-BR: Brazil cultural adaptation, mixed technical
    terminology, Markdown/code/identifier preservation).
  - New `app/workflows/content_pipeline_workflow_nodes/translate_ptbr_node.py` —
    `TranslatePtBrNode(AgentNode)` + nested `TranslatedTerm`; `OutputType` = `translated_title`,
    `translated_body_markdown`, `confidence` (default 80), `cultural_notes`, `technical_terms`.
    `ModelProvider.ANTHROPIC` / `claude-opus-4-8` (top-tier first run per D19; flagged Project H
    downgrade candidate). Reads `ReviseNode` output via `get_node_output(...)`, runs via
    `run_agent_recorded()`.
  - Wired in `content_pipeline_workflow.py`: `ReviseNode → TranslatePtBrNode` (translate is now the
    **terminal** node); updated the docstring graph. Inherits the existing `make_blog` gate, so
    digest-only runs skip it. DAG still validates (now 10 nodes).
  - Tests: new `tests/workflows/content_pipeline/test_translate_ptbr_node.py`; updated
    `tests/workflows/test_content_pipeline_workflow.py` (node-map, is_router, connection-map,
    integration `_agent_output_for` + `_BLOG_NODES` + a pt-BR output assertion).
  - Docs: `docs/api-reference.md` (new node section + branch header Four→Five + ReviseNode no
    longer terminal) and `docs/app-architecture-overview.md` (new "Project A — follow-up" row).
- **Validation:** **358 tests pass** (was 353: +2 corpus, +3 translate), ruff `app/` clean,
  pylint `app/` **10.00/10**, DAG builds + validates.

## Remaining work
- **Nothing left in `follow-ups.md`** — all items are `[x]`.
- **Next planned unit: Phase 1 Project B (Research agent)** — thin cut first (~50 lines, raw tool
  loop) per `status.md` current focus. Start with `/feature` or `/generate-tasks`. No blocker.
- **Carried from the prior handoff (still open, operator-only, NOT an agent task):** subscription-host
  e2e gates for both Claude-Code provider modes (`CLAUDE_CODE_SDK` + `CLAUDE_CODE_SESSION`) — must run
  on a host with the `claude` CLI logged into the subscription to verify billing. Record findings in
  the respective spec `## Notes`.

## Open questions / choices
- **None blocking.** The PT-BR scope question (the only decision item in the follow-ups) was resolved
  this session — Brandon chose "build it as a Project A item," and it is built and green.

## Context the next agent needs
- **This session did NOT run `/log-work` or `/commit` yet at the time of writing this file** — the
  `/handoff` flow invokes them right after. All Project A follow-up changes are uncommitted in the
  working tree (see `git status`): modified `content_pipeline_workflow.py`, `conftest.py`, the three
  test files, `api-reference.md`, `app-architecture-overview.md`, `follow-ups.md`; untracked
  `prompts/translate_ptbr.j2`, `workflows/.../translate_ptbr_node.py`, `tests/fixtures/`,
  `tests/workflows/content_pipeline/test_translate_ptbr_node.py`.
- **Pre-existing test-tree lint debt is real but out of scope:** ~23 ruff import-sort violations exist
  elsewhere under `tests/`. The harness lints `app/` only (per `planning/harness.json` / CLAUDE.md), so
  they don't fail the gate. I fixed only the files I touched; don't get nerd-sniped into a tree-wide
  ruff sweep unless asked.
- **venv gotcha (unchanged):** a stale `VIRTUAL_ENV=.../orchestration/.venv` is exported in this shell.
  Run `uv run python -m <tool>` **without** `--active` so uv picks the project `.venv`; ruff prints a
  harmless warning about this and still runs against the right env.
- **`TranslatePtBrNode` follows the frozen AgentNode pattern** (mirror of `revise_node.py` /
  `self_critic_node.py`): `# pylint: disable=duplicate-code` is intentional — the AgentConfig
  boilerplate every subclass repeats trips R0801, it is not a refactor target.

## First command after `/prime`
`uv run python -m pytest -q` — confirm the 358-test green baseline, then start Project B with
`/feature` (research agent, thin cut first).
