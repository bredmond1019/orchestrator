---
type: Reference
title: Developer Scripts
description: Reference for all scripts in the scripts/ directory — setup, dev server, inspection, and brain indexing.
doc_id: scripts
layer: [engine]
project: orchestrator
status: active
keywords: [dev-setup, dev.sh, inspect_run, index_brain, developer scripts]
related: [getting-started, brain-rag, configuration]
---

# Developer Scripts

All scripts live in `scripts/`. They are machine-local helpers (excluded from `.gitignore` tracking for env-specific paths) so they don't belong in `app/`.

---

## `scripts/dev-setup.sh` — One-time local setup

Run this once to get Postgres, Redis, pgvector, and a working `app/.env` on a Mac with Homebrew.

```bash
./scripts/dev-setup.sh
```

**What it does (idempotent — safe to re-run):**
1. Installs `postgresql@17`, `redis`, and `pgvector` via Homebrew if not already present
2. Starts Postgres and Redis as Homebrew services
3. Creates a `orchestration` database role and a `orchestration_dev` database
4. Enables the `pgvector` extension
5. Writes `app/.env` with local connection strings (skips if the file already exists)
6. Runs `alembic upgrade head` to create all tables

After running, open `app/.env` and fill in your API keys:

```bash
open app/.env  # or: nano app/.env
```

The minimum key for any LLM workflow: `ANTHROPIC_API_KEY`.

---

## `scripts/dev.sh` — Start / stop the dev stack

Opens a tmux split with FastAPI on top and the Celery worker on the bottom.

```bash
./scripts/dev.sh          # start (or re-attach if already running)
./scripts/dev.sh stop     # kill the tmux session
```

**Requires:** `tmux` (`brew install tmux`) and both Postgres and Redis running. The script checks service health before launching and starts them if needed.

**tmux session layout:**

```
┌──────────────────────────────────────────────┐
│  FastAPI — uvicorn on 0.0.0.0:8080 --reload  │
├──────────────────────────────────────────────┤
│  Celery worker — --loglevel=info             │
└──────────────────────────────────────────────┘
```

The session is named `orchestration`. After detaching (`Ctrl-b d`), re-attach with `tmux attach -t orchestration` or just run `./scripts/dev.sh` again.

---

## `scripts/inspect_run.py` — Inspect the latest content pipeline run

Reads the most recent `CONTENT_PIPELINE` event from the database and prints a per-node execution report plus the stored `LearningArtifact`.

```bash
# Run from the repo root, with the env loaded
cd app && uv run python ../scripts/inspect_run.py
```

**What it prints:**

```
EVENT  id=...  created=...
PER-NODE EXECUTION ENVELOPE
  SourceRouterNode     status=completed  usage=—
  FetchTranscriptNode  status=completed  usage=in=1203 out=42 model=claude-sonnet-4-6
  SummarizerNode       status=completed  usage=...
  ...
SUMMARIZER OUTPUT (structured)
  { "title": "...", "summary": "..." }
STORAGE OUTPUT
  { "artifact_id": "...", ... }
LEARNING ARTIFACT (persisted row)
  id          : <uuid>
  source_url  : https://...
  title       : ...
  category    : ...
  tl_dr       : ...
  embedding   : 1024-dim vector
```

Useful after a test run to verify node execution, check token usage, and confirm the artifact was persisted correctly.

**Note:** Reads from the live database using the connection strings in `app/.env`. The Celery worker must have already completed the run before this shows useful data.

---

## `scripts/index_brain.py` — Index the company brain corpus

Crawls the `agentic-portfolio` markdown files, chunks them by section header, embeds the chunks via Voyage AI, and stores them as `BrainDocument` rows for semantic retrieval.

```bash
# Dry run — see what would be indexed without writing to DB
python scripts/index_brain.py --dry-run

# Full index (incremental — skips docs already indexed)
python scripts/index_brain.py

# Force rebuild — drops all non-diagnostic rows and re-indexes
python scripts/index_brain.py --rebuild

# Prune rows for deleted/renamed-away files (surgical — no embedding, no API call)
python scripts/index_brain.py --prune-paths docs/old.md docs/decisions/gone.md

# Custom brain path (defaults to the parent of the orchestration repo, resolved
# from the script's own location — so it works from any working directory)
python scripts/index_brain.py --brain-path /path/to/agentic-portfolio
```

**`--prune-paths`** deletes `brain_documents` rows whose `file_path` matches the given
paths, then exits. The incremental upsert keys on `file_path + section`, so a deleted or
renamed file's old rows are never revisited and linger as stale retrieval hits; this removes
them without re-embedding anything. Diagnostic rows (`client_slug` set) are preserved and a
warning is logged if any matched. This mode powers the brain repo's `post-commit` freshness
hook (see `hooks/README.md` in the brain repo), which prunes automatically on delete/rename.

**What gets indexed** (defined in `CORPUS` inside the script):

| Path in brain repo | `doc_type` |
|---|---|
| `docs/decisions/` | `decision` |
| `docs/projects/` | `project` |
| `docs/career.md` | `career` |
| `docs/brand.md` | `brand` |
| `docs/business/` | `business` |
| `docs/content/` | `content` |
| `docs/linkedin.md` | `content` |
| `planning/the-diagnostic/` | `diagnostic` |
| `memory/` | `memory` |
| `MEMORY.md` | `memory` |

