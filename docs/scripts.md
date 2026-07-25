---
type: Reference
title: Developer Scripts
description: Reference for all scripts in the scripts/ directory — setup, dev server, inspection, and brain indexing.
doc_id: scripts
layer: [engine]
project: orchestrator
status: active
keywords: [dev-setup, dev.sh, inspect_run, index_brain, developer scripts, run_eval, workspace mode, syn CLI, recall, walk, pulse, prune]
related: [getting-started, brain-rag, configuration, evals, workspace-contract]
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

# Restrict indexing to specific files (still flows through the same
# chunk->embed->write + incremental-skip pipeline; unmatched paths are warned and skipped)
python scripts/index_brain.py --only-paths docs/decisions/D52-foo.md docs/scripts.md

# Force a full re-embed of the targeted files, bypassing the incremental skip
# (narrower than --rebuild, which clears all non-diagnostic rows corpus-wide)
python scripts/index_brain.py --only-paths docs/scripts.md --force
```

**OR.N2 — `--only-paths` / `--force`:** these two flags are the reusable primitive
`app/brain/ops.py::embed_paths` shells into (no second chunk->embed->write implementation) — the
`syn embed`/`syn ingest` commands and `app.brain.ops.embed_paths`/`ingest_dir` are thin callers
over this exact path. `--only-paths` accepts one or more paths (absolute or brain-root-relative)
and filters the collected corpus down to just those files before the embed loop runs; a path
that isn't part of the collected corpus is logged as a warning and skipped, not an error.
`--force` disables the per-file incremental skip (the `indexed_at`-vs-mtime check) so the
targeted files re-embed unconditionally — it is scoped to whichever files are being processed
that run (all of them, or just `--only-paths`'s subset), unlike `--rebuild`, which deletes all
non-diagnostic rows corpus-wide before re-indexing from scratch.

### Workspace mode — indexing an arbitrary OKF directory (OR.C)

By default `index_brain.py` runs in **brain mode**: no flags needed, behavior is unchanged from
the table above (the `brain.toml` walk-up default). Passing `--workspace` and/or `--root`
switches to **workspace mode**, which indexes any OKF markdown directory — not just the brain
repo — per the pinned knowledge workspace contract (`docs/workspace-contract.md` v1.0.0).

```bash
# Index a workspace registered by name in ~/.config/orchestrator/config.toml
python scripts/index_brain.py --workspace my-notes

# Override resolution with an explicit root — --root always requires --workspace,
# since the name supplies the row identity ("project" column); --root only
# overrides where the corpus is read from
python scripts/index_brain.py --workspace my-notes --root /tmp/my-notes-checkout

