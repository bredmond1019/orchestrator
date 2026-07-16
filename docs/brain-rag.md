---
type: Guide
title: Brain RAG
description: How the company brain corpus is indexed and queried — BrainDocument model, index_brain.py, and retrieval via DOCUMENT_QA.
doc_id: brain-rag
layer: [engine, brain]
project: orchestrator
status: active
keywords: [brain RAG, BrainDocument, index_brain, semantic retrieval, DOCUMENT_QA, embeddings, multi-workspace]
related: [app-architecture-overview, D36-bastion-engine-brain-role, D37-local-embeddings-mxbai, workspace-contract]
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
- **Layer 2 (shipped):** `RetrieveChunksNode` `corpus` parameter — query the corpus via `DOCUMENT_QA`, including a structural graph-expansion stage (`BrainEdge` model + `load_brain_edges.py` CLI, OR.G — see below)
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
| `embedding` | vector(1024) | Embedding vector — local Ollama `mxbai-embed-large` by default (see `EmbeddingService`), or Voyage `voyage-2` if `EMBEDDING_PROVIDER=voyage` |
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

### Choosing the corpus

`DOCUMENT_QA` answers questions over **one of two corpora**, selected by the `corpus` field on the event payload. The same workflow and the same two-stage hybrid retrieval serve both — only the table queried changes:

| `corpus` value | Table queried | Model | Populated by | What it holds |
|---|---|---|---|---|
| `"content"` *(default)* | `content_chunks` | `ContentChunk` | the `DOCUMENT_INGEST` workflow | documents you ingest at runtime via the API |
| `"brain"` | `brain_documents` | `BrainDocument` | `scripts/index_brain.py` (this page) | the company-brain markdown corpus |

`corpus` is **optional and defaults to `"content"`** — so a `DOCUMENT_QA` event with no `corpus` field queries ingested documents, *not* the brain. **To query the brain you must explicitly set `"corpus": "brain"`.** The `filters` field (below) applies to the `"brain"` corpus only and is ignored for `"content"`. (Adding a third corpus is a single entry in `RetrieveChunksNode`'s module-level `_CORPUS_CONFIG` dict.)

### Brain query example

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

The retrieval runs two-stage hybrid search: HNSW-indexed semantic similarity (Voyage embedding) + a **graded Postgres full-text re-rank**, with 2× weight on section-title chunks. Unlike the content corpus (which uses a binary ILIKE keyword match), the brain corpus scores keyword relevance with `ts_rank` over a generated `content_tsv` column: a term in a document's `title` or `keywords` (full-text weight `'A'`) outranks the same term buried in body text (weight `'C'`). `plainto_tsquery` strips English stop words and stems terms natively (`"contracts"` matches `"contract"`), so no manual stop-word list is needed. Returned chunks also carry `file_path`, `doc_id`, and `title` provenance for citation.

By default the brain corpus **excludes archived documents** (`status='archived'`). Pass `"include_archived": true` in the event to surface them (e.g. for historical questions):

```bash
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "DOCUMENT_QA",
    "data": {
      "doc_id": "00000000-0000-0000-0000-000000000000",
      "question": "When did we do the OKF backfill?",
      "corpus": "brain",
      "include_archived": true
    }
  }'
```

### Structural graph expansion (OR.G)

The brain corpus also supports a **structural** retrieval widening on top of semantic search:
after Stage 1 (semantic) hits are found, the top 5 are used to walk `brain_edges` — a table of
resolved `related:` frontmatter edges, loaded from mev's `emit-graph` output by
`scripts/load_brain_edges.py` — and pull in their neighbor documents as extra candidates before
keyword re-rank. Each structurally-added chunk is flagged `"via": "structural"` in the response
(semantic hits carry `"via": "semantic"`) so callers can distinguish provenance.

This is **on by default** and controlled by the optional `expand_structural` field (default
`true`); set it to `false` to fall back to semantic-only retrieval:

```bash
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "DOCUMENT_QA",
    "data": {
      "doc_id": "00000000-0000-0000-0000-000000000000",
      "question": "What decisions relate to the Bastion Engine role?",
      "corpus": "brain",
      "expand_structural": false
    }
  }'
```

**Prerequisite:** `brain_edges` must be populated by running mev's `emit-graph` over the brain
repo and piping it into the loader (`mev emit-graph ~/Dev/agentic-portfolio | python
scripts/load_brain_edges.py`) — see `docs/scripts.md` § `load_brain_edges.py`. An edge whose
target doesn't resolve is kept as a dangling row rather than dropped, so structural expansion is
a no-op for that neighbor rather than an error. See `docs/api-reference.md` § `RetrieveChunksNode`
and § `BrainEdge SQLAlchemy Model` for the full mechanics.

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
      "filters": {"project": "orchestrator", "status": "active"}
    }
  }'