Chunking is section-header-based (H2/H3 splits) so each chunk maps to a named section.

**Frontmatter handling:** When a document contains an OKF YAML frontmatter block (delimited by `---`), the indexer:
1. Parses the block with `parse_document()` and extracts the six OKF fields (`doc_id`, `layer`, `project`, `status`, `keywords`, `related`) via `normalize_metadata()`.
2. Strips the frontmatter from `content` before storage — no `---` or field lines leak into the stored chunk text.
3. Builds a semantic context prefix from the metadata (`type`, `title`, `description`, `layer`, `project`, `keywords`) via `build_context_prefix()` and prepends it to the text passed to `embed_batch` only — the stored `content` remains clean.

Out-of-vocabulary `layer`/`project`/`status` values are logged as warnings and stored unchanged; they never raise. Documents without frontmatter fall back to safe defaults (`doc_id` derived from filename stem; other fields `null`).

**Use this when:**
- You've added or updated brain documents and want them searchable via `DOCUMENT_QA` with `corpus="brain"`
- Before using the brain RAG layer for the first time

See `docs/brain-rag.md` for the full brain RAG architecture.

---

## `scripts/load_brain_edges.py` — Load structural graph edges (OR.G)

Reads a `mev emit-graph` v2 JSON payload (`nodes[]` + `edges[]`, one edge per authored
`related:` frontmatter entry) and loads it into the `brain_edges` table, reading each
edge's already-resolved `target_node_id`/`target_doc_id` fields directly — mev's own
`resolve_edge()` is the single source of truth for edge resolution; the loader no longer
re-resolves `to_ref` itself. This is the traversal layer that makes `BrainDocument.related`
queryable as a graph — `RetrieveChunksNode`'s structural neighborhood-expansion stage walks
these rows at query time.

```bash
# Pipe mev's output directly (recommended)
mev emit-graph ~/Dev/agentic-portfolio | python scripts/load_brain_edges.py

# Or read from a file
python scripts/load_brain_edges.py --input graph.json
```

| Argument | Description |
|---|---|
| `--input` | Path to an emit-graph JSON payload. Defaults to reading the payload from stdin. |

**Resolution:** the loader reads mev emit-graph v2's already-resolved `target_node_id`/
`target_doc_id` edge fields directly; an edge with a `null` target is kept as a **dangling
row** rather than dropped, preserving authoring intent. `validate_payload` requires
`version == "2"` — a pre-v2 payload carries no resolved target fields and would otherwise
silently load every edge as dangling. An edge whose *source* doesn't resolve against
`nodes[]` is skipped and logged (`source_doc_id` is a required non-null column).

**Idempotency:** the loader clear-then-reloads the whole `brain_edges` table inside one
transaction on every run, rather than upserting per-row — `brain_edges` is a read-only derived
index, not a source of truth, so a full reload is simpler and safe to re-run.

**Use this when:**
- You've run `mev emit-graph` over the brain repo and want the resulting graph queryable via
  `RetrieveChunksNode`'s structural expansion stage (`corpus="brain"`, `expand_structural=True`)
- After any brain document's `related:` frontmatter changes

See `docs/brain-rag.md` and `docs/api-reference.md` § `BrainEdge SQLAlchemy Model` for the full
structural retrieval architecture.

---

## `scripts/query_brain.py` — Manual semantic-search smoke test (OR.B)

Embeds a natural-language query via the configured `EmbeddingService` (local Ollama
`mxbai-embed-large` by default) and prints the nearest `brain_documents` rows by cosine
distance. This is **raw retrieval only** — no keyword fusion, no structural graph expansion,
no LLM answer synthesis — so you can eyeball indexing/retrieval quality right after a
`scripts/index_brain.py --rebuild` without standing up the API/Celery stack and driving the
full `DOCUMENT_QA` workflow.

```bash
python scripts/query_brain.py "What is the Bastion program and its five layers?"

# More results, with a content snippet per row
python scripts/query_brain.py "How does structural graph retrieval work?" --limit 10 --show-content

# Longer snippets
python scripts/query_brain.py "some question" --show-content --content-chars 400
```

| Argument | Description |
|---|---|
| `query` | (positional) Natural-language question to embed and search for. |
| `--limit` | Number of results to show (default: `5`). |
| `--show-content` | Print a content snippet for each result. |
| `--content-chars` | Snippet length in characters when `--show-content` is set (default: `200`). |

Each result line shows the cosine distance (`0.0` = identical, larger = less similar), the
source file path, the OKF `title`, and the section header if the chunk falls under one.

**Use this when:**
- You just ran `scripts/index_brain.py --rebuild` and want a fast sanity check that
  retrieval surfaces the right documents before wiring up the full `DOCUMENT_QA` path
- You're debugging a `"brain"`-corpus retrieval quality issue and want to isolate whether the
  problem is in embedding/ranking (this script) vs. keyword fusion or structural expansion
  (`RetrieveChunksNode`)

See `docs/brain-rag.md` § "Testing retrieval manually" for a walkthrough and for how this
compares to the full `DOCUMENT_QA` answer path.
