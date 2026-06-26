---
type: Handoff
created: 2026-06-25
---

# Handoff — frontmatter specs shipped; Wave 0 Block B next

> **For the next agent:** Read this immediately after `/prime`. Delete this file once consumed.

## What we're doing and why

We are executing the Bastion program's **Wave 0** demand-first work for this repo (the Engine +
Python Brain). Two supporting-infrastructure specs — `frontmatter-indexer-enrich` (Block B
indexer enrichment) and `frontmatter-retrieval-filters` (Block C metadata filters) — were
completed this session via `/sdlc-run`. Both are fully shipped and on `main`. The pipeline
infrastructure is now ready to populate the Brain's vector store with OKF-enriched frontmatter
and to scope brain-corpus Q&A by `layer`/`project`/`status`. The next operator step is to
actually **run `index_brain.py`** to populate the store and confirm `corpus="brain"` Q&A works
end-to-end. After that, `Block O` widens the corpus to all sub-repo `planning/` + `CLAUDE.md`
files.

## Completed this session

- **`frontmatter-indexer-enrich`** shipped (commits `d417a07` → `c61ff5c`):
  - 6 OKF columns (`doc_id`, `layer`, `project`, `status`, `keywords`, `related`) + GIN/btree
    indexes on `BrainDocument` via Alembic migration `d1e2f3a4b5c6`
  - `parse_document()`, `normalize_metadata()`, `build_context_prefix()` in `scripts/index_brain.py`
  - 32 new tests; 746 pass; pylint 10.00/10; review PASS in 1 attempt
  - Docs patched: `docs/brain-rag.md` (column table), `docs/scripts.md` (frontmatter subsection)

- **`frontmatter-retrieval-filters`** shipped (commits `e8678a1` → `e8bd767`):
  - `_apply_metadata_filters` helper; `filters: dict | None` on `DocumentQAEventSchema`
  - `_CORPUS_CONFIG["brain"]` extended with `keyword_extra_fields` + `filter_fields`
  - `keywords` ARRAY column ORed into brain-corpus keyword stage
  - `pyproject.toml` raised `max-args = 6` to accommodate new `retrieve()` signature (amendment logged)
  - 9 new tests; 755 pass; pylint 10.00/10; review PASS in 1 attempt
  - Docs patched: `docs/api-reference.md` (filters field, `_apply_metadata_filters`, test count)

- **`/close-out` doc sweep** patched two more stale docs:
  - `docs/workflows.md` — added `filters` row to DOCUMENT_QA payload table
  - `docs/brain-rag.md` — added filters usage subsection + brain `keywords` OR-in note

## Remaining work

1. **Run `index_brain.py`** (operator step — not a spec):
   ```bash
   python scripts/index_brain.py --dry-run   # verify corpus list
   python scripts/index_brain.py             # populate the vector store
   ```
   Then confirm `corpus="brain"` Q&A returns grounded answers from the enriched store.

2. **Block O** — widen the index corpus to all sub-repo `planning/` + `CLAUDE.md` files
   (per-repo corpora). Next spec to generate from `master-plan.md` → Block O.

3. **Block J** — brain freshness loop (auto-reindex on commit via git hook). Wave 0, after B+O.

4. **NEEDS_REVIEW: `docs/app-architecture-overview.md`** — three stale entries flagged by the
   document agent during `/sdlc-run` and confirmed by `/update-docs`. Do NOT auto-patch; human
   review needed before editing:
   - **Line 163** (BrainDocument status entry): missing 6 new OKF columns and migration
     `d1e2f3a4b5c6`; current text only mentions `Vector(1024)` + `ARRAY(String)` workflow_patterns.
   - **Line 249** (Project D Task 3 row): says "22 tests"; doesn't mention `filters` kwarg,
     `_apply_metadata_filters`, or `keywords` OR-in.
   - **Line 250** (Project D Task 4 row): `DocumentQAEventSchema` field list missing `filters`.

5. **Block B private face** (Tailscale) — remaining: Pixel tablet/phone, orchestration API
   binding. Separate from this spec track; tracked in `planning/status.md` Block B.

## Open questions / choices

- Whether to record the OKF vocabulary constants sync (`_VALID_LAYERS`/`_VALID_PROJECTS`/`_VALID_STATUSES`
  in `scripts/index_brain.py`) as a decision in `planning/decisions/` — deferred per wrap-up; only
  needed if the sync mechanism is ever formalized beyond the current warning-based approach.
- `docs/app-architecture-overview.md` NEEDS_REVIEW: decide how granular the frontmatter and
  filters entries should be in that dense timeline doc before editing it.

## Context the next agent needs

- The two net-new-lint baseline JSON files (`planning/frontmatter-indexer-enrich/sdlc/reports/net-new-lint-baseline.json`
  and `planning/frontmatter-retrieval-filters/sdlc/reports/net-new-lint-baseline.json`) are
  generated artifacts from the SDLC pipeline; they are untracked and benign — do not commit them.
- The Alembic migration `d1e2f3a4b5c6` must be applied (`alembic upgrade head`) before
  `index_brain.py` will write to the new OKF columns. The migration chains off `c4d5e6f7a8b9`.
- `corpus="brain"` queries on `DocumentQAEventSchema` now accept `filters` dict with keys
  `"layer"` (array overlap), `"project"` (scalar `==`), `"status"` (scalar `==`).
- The `pyproject.toml` amendment (raised `max-args = 6`) is intentional and covered by tests.

## First command after `/prime`

`python scripts/index_brain.py --dry-run`
