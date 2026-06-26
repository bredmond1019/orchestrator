---
type: Handoff
created: 2026-06-26
---

# Handoff — brain-rag-improvements E+F+G done; review, then Block H

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.
> **Your job this session is to REVIEW** the work below (Blocks E + F + G + doc patches), not to
> extend it. If it passes review, the next step is Block H (the live `--rebuild`).

## What we're doing and why

We are executing the **brain-rag-improvements** initiative — a pre-`--rebuild` overhaul of the
brain RAG stack so the one-time Voyage embedding cost is paid once, over the correct corpus, with
clean metadata and fast hybrid retrieval. The full block contract lives in the brain repo at
`../planning/brain-rag-improvements/plan.md` (Revision 2, post-Opus review). Blocks **C** (Alembic
migration: `is_section_title`/`title`/`description` + generated `content_tsv` FTS column + GIN +
HNSW indexes) and **D** (BrainDocument model columns) landed in a parallel session
(commit `61d8559`). This session implemented Blocks **E** (indexer), **F** (retrieval node), and
**G** (tests), plus the close-out doc patches. All gates are green; `/commit` at the end of this
handoff stages the work — check `git log` for the commit.

## Completed this session

- **Block E — `scripts/index_brain.py`:**
  - E1: rewrote `CORPUS` — dropped broken `planning/the-diagnostic` + out-of-repo `memory/`/`MEMORY.md`;
    added `docs/diagnostic`, `CLAUDE.md`, `README.md`, `docs/index.md`, `docs/progress.md`,
    `docs/okf-frontmatter.md`, `docs/infrastructure.md`, `docs/integrations`, `docs/bastion`,
    `planning/bastion-product`, `planning/bastion-ui`, `planning/status.md`, `planning/archived`.
  - E2: fixed vocab sets (`surfaces`→`surface`; added `infra`/`business`/`content`/`meta` layers,
    `brain`/`bella`/`amistad` projects, `superseded` status) **and** case-normalized
    layer/project/status in `normalize_metadata` (lowercased for both check + storage).
  - E3: no-op (no `_STOP_WORDS` existed in this file; FTS supersedes it).
  - E4: added `_is_header_only_chunk()` (measures the **header-stripped** body — the blocker) and
    populated `is_section_title`/`title`/`description` in the upsert; never writes `content_tsv`.
- **Block F — `retrieve_chunks_node.py` + `document_qa_schema.py`:**
  - F1: `_CORPUS_CONFIG["brain"]` — wired `is_section_title_field`, added `tsv_field` +
    `default_status_exclude="archived"`, removed superseded ILIKE `keyword_extra_fields`. Added
    module-scope `_KW_WEIGHT = 5.0` / `_KW_BOOST = 1.0`.
  - F2: explicit `include_archived: bool = False` on `DocumentQAEventSchema`; threaded
    `process → retrieve → _semantic_search`; NULL-safe default archived filter.
  - F3: `_keyword_search` now dispatches to `_keyword_search_fts` (graded `dict[id→ts_rank]`, brain)
    or `_keyword_search_ilike` (legacy `set`, content). Split into helpers to hold pylint 10/10.
  - F4/F5: enriched candidates + results with `file_path`/`doc_id`/`title`; graded fusion in
    `_fuse_and_rank` (dict → `_KW_WEIGHT × ts_rank`; set → flat `_KW_BOOST`).
- **Block G — tests:** +35 tests (755 → **790 passed**, 8 skipped). New: header-strip + guardrail,
  vocab case-normalization, CORPUS membership, column population, graded fusion, provenance,
  archived exclusion, FTS/legacy keyword-search shapes. Updated stale tests (`test_diagnostic_file`
  re-pointed to `docs/diagnostic`; memory doc-type tests now assert the `content` fallback;
  `_semantic_search` call assertion gained `include_archived=False`).
- **`pyproject.toml`:** bumped pylint `max-args 6→7` + added `max-positional-arguments=6` (with a
  logged rationale comment) — the retrieve contract now legitimately carries
  query/corpus/k/threshold/filters/include_archived. Continues the precedent the
  frontmatter-retrieval-filters spec set.
