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

- [ ] **Transcript corpus as golden test fixtures.** The spec called for wiring
  `learn-ai/content/youtube-transcripts/*.{json,txt}` as golden fixtures for the Project A
  workflow tests. Current tests use inline mock strings instead. Upgrading `FetchTranscriptNode` /
  `SummarizerNode` tests to run against a couple of real corpus files would make them more
  realistic. Low effort; pairs naturally with item 1 above. (Copy the fixture files into this
  repo's `tests/` tree — do NOT add a cross-repo path dependency.)

- [ ] **Cross-check `SummaryOutput` against the site's summary template.** We built
  `content_summarizer.j2` + `SummaryOutput` independently rather than porting the site's
  `content/summaries/youtube-transcript-summary-template.md`. Worth a 5-minute diff to confirm no
  useful field/section from the proven template was dropped. Likely fine — confirm, don't assume.

- [ ] **DECISION NEEDED (not scheduled): PT-BR translation prompt.** The reuse spec called for
  porting `claude-translator.ts` into `app/prompts/translate_ptbr.j2` + an `AgentNode`. This was
  **not built** — the shipped `content_pipeline` is digest + optional **EN** blog, with no
  translation anywhere. Open question for Brandon: does PT-BR translation belong to Project A
  (a dropped MVP item), or is it a *content-publishing* concern tied to the brand's PT+EN cadence
  that should live elsewhere / later? Resolve the scope question first; only then schedule the port
  (refresh the model id via the `claude-api` skill if/when built). Do not build it on autopilot.

---

*When picked up: tick boxes here, run `uv run python -m pytest`, and log via `/log-work`.*