# Dry run over a workspace — lists root-relative paths + the stamped project name
python scripts/index_brain.py --workspace my-notes --dry-run
```

**Flags:**

| Flag | Effect |
|---|---|
| `--workspace NAME` | Selects workspace mode. Resolves `NAME` against the `[workspaces]` registry (see `docs/configuration.md` § workspace registry) via `app/services/workspace_resolver.py`. `NAME` also becomes the row identity — every indexed chunk is stamped `project=NAME`. |
| `--root PATH` | Explicit workspace root, overriding registry resolution (contract §3 precedence step 1). Requires `--workspace` — the flag only changes *where* the corpus is read from, not the row identity. Using `--root` without `--workspace` is a usage error. |
| `--brain-path` | Brain-mode-only. Combining it with `--workspace`/`--root` is a usage error. |
| `--backfill-dates` | Populates `authored_at` (from each indexed file's mtime) for existing `brain_documents` rows that don't have it set yet, without any re-embedding or re-chunking round-trip. Exits immediately after backfilling — combine with `--dry-run` to preview the row count first. This is the one-time catch-up for rows indexed before `authored_at` existed; every normal index/`--rebuild` run populates it going forward. See `docs/brain-rag.md` for how `authored_at` feeds `RetrieveChunksNode`'s ranking decay. |

**Resolution** (`resolve_workspace_root`, contract §3), highest precedence first: (1) `--root`
always wins, no registry lookup; (2) `--workspace NAME` looked up in the `[workspaces]` registry
— an unregistered name raises a typed, descriptive error naming the workspace
(`UnknownWorkspaceError`), and a name supplied with no registry file at all raises a distinct
error (`NoWorkspaceRegistryError`); (3) the registry's `default_workspace` key, resolved the same
way; (4) the built-in default `Path(".")`. Resolution is pure — no I/O, no canonicalization, no
existence checks — so a resolved path that doesn't exist or isn't a directory surfaces as its own
explicit error once the indexer tries to walk it. Every resolver error is mapped to a
`SystemExit` carrying the resolver's own message — no raw tracebacks reach the CLI.

**Corpus walk** (`_collect_workspace_files`, contract §4 shared minimum): recursive; `.md` and
`.mdx` files; any file or directory whose name starts with `.` is skipped; any directory named
`target` is skipped. No `brain.toml` is required and none of the brain-mode narrowings apply (no
vocab checks, no manifest, no sub-repo crawl, no tier roots, no underscore/ephemeral-filename
skips). An empty result (zero `.md`/`.mdx` files under the resolved root) is a fatal error naming
the root — an empty corpus is never indexed silently.

**Row shape in workspace mode:** `file_path` is stored **relative to the workspace root** (not
the brain repo), and `project` is stamped with the workspace name **verbatim** on every row,
overriding any frontmatter `project:` value — this is what lets two different workspaces contain
a same-named file (e.g. both have a `README.md`) without colliding, and it's the same string
retrieval later filters on (`filters={"project": "<name>"}` — see `docs/brain-rag.md`).
Frontmatter parsing, chunking, embedding, and `title`/`description`/`is_section_title`
population are otherwise identical to brain mode.

**Scoped destructive queries:** in workspace mode, the per-file upsert delete (keyed on
`file_path + section`), `--rebuild`, and `--prune-paths` all additionally filter on
`project == <workspace name>` — so two workspaces sharing a relative path never delete or
overwrite each other's rows. As a corollary, **brain-mode `--rebuild` was narrowed**: it now
deletes only rows whose `project` is `NULL`/empty or one of the brain manifest's registered
project slugs, so a brain-mode rebuild can never wipe a non-manifest workspace's corpus that
happens to share the same `brain_documents` table. Diagnostic-row (`client_slug`) protection is
unchanged in every mode. `--dry-run` and `--limit` both work in workspace mode the same way they
do in brain mode.

See `docs/workspace-contract.md` for the full binding contract and `docs/configuration.md` §
workspace registry for the registry file format.

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

**Sub-repo widening (OR.O):** for every `brain.toml` `[[repos]]` entry with
`repo_path != "."`, the indexer also crawls that sub-repo's `planning/**/*.md`
subtree and its root `CLAUDE.md` — honouring the same `skip_dirs` / underscore /
ephemeral-filename rules as the brain-root crawl above. It never reaches a
sub-repo's `docs/` or source. Every chunk collected this way is unconditionally
stamped with the manifest's `project` slug (the workspace identity), overriding
any frontmatter `project:` value the file might carry — `CLAUDE.md` files have
no frontmatter at all. `--dry-run` annotates these entries with `(project=<slug>)`
so you can confirm the widened corpus before writing to the DB. Brain-root and
sub-brain-tier crawling above are unaffected — `project` there still comes from
each file's own frontmatter.

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

## `scripts/refresh_brain.py` — removed (use `syn refresh`)

This script was a thin shim over `app.brain.ops.refresh`, kept only for backward
compatibility while `syn` bedded in. With the delete/rename freshness hook migrated onto
`syn prune` and no remaining callers, the shim added no value over calling `syn refresh`
directly, so it was deleted rather than kept as a second entry point. There is exactly one
implementation, in `app/brain/ops.py::refresh`; runs the content-index step
(`index_brain.py`, `brain_documents`) then the edge-reload step
(`mev emit-graph | load_brain_edges.py`, `brain_edges`) in sequence — the two underlying
scripts have no shared entry point on their own, so running only `index_brain.py` leaves
`brain_edges` exactly as stale as never running anything at all (confirmed 2026-07-15:
`brain_edges` sat at 0 rows through an actively re-indexed 4749-row `brain_documents`
corpus, and `RetrieveChunksNode`'s structural-expansion stage silently returned zero
`via="structural"` results the entire time, with no error).

```bash
syn refresh
syn refresh --rebuild
syn refresh --brain-path ~/Dev/agentic-portfolio --dry-run
```

Requires the `mev` CLI on `PATH` for the edge-refresh step. Exits non-zero (propagates
`subprocess.CalledProcessError`) if `mev emit-graph` fails, before any `brain_edges` write is
attempted.

---

## `scripts/query_brain.py` — Manual semantic-search smoke test (OR.B)

Embeds a natural-language query via the configured `EmbeddingService` (local Ollama
`mxbai-embed-large` by default) and prints the nearest `brain_documents` rows by cosine
distance. This is **raw retrieval only** — no keyword fusion, no structural graph expansion,
no LLM answer synthesis — so you can eyeball indexing/retrieval quality right after a
`scripts/index_brain.py --rebuild` without standing up the API/Celery stack and driving the
full `DOCUMENT_QA` workflow.

**OR.N1:** the exact-id / semantic / hybrid search functions (`find_exact_id`,
`exact_id_lookup`, `semantic_search`, `hybrid_search`) were extracted into
`app/brain/retrieval.py` — the Brain's shared recall read core — once the `syn recall` console
command (see below) needed the same dispatch this script already had. This script is now a thin
caller that imports and re-exports those functions unchanged; only `main()` and the
`format_result`/`format_hybrid_result` display helpers stay here. Behavior and output are
byte-for-byte identical to before the extraction. See `docs/api-reference.md` §
[Brain Read Core](api-reference.md#brain-read-core-recall--walk--pulse--syn-cli) for the
extracted functions' reference.

A query that is (or contains) a bare structured code — e.g. `D20`, `OR.V`, `MV.3B.Q` — skips
embedding entirely and resolves via a deterministic `doc_id`/`file_path` ILIKE lookup instead,
since short alphanumeric identifiers aren't reliably distinct in embedding space.

```bash
python scripts/query_brain.py "What is the Bastion program and its five layers?"

