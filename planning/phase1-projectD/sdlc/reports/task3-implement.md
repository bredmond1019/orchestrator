# Implementation Report — phase1-projectD-task3

**Date:** 2026-06-22
**Plan:** planning/phase1-projectD/tasks.md
**Scope:** Task 3

## What Was Built or Changed

- Created `app/workflows/document_qa_workflow_nodes/__init__.py` — empty package init.
- Created `app/workflows/document_qa_workflow_nodes/retrieve_chunks_node.py` — `RetrieveChunksNode` with two-stage hybrid retrieval: semantic pgvector cosine-distance (Stage 1, top-20 candidates), ILIKE keyword re-rank scoped to those candidates (Stage 2), and additive score fusion with section-title 2x weight and NaN-safe sorting. Corpus dispatch map (`_CORPUS_CONFIG`) covers `"content"` (ContentChunk) and `"brain"` (BrainDocument). DB calls isolated in `_semantic_search` and `_keyword_search` (mockable seams); `_fuse_and_rank` is pure.
- Created `tests/workflows/test_retrieve_chunks_node.py` — 22 tests covering: score ordering, keyword boost, section-title 2x weight, threshold filtering, top-k, NaN safety, corpus="brain" threading, TaskContext seeding, and exact score formula verification.

## Files Created or Modified

| File | Action |
|---|---|
| `app/workflows/document_qa_workflow_nodes/__init__.py` | created |
| `app/workflows/document_qa_workflow_nodes/retrieve_chunks_node.py` | created |
| `tests/workflows/test_retrieve_chunks_node.py` | created |

## Validation Output

**Commands run:**
```
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
uv run python -m pytest tests/workflows/test_retrieve_chunks_node.py -q
```
**Result:** PASSED

## Decisions and Trade-offs

- **`_row_to_candidate` module-level helper**: extracted from `_semantic_search` to reduce its local variable count below pylint's limit of 15.
- **`sqlalchemy.or_` import**: ruff (without a `known-first-party` setting) sorted this alongside local imports; this is acceptable since ruff found no errors after its own `--fix` pass.
- **NaN guard**: filtered out before scoring (rather than sorting last) to exactly match the Rust `total_cmp` guard semantics — a NaN distance is treated as an invalid result, not just a low-score one.
- **`_fuse_and_rank` is pure**: no DB calls inside this function; all DB work is in the two mockable seams. This makes the scoring logic unit-testable with zero mocking overhead.
- **`id` preserved in output**: the output dicts from `_fuse_and_rank` include `"id"` to allow downstream tests to assert ranking by candidate identity. This is not leaked to the public API (callers use `content`/`section_title`/`score`/`source`).

## Follow-up Work

- Task 4 imports `RetrieveChunksNode` and wires it into the `DocumentQAWorkflow` DAG.
- `_semantic_search` and `_keyword_search` execute live SQL (pgvector + ILIKE); the two-stage SQL logic is validated at integration time, not in unit tests (unit tests mock these methods). This gap is documented here and in the breakdown notes.
- Project F will reuse `RetrieveChunksNode` verbatim and add a `learning_artifacts` corpus by adding one entry to `_CORPUS_CONFIG`.

## git diff --stat

```
 app/workflows/document_qa_workflow_nodes/__init__.py    |   0 +
 app/workflows/document_qa_workflow_nodes/retrieve_chunks_node.py | 207 +++++
 tests/workflows/test_retrieve_chunks_node.py           | 315 +++++++++++++++++
 3 files changed, 522 insertions(+)
```