```

Supported filter keys: `"layer"` (array overlap — matches if the document's layer list contains the value), `"project"` (scalar `==`), `"status"` (scalar `==`). Unknown keys and `null` values are silently skipped.

### Keyword-candidate expansion

Stage 2's keyword re-rank is scoped to `WHERE id IN (candidate_ids)` — it can only boost a
document Stage 1 (semantic) or Stage 1b (structural) already picked as a candidate. A document
with a strong full-text match but a cosine-distance rank outside the Stage-1 top-20 was
previously invisible to keyword re-rank no matter how well it matched. Confirmed live: the query
`"OR.V graph resolver cleanup"` never surfaced `core/orchestrator/planning/status.md` despite it
having one of the best `ts_rank` scores in the whole corpus, because its cosine-distance rank sat
around 60-77.

Stage 1c (`_keyword_expand`) fixes this: an independent top-15 full-text query (`ts_rank`
descending, same corpus/filters/archived-exclusion as `_semantic_search`) runs alongside
structural expansion, and its hits are unioned into the candidate set before Stage 2 re-ranks,
flagged `"via": "keyword"` in the response. It always runs for the brain corpus (not gated by a
request flag, unlike `expand_structural`) and is a no-op for corpora without a `tsv_field` (e.g.
`"content"`).

---

## Testing retrieval manually

Two ways to check that indexing actually produced good, queryable results, from lightest to
heaviest:

### 1. Raw semantic search — `scripts/query_brain.py`

The fastest sanity check. Embeds your query and prints the nearest `brain_documents` rows —
**no** keyword fusion, no structural expansion, no LLM answer. Good for isolating whether
retrieval quality problems are in embedding/ranking versus the fuller pipeline, and for
checking a fresh `--rebuild` without starting the API/Celery stack:

```bash
python scripts/query_brain.py "What is the Bastion program and its five layers?"

# More results, with a content snippet
python scripts/query_brain.py "How does structural graph retrieval work?" --limit 10 --show-content
```

Each line shows cosine distance (`0.0` = identical, larger = less similar), the source file,
its OKF `title`, and the section header. See `docs/scripts.md` § `query_brain.py` for the full
flag reference. Requires only Postgres + Ollama running (no API server, no Celery worker).

A query matching a bare structured code (`D20`, `OR.V`, `MV.3B.Q`) short-circuits straight to
a `doc_id`/`file_path` lookup — no embedding call. Pass `--hybrid` to run the same
keyword+semantic fusion `RetrieveChunksNode` uses in production (including the diversity cap
on results-per-file), without standing up the API/Celery stack — see (2) below for when the
full pipeline is still worth exercising.

### 2. Full answer path — `DOCUMENT_QA` over HTTP

Exercises the real pipeline an end user gets: two-stage hybrid retrieval (semantic + graded
keyword re-rank) + structural graph expansion + LLM-grounded answer synthesis. Requires the
API (`uvicorn`) and a Celery worker running (see `docs/getting-started.md`) — use the `curl`
examples under "Querying the brain" above (`corpus: "brain"`).

Use (1) first to confirm the corpus is populated and retrieval is sane, then (2) to confirm
the end-to-end answer quality once (1) looks right.

---

## When to re-index

Re-run `index_brain.py` after:
- Adding or updating any document in a corpus path — `docs/` (incl. `docs/diagnostic/`, `docs/projects/`, `docs/business/`), the in-corpus `planning/` docs (`bastion-product`, `bastion-ui`, `status.md`, `archived`), or top-level `CLAUDE.md`/`README.md`
- Publishing a decision (`docs/decisions/`)

> The auto-memory (`~/.claude/.../memory/` + `MEMORY.md`) is **not** in the corpus — it lives outside the brain repo and drifts, so the repo docs are the authoritative current-state source. See the brain-rag-improvements plan, Block E1.

The incremental mode is fast — it compares `indexed_at` against file modification time and skips unchanged docs. Only updated or new sections get re-embedded.

### Deleted and renamed files (orphan rows)

The incremental upsert keys on `file_path + section`, so it only ever *adds or replaces* rows for files it walks. When a file is **deleted or renamed away**, the indexer never revisits the old path and its rows linger as stale retrieval hits. Two ways to clean them up:

- **Surgical:** `python scripts/index_brain.py --prune-paths <old paths…>` deletes just those files' rows — no re-embedding, no API call. Diagnostic rows (`client_slug` set) are preserved.
- **Automatic:** the brain repo ships a `post-commit` git hook (tracked in `hooks/`, enabled via `git config core.hooksPath hooks`) that runs `--prune-paths` for exactly the files a commit deleted or renamed. It is a no-op on ordinary edits and catches renames whether or not `git mv` was used. See `hooks/README.md` in the brain repo.

Note this is **file-level** cleanup only. A section renamed or removed *inside* a still-existing file leaves an orphan row that neither incremental indexing nor `--prune-paths` removes — run `--rebuild` after structural edits within files.

---

## Resetting and tearing down the store

There are three levels of reset, from softest to hardest:

| Goal | Command | Effect |
|---|---|---|
| Rebuild the corpus (keep the schema) | `python scripts/index_brain.py --rebuild` | Deletes all **non-diagnostic** rows (`client_slug IS NULL`), then re-indexes from scratch. **Diagnostic rows are preserved** — this is *not* a full wipe. |
| Remove specific files' rows | `python scripts/index_brain.py --prune-paths <paths>` | Deletes rows for the named files only. No re-embedding. |
| Drop the OKF columns | `cd app && alembic downgrade c4d5e6f7a8b9` | Reverts migration `d1e2f3a4b5c6` only (the six OKF columns + their indexes). Restore with `alembic upgrade head`. |
| Drop the `brain_documents` table | **Not a clean `alembic downgrade`** — see note below | Manual `DROP TABLE brain_documents` or a new targeted migration. |

**Why the table can't be cleanly downgraded:** `brain_documents` is created by migration `b3c4d5e6f7a8`, which sits *below* the mergepoint `020c9f7f89e2` that it shares with the `events` and `content_chunks`/`chat_sessions` tables. Downgrading far enough to drop `brain_documents` would also drop those tables. To drop just this table, run a manual `DROP TABLE brain_documents CASCADE` or author a dedicated down-migration — don't reach for `alembic downgrade`.

**On the diagnostic-row carve-out:** `doc_type="diagnostic"` rows carry client-specific pattern data that is expensive to regenerate, so `--rebuild` deliberately leaves them in place. If you genuinely need a *full* clear including diagnostic rows, delete them by hand (e.g. `DELETE FROM brain_documents WHERE doc_type = 'diagnostic'`).

---

## Multi-workspace corpora (OR.C)

`index_brain.py` and `RetrieveChunksNode` are not hard-wired to the brain repo — a **workspace**
is any named OKF markdown root, per the pinned knowledge workspace contract
(`docs/workspace-contract.md` v1.0.0, brain D47), and the brain corpus above is just the
degenerate single-workspace case (no `--workspace`/`--root` flags needed, behavior unchanged).

Indexing a second, non-brain OKF directory:

```bash
python scripts/index_brain.py --workspace my-notes
```

resolves `my-notes` against the `[workspaces]` registry (see `docs/configuration.md` §
"Workspace registry"), walks it per contract §4 (`.md`/`.mdx`, hidden entries and `target/`
skipped, empty corpus fatal), and stamps every row `project=my-notes` with `file_path` relative
to that workspace's own root.

**The workspace name IS the retrieval scoping value** — no separate concept exists at query
time. Answer over that workspace alone with the same `filters` field documented above:

```bash
curl -X POST http://localhost:8080/events/ \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: dev-secret' \
  -d '{
    "workflow_type": "DOCUMENT_QA",
    "data": {
      "doc_id": "00000000-0000-0000-0000-000000000000",
      "question": "What does this workspace say about X?",
      "corpus": "brain",
      "filters": {"project": "my-notes"}
    }
  }'