# More results, with a content snippet per row
python scripts/query_brain.py "How does structural graph retrieval work?" --limit 10 --show-content

# Longer snippets
python scripts/query_brain.py "some question" --show-content --content-chars 400

# Exact-ID short-circuit — no embedding call made
python scripts/query_brain.py "What is decision D20 about?"

# Hybrid mode — reuses RetrieveChunksNode's keyword+semantic fusion (same ranking
# the production DOCUMENT_QA workflow produces) instead of raw cosine distance
python scripts/query_brain.py "some question" --hybrid
```

| Argument | Description |
|---|---|
| `query` | (positional) Natural-language question to embed and search for. |
| `--limit` | Number of results to show (default: `5`). |
| `--show-content` | Print a content snippet for each result. |
| `--content-chars` | Snippet length in characters when `--show-content` is set (default: `200`). |
| `--hybrid` | Use `RetrieveChunksNode`'s keyword+semantic fusion pipeline instead of raw cosine-distance semantic search. |

Each result line shows the cosine distance (`0.0` = identical, larger = less similar), the
source file path, the OKF `title`, and the section header if the chunk falls under one. In
`--hybrid` mode, each line instead shows the fused score and a `via=semantic|structural`
provenance tag.

**Use this when:**
- You just ran `scripts/index_brain.py --rebuild` and want a fast sanity check that
  retrieval surfaces the right documents before wiring up the full `DOCUMENT_QA` path
- You're debugging a `"brain"`-corpus retrieval quality issue and want to isolate whether the
  problem is in embedding/ranking (this script) vs. keyword fusion or structural expansion
  (`RetrieveChunksNode`) — pass `--hybrid` to see the fused-and-diversity-capped ranking without
  standing up the API/Celery stack

See `docs/brain-rag.md` § "Testing retrieval manually" for a walkthrough and for how this
compares to the full `DOCUMENT_QA` answer path.

---

## `scripts/ingest_repo_log.py` — Dogfood ingest of this repo's `log.md` (OR.M)

Parses this repo's `log.md` dated `##`/`###` entries into one reused `Peer(peer_id="orchestrator",
peer_type=PeerType.PRODUCT, workspace_id="orchestrator")` plus one `AgentEpisode` per entry, written
through the existing `EpisodeWriteService` (reused verbatim — no hand-rolled inserts). This gives
`RetrieveChunksNode`'s `_memory_expand` stage real episode data to be proven against instead of an
empty memory tier. Ingest only — consolidation over these episodes and any write-back to
`planning/knowledge.md`/`planning/memory.md` are explicitly out of scope.

```bash
# Dry run — parse and print entries, no DB writes, no embedding API calls
python scripts/ingest_repo_log.py --dry-run

# Ingest only the first N parsed entries
python scripts/ingest_repo_log.py --limit 5

# Delete existing 'orchestrator' peer episodes, then re-ingest from scratch
python scripts/ingest_repo_log.py --rebuild

