---
type: Guide
title: Brain RAG
description: How the company brain corpus is indexed and queried — BrainDocument model, index_brain.py, and retrieval via DOCUMENT_QA.
---

# Brain RAG

The brain RAG layer lets you query the `agentic-portfolio` knowledge base (decisions, projects, career docs, brand notes, business pipeline) using the same `DOCUMENT_QA` workflow that answers questions over any ingested document. It's a personal semantic search over everything written in the company brain.

---

## Architecture

```
agentic-portfolio/ markdown files
         │
  scripts/index_brain.py   ← you run this to index / re-index
         │
  BrainDocument rows       ← pgvector table (one row per section chunk)
         │
  RetrieveChunksNode       ← corpus="brain" parameter
  (DOCUMENT_QA workflow)
         │
  AnswerNode               ← grounded answer from brain context
```

There are three layers:
- **Layer 1 (shipped):** `BrainDocument` model + `index_brain.py` CLI — index the corpus
- **Layer 2 (shipped):** `RetrieveChunksNode` `corpus` parameter — query the corpus via `DOCUMENT_QA`
- **Layer 3 (deferred, Project F):** MCP endpoint exposing brain retrieval to external clients

---

## The `BrainDocument` model

Each row is one section-level chunk of a brain document. The brain is indexed by H2/H3 section header so each chunk has a named section and maps to a coherent unit of content.

| Column | Type | What it holds |
|---|---|---|
| `id` | UUID | Row identifier |
| `file_path` | string | Relative path from brain root (e.g. `docs/career.md`) |
| `doc_type` | string | Corpus category: `decision`, `project`, `career`, `brand`, `business`, `content`, `diagnostic`, `memory` |
| `section` | string | H2/H3 header this chunk falls under |
| `content` | text | Raw chunk text (up to ~500 tokens) |
| `embedding` | vector(1024) | Voyage AI `voyage-2` embedding |
| `indexed_at` | datetime | When this chunk was last indexed |
| `client_slug` | string (nullable) | Diagnostic client id — only for `doc_type="diagnostic"` |
| `workflow_patterns` | ARRAY(string) (nullable) | Pattern tags from diagnostic docs |

---

## Indexing the corpus

Run `scripts/index_brain.py` from the repo root:

```bash
# Dry run first — see what would be indexed
python scripts/index_brain.py --dry-run

# First-time index
python scripts/index_brain.py

# After updating brain documents, re-index incrementally
# (skips chunks that are already indexed with the same content)
python scripts/index_brain.py

# Full rebuild — drop all non-diagnostic rows and re-index from scratch
python scripts/index_brain.py --rebuild
```

The script defaults to `../agentic-portfolio` relative to the repo root. If your brain repo is elsewhere:

```bash
python scripts/index_brain.py --brain-path /absolute/path/to/agentic-portfolio
```

**What gets indexed:** see `docs/scripts.md` § index_brain.py for the full corpus list.

**Prerequisites:**
- Postgres running with `brain_documents` table created (`alembic upgrade head`)
- `VOYAGE_API_KEY` set in `app/.env`
- The brain repo exists at the expected path

---

## Querying the brain

Use `DOCUMENT_QA` with `corpus="brain"`. The `doc_id` field is required by the schema but not used for brain corpus queries — pass any valid UUID:

```bash
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "DOCUMENT_QA",
    "data": {
      "doc_id": "00000000-0000-0000-0000-000000000000",
      "question": "What is my current contracting rate strategy?",
      "corpus": "brain"
    }
  }'
```

The retrieval runs the same two-stage hybrid search as regular document Q&A: semantic similarity (Voyage embedding) + keyword ILIKE re-rank, with 2× weight on section-title matches.

---

## When to re-index

Re-run `index_brain.py` after:
- Adding or updating any document in the brain's `docs/`, `planning/the-diagnostic/`, or `memory/` directories
- Adding a new memory entry
- Publishing a decision (`docs/decisions/`)

The incremental mode is fast — it compares `indexed_at` against file modification time and skips unchanged docs. Only updated or new sections get re-embedded.

---

## Notes

- The `brain_documents` table uses PostgreSQL `ARRAY` for `workflow_patterns`, which is not compatible with SQLite. Tests that touch this model are marked `@pytest.mark.skip(reason="requires PostgreSQL")` — this is intentional (see decision D31).
- Embeddings use `voyage-2` (1024 dimensions). If you switch models, run `--rebuild` to avoid mixing vector spaces.
- Diagnostic rows (`doc_type="diagnostic"`) are protected from `--rebuild` deletion — they carry client-specific pattern data that is expensive to regenerate.