- **Doc patches:** `docs/api-reference.md` (BrainDocument columns table now lists all OKF + new
  columns + migrations `d1e2f3a4b5c6`/`e2f3a4b5c6d7`; rewrote Stage-2 / `_keyword_search` /
  `_fuse_and_rank` / `retrieve` / `DocumentQAEventSchema` sections), `docs/brain-rag.md` (FTS +
  `include_archived` + memory-out-of-corpus note + fixed stale re-index paths),
  `docs/workflows.md` (FTS note + `include_archived` payload field).
- **Validation:** `uv run python -m pytest` → 790 passed / 8 skipped; `ruff check app/` clean;
  `pylint app/` **10.00/10**. Ran a real `--dry-run` against the live brain repo: **109 files**
  resolve, **zero vocab warnings**, **zero broken paths**, all by-design exclusions absent.

## Remaining work

1. **REVIEW this session's work** (your primary task) — verify Blocks E/F/G against
   `../planning/brain-rag-improvements/plan.md` acceptance criteria. Suggested focus areas:
   - **E4 blocker:** `_is_header_only_chunk` measures the header-stripped body, and the guardrail
     test asserts the flag is a *mix*, never uniformly True. This is the single most expensive
     thing to get wrong (it wastes the Voyage spend). Confirm the logic + test.
   - **F3 dual-shape contract:** `_keyword_search` returns `dict` for brain / `set` for content,
     and `_fuse_and_rank` branches on `isinstance(..., dict)`. Confirm both shapes + the empty-
     candidate early-return shapes are right.
   - **F2 archived filter:** NULL-safe (`status != "archived" OR status IS NULL`), default-on,
     overridable via the explicit schema field (not a `filters` key).
   - Whether `_KW_WEIGHT = 5.0` is a sane starting point (it is explicitly a Block H tuning target).
2. **Block H** (after review passes) — the live, paid, one-shot `--rebuild`. Needs the Mac Mini
   Postgres. Steps in the plan: `alembic heads`/`current` → `alembic upgrade head` →
   `--dry-run` → **pre-rebuild write-path check on a 2–3 file subset** (assert `is_section_title`
   is a True/False mix and `title`/`description` populate) → `--rebuild` → smoke tests.
3. **Blocks A + B (brain repo side):** Block A (relocate `architecture.md`/`ownership.md` to
   `docs/bastion/`) is **already done** — the dry-run confirmed `docs/bastion/` resolves. Block B
   (commit hook `.brain-moves-pending` log) status unknown; check the brain repo.

## Open questions / choices

- **`_KW_WEIGHT = 5.0`** is a reasoned default, not a tuned value. ts_rank values run small
  (~<0.1), so this scales a strong keyword hit to roughly parity with the semantic + section-title
  contributions. The plan defers final tuning to Block H against live smoke queries. Flag if review
  wants it tuned earlier.
- The schema class **docstring** in `document_qa_schema.py` lists fields up to `corpus` and does not
  enumerate `filters`/`include_archived` (the `Field(description=...)` strings document them). Left
  as-is to match the existing pattern (it already omitted `filters`). Trivial to expand if desired.

## Context the next agent needs

- **C + D are committed (`61d8559`); E/F/G/docs are this session's diff.** The model columns the
  E/F code depends on are already on `main` via that commit — tests run green with nothing pending
  from a parallel tree.
- The two pre-existing ruff violations in `scripts/index_brain.py` (`chunk_texts` unused at the
  upsert prep; `B905` zip-without-strict) are **pre-existing and outside the enforced gate**
  (`ruff check app/`, not `scripts/`). I deliberately did not touch them. `ruff check scripts/`
  reporting 2 errors is the baseline, not a regression.
- `content_tsv` is a **generated** column — the indexer must never write it; the model maps it
  read-only (`FetchedValue`/`TSVECTOR`). A regression here would fail at INSERT against real PG.
- Migration chain: `c4d5e6f7a8b9` → `d1e2f3a4b5c6` (OKF cols) → `e2f3a4b5c6d7` (FTS/ANN). Single
  head. `e2f3a4b5c6d7` uses `::regconfig` cast + `array_to_tsvector` to satisfy the generated-column
  IMMUTABLE requirement (the plan's original `array_to_string` snippet would have failed — already
  fixed in C).
- For a quick review re-validation: `uv run python -m pytest tests/test_index_brain.py
  tests/workflows/test_retrieve_chunks_node.py -q` (146 pass, 7 skip) and
  `uv run python scripts/index_brain.py --dry-run` (read-only; no DB/embeddings).

## First command after `/prime`

`uv run python -m pytest -q && uv run python -m pylint app/ | grep rated`