# Ingest a log file at a different path
python scripts/ingest_repo_log.py --log-path /path/to/log.md --dry-run
```

| Argument | Description |
|---|---|
| `--log-path PATH` | Path to the log file to ingest (default: this repo's own root `log.md`). |
| `--dry-run` | Parse and print entries without writing to the DB or calling the embedding API. |
| `--limit N` | Ingest only the first `N` parsed entries. |
| `--rebuild` | Delete existing `orchestrator`-peer episodes (scoped by `peer_id`) before re-ingesting from scratch. |

**`--dry-run` is the deliverable's gate, not a convenience flag.** `log.md` is a *process* log
("ran `/close-out`, gates green, 1320 tests passed") — distilled into facts and injected into
answers, that risks being noise, since the durable content already lives in
`knowledge.md`/`decisions/` and is already indexed into `brain_documents` by
`scripts/index_brain.py`. Read the `--dry-run` output before trusting the write path.

**Heading parsing:** recognizes `## [run: DATE]` / `## [DATE]` / `## DATE` as pure
session-grouping headers (not entries themselves), `## DATE (title)` as a combined date+title
entry, and `### title` as an entry dated by the nearest preceding `##` grouping header — unless
the `###` heading carries its own embedded `DATE (title)` pattern, which overrides the enclosing
grouping header's date (the log has entries filed under a later session's grouping header that
document earlier-dated work).

**Use this when:**
- You want the memory tier's `_memory_expand` retrieval stage to have real episode data to
  retrieve against, without waiting on live peer/agent interaction traffic
- After a substantial `log.md` update, if you want the memory tier refreshed (`--rebuild`) to
  match

---

## `scripts/run_eval.py` — Offline eval CLI (OR.U)

