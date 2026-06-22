---
type: Backlog
title: Project A (content_pipeline) — follow-ups
description: Deferred test hardening + carried-over reuse items found after Project A shipped. Pick up before or alongside Project B.
---

# Project A — Follow-ups

*Project A (`content_pipeline`) shipped DONE on 2026-06-20 (8/8 tasks, 295 tests green).
These are small, deferred items found in a post-ship coverage audit and a cross-check
against the site reuse spec. None block Project B; do them when convenient.*

---

## 1. Two deferred tests (from the 2026-06-20 coverage audit)

Coverage is otherwise strong; these are the two genuine gaps.

- [x] **`_is_youtube_url` spoof/subdomain negative cases.** *(Done 2026-06-21.)*
  **Where:** `tests/workflows/content_pipeline/test_fetch_nodes.py`, in the *SourceRouterNode routing* section.
  **What:** Add parametrized cases for the `host.endswith("." + h)` branch in
  `app/workflows/content_pipeline_workflow_nodes/source_router_node.py`:
  - a real subdomain that SHOULD route to transcript (e.g. `https://m.youtube.com/watch?v=x`)
  - a spoof that must NOT route to transcript (e.g. `https://youtube.com.evil.com/x` → falls back to article)
  Today only `www.youtube.com` / `youtu.be` / `youtube.com` happy cases are tested, so the
  anti-spoofing logic is unexercised.

- [x] **Document that `SelfCriticNode.approved` is intentionally inert.** *(Done 2026-06-21.)*
  **Where:** `tests/workflows/test_content_blog_branch.py`, `TestSelfCriticNode` (or a short workflow-level test).
  **What:** The blog branch is a *linear* writer→critic→revise (DAG validated acyclic), so
  `ReviseNode` always runs regardless of `approved`. Add a one-line test asserting that
  `approved=True` does NOT skip revise (i.e. the field has no control-flow effect), so a future
  reader doesn't misread the unused field as a bug. Alternatively, a code comment on the field.
  This matches the planned "one-shot self-critic→revise" design — it is not a loop.

---

## 2. Carried-over items from the site reuse spec

Source: `learn-ai/planning/5.1-reuse-for-project-a/tasks.md` (a cross-repo finding written
*before* Project A was built). Most of it landed; these did not.

- [x] **Transcript corpus as golden test fixtures.** *(Done 2026-06-22.)* Vendored two real
  transcripts into `tests/fixtures/transcripts/` (`software-is-evolving-backwards.txt`,
  `the-new-code-sean-grove-openai.txt`) — copied in, no cross-repo path dependency. Added a
  `load_transcript` fixture in `tests/conftest.py`, and two realistic tests that exercise the
  full untruncated transcript instead of inline strings: `test_fetch_transcript_propagates_full_corpus_text`
  (FetchTranscriptNode stores the large text verbatim) and `test_reads_full_corpus_transcript_as_source`
  (SummarizerNode's `_read_source_text` feeds the whole transcript to the agent). 355 tests pass.

- [x] **Cross-check `SummaryOutput` against the site's summary template.** *(Done 2026-06-22 —
  confirmed intentional, no change.)* The site's `youtube-transcript-summary-template.md` is a
  heavyweight publish-everything artifact; `SummaryOutput` is a deliberately lean personal-digest
  schema. Every durable-value section maps to a field (Executive Summary→`tl_dr`, Key Takeaways→
  `key_insights`, Technical Concepts→`core_concepts`, Questions→`questions_raised`, Tools/Action
  Items/Related→`further_exploration`), and `SummaryOutput` *adds* `connections_to_my_work` (absent
  from the template). The omitted template sections (Timeline Markers, Quotes, Metrics, Do's/Don'ts,
  Tags) are public-summary scaffolding, correctly dropped for a "what's worth remembering" feed.
  Nothing useful was lost.

- [x] **PT-BR translation prompt — DECIDED (Project A item) + BUILT.** *(Done 2026-06-22.)*
  Brandon's call: it belongs to Project A as a dropped MVP item, so it was built. Ported the site's
  `claude-translator.ts` (blog-post content type, Brazil cultural adaptation, mixed technical
  terminology, Markdown preserved) into `app/prompts/translate_ptbr.j2` + `TranslatePtBrNode`
  (`app/workflows/content_pipeline_workflow_nodes/translate_ptbr_node.py`). Wired as the new terminal
  node of the blog branch: `ReviseNode → TranslatePtBrNode`, so it inherits the existing `make_blog`
  gate (digest-only runs skip it). `OutputType`: `translated_title`, `translated_body_markdown`,
  `confidence`, `cultural_notes`, `technical_terms` (nested `TranslatedTerm`). Model
  `claude-opus-4-8` per the standing top-tier-first-run strategy (D19) — flagged as a Project H
  downgrade candidate. Tests added (`tests/workflows/content_pipeline/test_translate_ptbr_node.py`
  + workflow-structure/integration updates); 358 tests pass, ruff clean, pylint 10.00/10. Docs:
  `api-reference.md` + `app-architecture-overview.md`.

---

*When picked up: tick boxes here, run `uv run python -m pytest`, and log via `/log-work`.*
