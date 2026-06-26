---
type: Guide
title: Brain RAG
description: How the company brain corpus is indexed and queried — BrainDocument model, index_brain.py, and retrieval via DOCUMENT_QA.
---

# Brain RAG

The brain RAG layer lets you query the `agentic-portfolio` knowledge base (decisions, projects, career docs, brand notes, business pipeline) using the same `DOCUMENT_QA` workflow that answers questions over any ingested document. It's a personal semantic search over everything written in the company brain.

In the Bastion program, this is the **Python half of the Brain layer** — semantic retrieval over the company-brain corpus. The structural half (graph queries over the OKF `[[link]]` structure) lives in the Console (`bastion`, Rust). See `planning/master-plan.md` → "Bastion Program Blocks" and `planning/decisions/D36-bastion-engine-brain-role.md`.

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
- **Layer 3 (planned — Block R):** Brain-as-MCP-server exposing brain retrieval to external clients (the Python server half of the MCP split; the Console vendors the Rust client). Was scoped as "Project F" before the Bastion reframe; see D36.

The indexer's own roadmap sits in the demand-first program blocks: **Block B** populates the vector store over the brain corpus, **Block O** widens it to every sub-repo's `planning/` + `CLAUDE.md`, and **Block J** makes re-indexing automatic on commit (today it is the manual CLI below).

---

## The `BrainDocument` model

Each row is one section-level chunk of a brain document. The brain is indexed by H2/H3 section header so each chunk has a named section and maps to a coherent unit of content.

| Column | Type | What it holds |
|---|---|---|
| `id` | UUID | Row identifier |
| `file_path` | string | Relative path from brain root (e.g. `docs/career.md`) |
| `doc_type` | string | Corpus category: `decision`, `project`, `career`, `brand`, `business`, `content`, `diagnostic`, `memory` |
| `section` | string | H2/H3 header this chunk falls under |
| `content` | text | Raw chunk text (up to ~500 tokens) — YAML frontmatter block is stripped before storage |
| `embedding` | vector(1024) | Voyage AI `voyage-2` embedding |
| `indexed_at` | datetime | When this chunk was last indexed |
| `client_slug` | string (nullable) | Diagnostic client id — only for `doc_type="diagnostic"` |
| `workflow_patterns` | ARRAY(string) (nullable) | Pattern tags from diagnostic docs |
| `doc_id` | string (nullable) | OKF `id` frontmatter field; falls back to filename stem when absent |
| `layer` | ARRAY(string) (nullable) | OKF `layer` frontmatter field (e.g. `["Brain", "Engine"]`); bare strings coerced to list |
| `project` | string (nullable) | OKF `project` frontmatter field (controlled vocabulary; out-of-vocab values warn but are stored) |
| `status` | string (nullable) | OKF `status` frontmatter field (e.g. `active`, `draft`, `archived`) |
| `keywords` | ARRAY(string) (nullable) | OKF `keywords` frontmatter field; used in GIN-indexed search |
| `related` | ARRAY(string) (nullable) | OKF `related` frontmatter field — `[[wikilink]]` targets for graph traversal |

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

The script defaults to the parent of the orchestration repo (the brain root), resolved from the script's own location — so it works from any working directory. If your brain repo is elsewhere:

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

The retrieval runs the same two-stage hybrid search as regular document Q&A: semantic similarity (Voyage embedding) + keyword ILIKE re-rank, with 2× weight on section-title matches. The brain corpus also ORs the `keywords` column into the keyword stage, so tagged documents surface even when the section body doesn't match.

**Scoping retrieval with filters** — pass an optional `filters` dict to restrict Stage 1 semantic search to documents matching the specified OKF metadata fields:

```bash
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "DOCUMENT_QA",
    "data": {
      "doc_id": "00000000-0000-0000-0000-000000000000",
      "question": "What is the current contracting rate strategy?",
      "corpus": "brain",
      "filters": {"project": "python-orchestration", "status": "active"}
    }
  }'
```

Supported filter keys: `"layer"` (array overlap — matches if the document's layer list contains the value), `"project"` (scalar `==`), `"status"` (scalar `==`). Unknown keys and `null` values are silently skipped.

---

## When to re-index

Re-run `index_brain.py` after:
- Adding or updating any document in the brain's `docs/`, `planning/the-diagnostic/`, or `memory/` directories
- Adding a new memory entry
- Publishing a decision (`docs/decisions/`)

The incremental mode is fast — it compares `indexed_at` against file modification time and skips unchanged docs. Only updated or new sections get re-embedded.

### Deleted and renamed files (orphan rows)

The incremental upsert keys on `file_path + section`, so it only ever *adds or replaces* rows for files it walks. When a file is **deleted or renamed away**, the indexer never revisits the old path and its rows linger as stale retrieval hits. Two ways to clean them up:

- **Surgical:** `python scripts/index_brain.py --prune-paths <old paths…>` deletes just those files' rows — no re-embedding, no API call. Diagnostic rows (`client_slug` set) are preserved.
- **Automatic:** the brain repo ships a `post-commit` git hook (tracked in `hooks/`, enabled via `git config core.hooksPath hooks`) that runs `--prune-paths` for exactly the files a commit deleted or renamed. It is a no-op on ordinary edits and catches renames whether or not `git mv` was used. See `hooks/README.md` in the brain repo.

Note this is **file-level** cleanup only. A section renamed or removed *inside* a still-existing file leaves an orphan row that neither incremental indexing nor `--prune-paths` removes — run `--rebuild` after structural edits within files.

---

## Notes

- The `brain_documents` table uses PostgreSQL `ARRAY` for `workflow_patterns`, which is not compatible with SQLite. Tests that touch this model are marked `@pytest.mark.skip(reason="requires PostgreSQL")` — this is intentional (see decision D31).
- Embeddings use `voyage-2` (1024 dimensions). If you switch models, run `--rebuild` to avoid mixing vector spaces.
- Diagnostic rows (`doc_type="diagnostic"`) are protected from `--rebuild` deletion — they carry client-specific pattern data that is expensive to regenerate.