Drives an `evals.slice.EvalSlice` end to end: loads already-recorded domain data (e.g. the
coding domain's SDLC run telemetry), builds the slice, executes + persists it via
`evals.runner.run_slice`, prints a by-domain/by-model pass-rate table, and optionally gates a
change (`evals.gate.gate_change`) or emits a routing config file. See `docs/evals.md` for the
full `app/evals/` library reference.

```bash
python scripts/run_eval.py --slice coding [--models MODEL ...] [--dry-run]
python scripts/run_eval.py --slice coding --gate [--baseline RUN_ID] [--min-delta F]
python scripts/run_eval.py --slice coding --emit-routing PATH [--quality-floor F]
```

| Argument | Description |
|---|---|
| `--slice NAME` | Registered eval slice to run (currently: `coding`). |
| `--models MODEL ...` | Models under test; defaults to the slice builder's own default. |
| `--dry-run` | List the slice's cases without executing or persisting anything. |
| `--gate` | After running, invoke the one-change self-improvement gate for each model under test; exits `0` if every model's decision is `keep`, `1` if any is `revert`. |
| `--baseline RUN_ID` | Explicit baseline run id for `--gate` (else the previous run in history is used). |
| `--min-delta F` | Minimum pass-rate improvement required to keep a candidate under `--gate` (default: `0.0`). |
| `--emit-routing PATH` | Write a per-model routing config JSON (quality vs. cost per model, plus the cheapest model meeting `--quality-floor`) to `PATH`. Produce only — nothing reads this file at runtime. |
| `--quality-floor F` | Minimum pass-rate a model must meet to be eligible for `--emit-routing`'s cheapest-model selection (default: `0.0`). |

This script runs from the CLI only — it is **not** a workflow node and is **not** run by Celery.

---

## `syn` — Brain console script (OR.N1 read commands + OR.N2 write/ops commands)

Agent-callable console script (registered `[project.scripts]` entry in `pyproject.toml`, `syn =
"app.brain.cli:main"`, mirroring `createworkflow`) wiring the Brain read cores
(`app/brain/retrieval.py::recall`, `app/brain/graph.py::walk`, `app/brain/pulse.py::pulse`) and
the Brain write/ops core (`app/brain/ops.py::embed_paths`, `ingest_dir`, `prune_paths`,
`refresh`, `stale`, `run_routine`) behind short, deterministic verbs: `recall`, `walk`, `pulse`,
`embed`, `ingest`, `prune`, `refresh`, `stale`, `routine`. Every command supports `--json` for a
machine-parseable payload
and nothing else on stdout, has a deterministic exit code (`0` on success; non-zero on an
unhealthy `pulse` verdict, a typed `--workspace` resolution error, an unknown `routine` name, or
`stale --assert-clean` finding drift), and never prompts interactively.

```bash
syn recall "What is decision D20 about?"
syn recall "How does structural graph retrieval work?" --limit 10 --hybrid --json

syn walk D20 --depth 2

syn pulse --json

# OR.N2 write/ops verbs
syn embed docs/scripts.md --force
syn ingest --dir docs/decisions --json
syn prune docs/old.md docs/decisions/gone.md    # the brain repo's post-commit hook calls this
syn refresh --rebuild
syn stale --assert-clean          # non-zero exit if content or structure drift is found
syn routine refresh               # runs a registered ROUTINES entry (OR.J cron convention)
```

| Command | Description |
|---|---|
| `recall QUERY [--limit N] [--hybrid] [--workspace NAME] [--json]` | Exact-id / semantic / hybrid search over `brain_documents`, dispatched the same way `query_brain.py`'s `main()` does. |
| `walk DOC_ID [--depth N] [--workspace NAME] [--json]` | BFS-traverses `brain_edges` from `DOC_ID` out to `N` hops. `--workspace` is accepted but currently unused (reserved). |
| `pulse [--json]` | Reports corpus/substrate health (pgvector + embedding reachability, row counts, staleness, `edges_empty_but_related_exists`). Exits non-zero when unhealthy. |
| `embed FILE [--force] [--brain-path PATH] [--json]` | Re-embeds a single file via `brain.ops.embed_paths` (which shells into `index_brain.py --only-paths`). `--force` bypasses the incremental skip. |
| `ingest --dir DIRECTORY [--force] [--brain-path PATH] [--json]` | Indexes every on-disk `*.md` file under `DIRECTORY` via `brain.ops.ingest_dir` (collects the file list, then calls `embed_paths`). Not the OR.Q artifact-ingest API path — this is on-disk file indexing only. |
| `prune PATH [PATH ...] [--dry-run] [--brain-path PATH] [--json]` | Deletes `brain_documents` rows for the named (deleted/renamed-away) file paths via `brain.ops.prune_paths` (shells into `index_brain.py --prune-paths`) — no embedding, no API call. The brain repo's post-commit delete/rename freshness hook calls this. |
| `refresh [--rebuild] [--dry-run] [--brain-path PATH] [--json]` | Runs the content-index step then the edge-reload step via `brain.ops.refresh`. `--dry-run` skips the edge-reload step entirely. |
| `stale [--assert-clean] [--brain-path PATH] [--json]` | Read-only drift report via `brain.ops.stale`: content axis (file mtime newer than its indexed `brain_documents` row) and structure axis (`pulse()`'s `edges_empty_but_related_exists`). `--assert-clean` turns any drift into a non-zero exit — the flag `OR.J`'s cron uses to fail loudly; a plain `syn stale` always exits `0`. |
| `routine NAME [--json]` | Runs a registered `ROUTINES` entry (`app.brain.ops.ROUTINES`; currently `refresh` and `stale`) by name — the convention `OR.J`'s cron invokes. An unregistered name is a typed `UnknownRoutineError`, non-zero exit. |

**Invoking from outside this repo:** `syn` is a real console script (`pyproject.toml` declares
`[build-system]`/`[tool.setuptools.packages.find]` with `namespaces = true`, since `app/` has no
`__init__.py` anywhere — a plain `packages = ["app"]` can't discover it). From within this repo,
`uv run syn ...` just works. To call it from any other directory without `cd`-ing here first, use
`uv run --project /path/to/core/orchestrator syn ...`, or alias it:

```bash
alias syn='uv run --project /path/to/core/orchestrator syn'
```

(`uv tool install --editable .` also puts a bare `syn` on `PATH`, but resolves its own
independent, unpinned dependency set rather than reusing this project's `.venv`/`uv.lock` — the
alias avoids that drift and is the recommended approach.)

See `docs/api-reference.md` §
[Brain Read Core](api-reference.md#brain-read-core-recall--walk--pulse--syn-cli) for the full
reference.

---

## `scripts/emit_task_context_fixture.py` — Emit a real `task_context` conformance fixture

Runs `ResearchAgentWorkflow` end to end (Anthropic client + prompt loading mocked; no DB/Celery
involved) and writes the resulting `TaskContext.model_dump(mode="json")` to
`tests/fixtures/task_context/research_agent_task_context.json` — a **captured**, code-path-produced
fixture, not a hand-authored one. `engine-rs`'s `crates/engine-contract/tests/round_trip.rs` asserts
against a checked-in copy of this file instead of a fixture it previously wrote about itself; this
repo's own `tests/test_task_context_fixture.py` asserts the same live output matches it too, so
drift on either side is caught. See `tests/fixtures/task_context/README.md` for full provenance
(what was redacted and why) and `planning/task-context-fixture/notes.md` for the finding that
prompted this.

```bash
uv run python scripts/emit_task_context_fixture.py
```

The event dict and every mocked Anthropic response are fixed literals, so re-running the script is
a no-op diff unless the workflow's actual `task_context` shape changes. If the diff is non-empty,
review it, update `docs/data-contract.md` §5/§6 if the shape changed intentionally, and copy the
regenerated file into `engine-rs/tests/fixtures/`.
Per the block's design principle (D33 / local D8), it is an offline eval harness, not a runtime
router: `--emit-routing` only ever produces a routing config file; nothing in `app/core/` or
`app/workflows/` reads it.
