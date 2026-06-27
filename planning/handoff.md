---
type: Handoff
title: Handoff — brain-rag-improvements reviewed PASS; Block H local-embedding swap
description: Handoff note for the next agent — brain-rag-improvements Blocks C–G are PASS; Block H is pending a local mxbai-embed-large embedding swap before the final --rebuild.
doc_id: handoff
layer: [engine, brain]
project: orchestrator
status: active
keywords: [handoff, brain-rag-improvements, Block H, local embeddings, mxbai]
related: [status, master-plan]
created: 2026-06-26
---

# Handoff — brain-rag-improvements reviewed PASS; final sweep before the live --rebuild

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.
> **Your job:** one last independent sweep of the brain-rag-improvements code (Blocks C–G + the
> pre-rebuild sweep), then drive **Block H** — the live, paid, one-shot `index_brain.py --rebuild`
> against the Mac Mini Postgres. This is the irreversible step the whole initiative exists to get
> right, so verify before you spend.

## What we're doing and why

We are finishing the **brain-rag-improvements** initiative — a pre-`--rebuild` overhaul of the
brain RAG stack so the one-time Voyage embedding cost is paid once, over the correct corpus, with
clean metadata and fast hybrid retrieval. Full block contract:
`../planning/brain-rag-improvements/plan.md` (Revision 2). Concise status of everything done:
`../planning/brain-rag-improvements/implementation-report.md` (read this — it is the map).
Blocks **C/D** (FTS/ANN migration + model columns, commit `61d8559`) and **E/F/G** (indexer,
retrieval, tests, commit `3c862d3`) are all on `main`. This session **reviewed E/F/G → PASS** and
applied a **final pre-rebuild sweep** (commit `3b96cfa`).

## Completed this session

- **Review of Blocks E/F/G → PASS.** Verified the three high-risk areas: E4 header-strip
  (`_is_header_only_chunk` measures the header-stripped body; guardrail test asserts a True/False
  mix), F3 dual-shape `_keyword_search` (graded `dict[id→ts_rank]` for brain / `set` for content,
  incl. empty shapes), F2 NULL-safe default-on archived filter via the explicit `include_archived`
  schema field. Regression-safe: `AssembleContextNode` ignores the new provenance keys; the
  `content` corpus path is untouched.
- **Final sweep — `scripts/index_brain.py`** (commit `3b96cfa`):
  - `zip(final_chunks, embeddings, strict=True)` — a Voyage count mismatch now fails loudly instead
    of silently truncating into **misaligned chunk↔embedding rows**.
  - Added **`--limit N`** flag (+ test in `tests/test_index_brain.py::TestLimit`) — makes the Block H
    pre-rebuild write-path check runnable: `--rebuild --limit 3`.
  - Removed dead `chunk_texts` variable. `scripts/index_brain.py` is now ruff-clean.
- **Report** written + index updated in the brain repo (commit `cc69a8b` there):
  `planning/brain-rag-improvements/implementation-report.md`.
- **Gate (current):** 791 passed / 8 skipped · ruff clean (`app/` + `scripts/`) · pylint 10.00/10.
- **Confirmed:** `alembic heads` → single head `e2f3a4b5c6d7` (no merge migration needed);
  `BrainDocument.content_tsv` mapped read-only via `FetchedValue()`.

## Remaining work

1. **One independent review pass** (your call how deep — the work is committed and green). If you
   concur, proceed to Block H.
2. **Block H — the live `--rebuild`** (paid, one-shot, against Mac Mini Postgres). Order:
   - `cd app && uv run python -m alembic upgrade head`  (single head `e2f3a4b5c6d7`)
   - `uv run python scripts/index_brain.py --dry-run`  (expect ~109 files; spot-check paths)
   - **Pre-rebuild write-path check:** `uv run python scripts/index_brain.py --rebuild --limit 3`,
     then inspect the DB — assert `is_section_title` is a **True/False mix** (NOT uniformly True)
     and `title`/`description` populate. This is the go/no-go gate before the full spend.
   - Full pass: `uv run python scripts/index_brain.py --rebuild`
   - Smoke queries (plan §Block H): D20 data-contract Q, `project: bastion` filter, CLAUDE.md
     standing-rules Q, archived include/exclude, FTS title-rank, HNSW `EXPLAIN`.
3. **Brain-side blocks (separate repo, non-blocking):** Block A (relocate to `docs/bastion/`) —
   dry-run shows `docs/bastion/` resolves, so **likely already done**; verify. Block B
   (`.brain-moves-pending` commit-hook log) — status unknown; check `../hooks/`.

## Open questions / choices

- **`_KW_WEIGHT = 5.0`** in `retrieve_chunks_node.py` is a reasoned default, not a tuned value
  (ts_rank runs small, ~<0.1). The plan defers final tuning to Block H smoke queries. Tune only if
  the smoke tests show keyword hits over/under-weighted; otherwise leave it.
- Otherwise clear to proceed — the approach is settled per the plan (Revision 2) and this session's
  review.

## Context the next agent needs

- **`content_tsv` is a generated column** — the indexer must NEVER write it (it doesn't; verified).
  A regression here fails at INSERT against real Postgres, not in the SQLite/mock tests.
- The `--rebuild` deletes only non-diagnostic rows (`client_slug IS NULL`); diagnostic rows are
  protected. `--prune-paths` and incremental skip are intact.
- Block H runs against the **Mac Mini Postgres**, reachable over Tailscale (`brandons-mac-mini`,
  100.104.113.100). Needs `VOYAGE_API_KEY` set. The local DB is already at head `e2f3a4b5c6d7`.
- Quick re-validation before the run: `uv run python -m pytest tests/test_index_brain.py
  tests/workflows/test_retrieve_chunks_node.py -q`.

## First command after `/prime`

`uv run python -m pytest -q && cd app && uv run python -m alembic heads`