```

Two workspaces can each contain a same-named/same-relative-path file without colliding — every
destructive write (incremental upsert, `--rebuild`, `--prune-paths`) is scoped by `project` in
workspace mode, and a brain-scoped query never returns another workspace's rows (retrieval was
already conformant here — no production change was needed, only tests). Structural graph
expansion (`brain_edges`) is a harmless no-op for a workspace with no loaded edges.

See `docs/workspace-contract.md` for the full binding rules (names, resolution precedence, corpus
rules) and `docs/scripts.md` § "Workspace mode" for the full CLI reference.

---

## Notes

- The `brain_documents` table uses PostgreSQL `ARRAY` for `workflow_patterns`, which is not compatible with SQLite. Tests that touch this model are marked `@pytest.mark.skip(reason="requires PostgreSQL")` — this is intentional (see decision D31).
- Embeddings are 1024 dimensions regardless of provider. If you switch models or providers, run `--rebuild` to avoid mixing vector spaces.
- **Embedding provider is local Ollama `mxbai-embed-large` (shipped, D37, OR.H/OR.B — 2026-07-03).** `EmbeddingService` defaults to `provider="ollama"`, `model="mxbai-embed-large"` — **1024-dim** (matches `EMBEDDING_DIM`, no migration), free, and ~670 MB / ~1–2 GB resident (runs comfortably on the M1 16 GB Mac Mini that also hosts Postgres, and on a MacBook Pro). This replaced Voyage as the default after Voyage's free-tier rate limit (3 RPM / 10K TPM, no payment method) blocked the first live `--rebuild`. Voyage remains available via `EMBEDDING_PROVIDER=voyage` (requires `VOYAGE_API_KEY`) for anyone who wants hosted embeddings instead. The vector store is now populated: the first full `--rebuild` indexed 176 corpus files / 1243 chunks in ~87 seconds at zero API cost. See `planning/decisions/D37-local-embeddings-mxbai.md`.
- Diagnostic rows (`doc_type="diagnostic"`) are protected from `--rebuild` deletion — they carry client-specific pattern data that is expensive to regenerate.
