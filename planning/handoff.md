---
type: Handoff
created: 2026-06-26
---

# Handoff — brain-rag-improvements Blocks C + D done; E + F next

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why

We are executing the **brain-rag-improvements** initiative
(`agentic-portfolio/planning/brain-rag-improvements/plan.md`) — a pre-`--rebuild` overhaul
of the brain RAG stack to fix corpus gaps, vocabulary mismatches, and weak keyword search
before paying the Voyage embedding cost. **Blocks C and D are now complete.** The DB has the
new columns, the GIN FTS index, and the HNSW ANN index. Next are **Block E** (`index_brain.py`
corpus/vocab/column-population fixes) and **Block F** (`retrieve_chunks_node.py` graded FTS
retrieval rewrite).

## Completed this session

- **Block C — Alembic migration** (`app/alembic/versions/e2f3a4b5c6d7_brain_documents_fts_ann_and_metadata_columns.py`):
  - Added `is_section_title` (boolean NOT NULL default false), `title` (varchar 512),
    `description` (text) columns
  - Added `content_tsv` as a Postgres GENERATED ALWAYS STORED tsvector with weighted FTS:
    title+keywords at weight A, description at B, content at C
  - Added GIN index `ix_brain_documents_content_tsv` on `content_tsv`
  - Added HNSW index `ix_brain_documents_embedding_hnsw` on `embedding` (cosine ops)
  - **Key implementation fix:** `array_to_string(keywords, ' ')` is STABLE not IMMUTABLE in
    Postgres, so it is rejected in generated columns. Replaced with `array_to_tsvector(keywords)`
    (which IS IMMUTABLE). Trade-off: keywords indexed as exact tokens, no stemming — correct
    for the controlled OKF vocabulary (`'brain'`, `'engine'`, etc.). This deviates from the
    plan's snippet but is equivalent or better for this use case.
  - Down/up/down cycle verified clean
  - `alembic upgrade head` applied against live DB — migration is at head

- **Block D — BrainDocument model** (`app/database/brain_document.py`):
  - Added `Boolean`, `FetchedValue` to SQLAlchemy imports; `TSVECTOR` to dialects
  - Added `is_section_title` (Boolean, default False), `title` (String 512),
    `description` (Text), and `content_tsv` (TSVECTOR, FetchedValue — read-only, never written
    by the indexer)

- **Gate: 760 passed, 8 skipped; ruff clean; pylint 10.00/10**

## Remaining work

1. **Block E** (`scripts/index_brain.py`) — fix CORPUS list, case-normalize + fix vocab sets,
   add `_is_header_only_chunk` helper, populate new columns at write time. Rated Opus in the
   plan (the `is_section_title` correctness guardrail is the expensive-mistake blocker).
2. **Block F** (`app/workflows/document_qa_workflow_nodes/retrieve_chunks_node.py`) — update
   `_CORPUS_CONFIG["brain"]` with `tsv_field`, rewrite `_keyword_search` to graded FTS
   (dict[id→rank] shape for brain corpus), update `_fuse_and_rank` for graded fusion, add
   explicit `include_archived: bool = False` to `DocumentQAEventSchema`, enrich returned dicts
   with `file_path`/`doc_id`/`title`. Rated Opus.
3. **Block G** (tests) — covers all new behavior in C–F; only after E + F land.
4. **Block H** (`--rebuild` + verification) — execution against live DB; gate before running.
5. **Blocks A + B** (brain repo) — doc relocation + commit hook. Independent; can run
   in parallel or after orchestrator work.

## Open questions / choices

- **`array_to_tsvector` vs `array_to_string` deviation:** The plan called for
  `array_to_string(keywords, ' ')` + `to_tsvector` so keywords get stemmed. This was
  impossible (STABLE not IMMUTABLE). `array_to_tsvector` is the correct substitute —
  keywords are OKF controlled vocabulary, so exact token matching is better than stemming.
  Block F's `_keyword_search` should use `plainto_tsquery` for prose (title/description/content
  FTS) while the generated column already handles keywords as exact tokens. **No action needed
  — the substitution is correct by design.**
- **Block F `_keyword_search` FTS path:** The retrieval node will call
  `func.plainto_tsquery('english', query)` against `content_tsv`. Since keywords are
  stored as exact tokens (e.g., `'brain'`, `'engine'`), a query like `"brain rag"` will
  match docs with keyword `'brain'` at weight A — working as designed.

## Context the next agent needs

- **The new migration is already applied** — the DB is at head `e2f3a4b5c6d7`. Do NOT run
  `alembic upgrade head` again before Block E/F (it's already done). Run `alembic current` to
  confirm if in doubt.
- **`content_tsv` is a generated column** — the indexer must NEVER write it (no `content_tsv`
  in the BrainDocument constructor in `index_brain.py`). It is also not settable via
  SQLAlchemy (`FetchedValue` makes it read-only on the model side).
- **Block E plan ref:** `agentic-portfolio/planning/brain-rag-improvements/plan.md` → Block E.
  Sub-changes: E1 (fix CORPUS list — note `docs/bastion` entry only works after Block A),
  E2 (case-normalize vocab sets), E3 (no-op — FTS supersedes stop-word list), E4
  (`_is_header_only_chunk` on the header-stripped body, not the combined chunk text).
- **Block F plan ref:** same file → Block F. The `_keyword_search` return shape changes to
  `dict[id→float]` for brain corpus (graded by `ts_rank`) vs `set[id]` for legacy content
  corpus. `_fuse_and_rank` must branch on `isinstance(kw, dict)`.
- **Test count baseline:** 760 passed, 8 skipped (up from 755 before this session).
- **Previous handoff consumed** — the prior `planning/handoff.md` referenced
  `frontmatter-indexer-enrich` + `frontmatter-retrieval-filters` as the just-completed work;
  those are done and in the Decisions & Deviations log in `planning/status.md`.

## First command after `/prime`

`uv run python -m alembic current`

(Confirm migration is at `e2f3a4b5c6d7 (head)`, then proceed to Block E.)
