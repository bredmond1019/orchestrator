---
type: Reference
title: Developer Scripts
description: Reference for all scripts in the scripts/ directory — setup, dev server, inspection, and brain indexing.
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
