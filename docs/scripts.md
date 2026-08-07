---
type: Reference
title: Developer Scripts
description: Reference for all scripts in the scripts/ directory — setup, dev server, inspection, and brain indexing.
doc_id: scripts
layer: [engine]
project: orchestrator
status: active
keywords: [dev-setup, dev.sh, inspect_run, index_brain, developer scripts, workspace mode, syn CLI, recall, walk, pulse, prune]
related: [getting-started, brain-rag, configuration, workspace-contract]
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

## `scripts/inspect_run.py` — removed (`OR.X` cut 4)

This script inspected the most recent `CONTENT_PIPELINE` event and printed a per-node execution
report plus the stored `LearningArtifact`. It never generalized beyond `content_pipeline` (its
docstring named that workflow specifically), so per the `OR.X` cut-4 pre-flight it was deleted
alongside the workflow rather than re-pointed. Use `docs/api-reference.md`'s `TaskContext` /
`NodeRun` reference plus a direct DB read (`app/.env` connection strings) if you need an
equivalent per-node execution envelope for a surviving workflow.

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

**`OR.2.C` — a YAML frontmatter parse failure is a real gate, not a silent drop.** A file whose
frontmatter fails to parse raises a typed `DocumentParseError` (carries the file path and the
underlying cause), is logged by path, and is skipped — the run still indexes every other file,
including in the sub-repo `docs/` lane (`_sub_repo_docs_files`), which previously aborted the
whole run on the first malformed file. What changed is that the run no longer claims success:
`main()` now returns `0` on a clean run and `1` whenever any file failed to parse or write, and
`__main__` propagates it via `sys.exit(main())`. The summary names each failed path on its own
line, not just a count. `--dry-run`, `--rebuild`, `--only-paths`, and `--prune-paths` semantics
are unchanged.

**Quarantine, not delete — `stale_rows_retained` and `--prune-failed`.** The per-file upsert is
delete-then-insert keyed on `file_path` + `section` (`:1086-1094`); when parsing fails that delete
never runs, so a file's previously-indexed rows survive untouched and keep being served by
retrieval — the corpus quietly serves a stale copy of a now-broken file indefinitely. For every
failed path, the run now reports `stale_rows_retained: N` (how many `brain_documents` rows still
exist for that path) in the summary, per path, so an operator can tell a newly-broken file from
one that's been quarantined for days. **Default is retain** — matching this repo's existing
quarantine-then-repair split (`reconcile.py` reports, `ops.repair_deep_stale` repairs,
separately); a transient YAML typo should never destroy retrievable content with no preview. Pass
`--prune-failed` to delete those rows instead:

```bash
# Quarantine (default) — failed files' rows are retained and reported
python scripts/index_brain.py

# Delete stale rows for files that failed to parse this run
python scripts/index_brain.py --prune-failed

# Preview what --prune-failed would delete, without deleting anything
python scripts/index_brain.py --prune-failed --dry-run
```

`--prune-failed` respects `--dry-run` (reports what would be deleted, deletes nothing) and the
same workspace/project delete scoping `--rebuild`/`--prune-paths` already apply.

**Exit code propagation.** `index_brain.main()` is called in-process from three `app/brain/ops.py`
call sites (`embed_paths`, `prune_paths`/`ingest_dir`, `refresh`) — each now captures and surfaces
`main()`'s return code as `exit_code`/`success` on its own return payload, so `syn ingest`, `syn
refresh`, and `syn embed` all exit non-zero when a run recorded parse failures, not just a direct
`python scripts/index_brain.py` invocation. The cron-facing `refresh`/`reconcile` routines report a
non-zero result in their payload rather than raising — a scheduled run still completes and is
inspectable, it just isn't silently green.

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

**What gets indexed.** The corpus is derived from `brain.toml`, not from a hand-maintained
list, by four lanes in `_collect_files` that share one `seen` set so no file is ever
collected twice:

| # | Lane | What it contributes | `project` |
|---|---|---|---|
| 1 | Brain root (`_corpus_roots`) | the brain root's `docs/**/*.md` + `planning/**/*.md`, plus its `README.md` and `CLAUDE.md` | from each file's own frontmatter |
| 2 | Tier `docs/` (`_tier_docs_files`) | every **tier container**'s `docs/**/*.md` — `core/docs/`, `business/docs/`, `portfolio|side|client/docs/` | from each file's own frontmatter |
| 3 | Sub-repo widening (`_sub_repo_files`, OR.O) | every gitignored sub-repo's `planning/**/*.md` + root `CLAUDE.md` | **stamped** with the manifest `slug` |
| 4 | Sub-repo `docs/` (`_sub_repo_docs_files`, `OR.ticket.corpus-sub-repo-docs`) | every gitignored sub-repo's `docs/**/*.md`, excluding tier containers (whose `docs/` already arrive via lane 2) | **frontmatter wins, slug-fallback** |

All four honour `[crawl].skip_dirs` (so `archive/` subtrees stay out) and skip
underscore-prefixed and ephemeral filenames (`handoff.md`).

`doc_type` is a soft categorisation assigned by a path classifier (`_DOC_TYPE_RULES`)
applied to each file's path *relative to its own scope root*, so `core/docs/projects/x.md`
classifies identically to `docs/projects/x.md`. Retrieval filters on `status` and `corpus`,
never on `doc_type`. Note `memory/` and `MEMORY.md` are deliberately **not** in the corpus —
they are harness-managed auto-memory living outside the brain repo, and they drift.

**Lane 2 — tier `docs/` (`OR.ticket.corpus-tier-docs`).** A *tier container* is any manifest
slug that appears as some other repo's `tier` value (`core` holds `core/orchestrator`,
`business` holds `business/bastiel`, …) — derived from the manifest, never hardcoded, so
registering a new tier in `brain.toml` is enough to bring its `docs/` tree in. Leaf code
repos that happen to sit at the brain root (`learn-ai`, `base-template`, both
`tier = "_root"`) are *not* tier containers and keep their lane-3 treatment. This lane exists
because every tier is itself a `[[repos]]` entry, so `_corpus_roots` excludes it and only
lane 3 re-added it — `planning/` and `CLAUDE.md` but never `docs/`, which left 170 `.md`
files (the whole of `business/docs/`) outside the corpus. Do **not** "simplify" this by
un-excluding tiers in `_corpus_roots`: the root walk runs first and would claim
`<tier>/planning/**`, silently re-attributing it from `project=<tier slug>` to `None`.

**Lane 3 — sub-repo widening (OR.O).** Every chunk is unconditionally stamped with the
manifest's `project` slug (the workspace identity), overriding any frontmatter `project:`
value — sub-repo `planning/status.md` often carries none and `CLAUDE.md` has no frontmatter
at all. `--dry-run` annotates these entries with `(project=<slug>)` so you can confirm the
widened corpus before writing to the DB. A sub-repo's `docs/` and source are never reached
by this lane; that boundary is what distinguishes lane 3 from lane 2 and is filled in by
lane 4 below (`docs/` only — source stays out of the corpus).

**Lane 4 — sub-repo `docs/` (`OR.ticket.corpus-sub-repo-docs`).** Every gitignored manifest
repo with `repo_path != "."` that is **not** a tier container additionally contributes its
own `docs/**/*.md` subtree (tier containers' `docs/` already arrive via lane 2; the shared
`seen` set makes the exclusion belt-and-braces). Attribution is a third semantics, distinct
from lanes 2/3's plain `None`/override: **frontmatter wins, slug-fallback.** The lane peeks
each file's frontmatter at collect time — if `project:` is present, the triple's override is
`None` (the file's own frontmatter value flows through the ingest pipeline untouched); if
absent, the override is the repo's manifest `slug` (the same "truthy override wins" pipeline
that lanes 2/3 already implement stamps the fallback). Rationale: sub-repo `docs/` files are
OKF documents that mostly carry a correct `project:` of their own, but a file missing
frontmatter should still land in its own repo's scope rather than falling through to `None`
the way tier `docs/` (lane 2) does. `--dry-run` annotates fallback-attributed entries with
`(project=<slug>)`, same as lane 3; frontmatter-attributed entries show no annotation, same
as lanes 1/2. `--dry-run` reported a 864 -> 1021 file total (157 net new files) the first
time this lane ran live, spread across every manifest repo's `docs/` tree.

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

## `syn` — Brain console script (OR.N1 read commands + OR.N2 write/ops commands + OR.K2 eval + OR.K1 query log)

Agent-callable console script (registered `[project.scripts]` entry in `pyproject.toml`, `syn =
"app.brain.cli:main"`, mirroring `createworkflow`) wiring the Brain read cores
(`app/brain/retrieval.py::recall`, `app/brain/graph.py::walk`, `app/brain/pulse.py::pulse`), the
Brain write/ops core (`app/brain/ops.py::embed_paths`, `ingest_dir`, `prune_paths`, `refresh`,
`stale`, `run_routine`), the deep-drift read core (`app/brain/reconcile.py::deep_stale`,
`ops.py::repair_deep_stale`), the retrieval eval harness (`app/brain/eval/`, OR.K2), and the
OR.K1 retrieval query log's read command (`queries`, over the `retrieval_queries` table written
by `app/brain/query_log.py`) behind short, deterministic verbs: `recall`, `walk`, `pulse`,
`embed`, `ingest`, `prune`, `refresh`, `stale` (plain and `--deep [--repair]`), `routine`, `eval`,
`queries`. Every command supports `--json` for a machine-parseable payload and nothing else on
stdout, has a deterministic exit code (`0` on success; non-zero on an unhealthy `pulse` verdict, a
typed `--workspace` resolution error, an unknown `routine` name, `stale --assert-clean` finding
drift, `stale --deep` finding drift on any axis, `eval --baseline` finding a metric regression, or
an invalid `queries --since` window), and never prompts interactively.

**`--workspace` scoping (OR.K2):** `recall --workspace NAME` now actually scopes results to that
D47 workspace's `project` on every retrieval path (exact-id, semantic, hybrid) — previously a
no-op past the CLI's registry-validation step. `walk --workspace` remains reserved/unused
(`graph.walk()` takes no `workspace` parameter in this block).

```bash
syn recall "What is decision D20 about?"
syn recall "How does structural graph retrieval work?" --limit 10 --hybrid --json
syn recall "onboarding checklist" --workspace my-notes    # scopes to that workspace's project (OR.K2)

syn walk D20 --depth 2

syn pulse --json

# OR.N2 write/ops verbs
syn embed docs/scripts.md --force
syn ingest --dir docs/decisions --json
syn prune docs/old.md docs/decisions/gone.md    # the brain repo's post-commit hook calls this
syn refresh --rebuild
syn stale --assert-clean          # non-zero exit if content or structure drift is found
syn stale --deep --json           # five-axis deep drift report + the ingested/ lane
syn stale --deep --repair         # repair the repairable axes, then re-report the delta
syn routine refresh               # runs a registered ROUTINES entry (OR.J cron convention)
syn routine reconcile             # runs the deep check (report-only — no --repair from a routine)

# OR.K2 retrieval eval harness (statistical-honesty upgrade: plan-eval-statistical-honesty)
syn eval                                    # score the default golden set, write a dated report;
                                             # compares against the promoted pin (baseline.json) by default
syn eval --baseline planning/retrieval-eval-runs/2026-08-01T22-43-33Z.json   # explicit baseline override
syn eval --no-baseline                      # skip comparison entirely; always exits 0
syn eval --strict                           # old strict-sign tripwire: exit 1 on ANY metric decrease
syn eval --set path/to/other-golden-set.yaml --json
syn eval promote planning/retrieval-eval-runs/<run>.json --reason "..."   # promote a run to the pin
syn routine eval                            # report-only cron-safe run (no baseline comparison)

# OR.K1 retrieval query log
syn queries                                 # every logged retrieval_queries row, newest first
syn queries --since 7d --json               # last 7 days, JSON + a read-time abstain_rate
syn queries --abstained                     # rows where retrieval_confidence < 0.55

# Retention for the query log (deletion only — never a rollup)
syn queries --prune --dry-run               # what a prune would delete, deleting nothing
syn queries --prune                          # delete rows older than the keep window (default 90d)
syn queries --prune --keep-days 30 --json   # narrower window, machine-parseable summary
syn routine queries_prune                    # the cron-safe form (defaults, no dry run)
```

| Command | Description |
|---|---|
| `recall QUERY [--limit N] [--hybrid] [--workspace NAME] [--json]` | Exact-id / semantic / hybrid search over `brain_documents`, dispatched the same way `query_brain.py`'s `main()` does. `--workspace` (OR.K2) scopes every path. |
| `walk DOC_ID [--depth N] [--workspace NAME] [--json]` | BFS-traverses `brain_edges` from `DOC_ID` out to `N` hops. `--workspace` is accepted but currently unused (reserved). |
| `pulse [--json]` | Reports corpus/substrate health (pgvector + embedding reachability, row counts, staleness, `edges_empty_but_related_exists`). Exits non-zero when unhealthy. |
| `embed FILE [--force] [--brain-path PATH] [--json]` | Re-embeds a single file via `brain.ops.embed_paths` (which shells into `index_brain.py --only-paths`). `--force` bypasses the incremental skip. |
| `ingest --dir DIRECTORY [--force] [--brain-path PATH] [--json]` | Indexes every on-disk `*.md` file under `DIRECTORY` via `brain.ops.ingest_dir` (collects the file list, then calls `embed_paths`). Not the OR.Q artifact-ingest API path — this is on-disk file indexing only. |
| `prune PATH [PATH ...] [--dry-run] [--brain-path PATH] [--json]` | Deletes `brain_documents` rows for the named (deleted/renamed-away) file paths via `brain.ops.prune_paths` (shells into `index_brain.py --prune-paths`) — no embedding, no API call. The brain repo's post-commit delete/rename freshness hook calls this. |
| `refresh [--rebuild] [--dry-run] [--brain-path PATH] [--json]` | Runs the content-index step then the edge-reload step via `brain.ops.refresh`. `--dry-run` skips the edge-reload step entirely. |
| `stale [--assert-clean] [--brain-path PATH] [--json]` | Read-only drift report via `brain.ops.stale`: content axis (file mtime newer than its indexed `brain_documents` row) and structure axis (`pulse()`'s `edges_empty_but_related_exists`). `--assert-clean` turns any drift into a non-zero exit — the flag `OR.J`'s cron uses to fail loudly; a plain `syn stale` always exits `0`. |
| `stale --deep [--repair] [--brain-path PATH] [--json]` | Deep corpus/index drift report via `brain.reconcile.deep_stale` — the inverse of plain `stale`: it walks DB rows looking for the filesystem/edge/embedding state they claim to still be backed by, instead of walking the filesystem looking for DB rows. Five drift axes plus the informational `ingested/` lane and the `OR.2.C` ingest-ceiling axis (`uncovered_files`/`unparseable_files`/`excluded_count`); see below. Exits `1` whenever the final report's `drift` is `True`, `0` otherwise — unconditional, unlike plain `stale` (no `--assert-clean` gate: asking for `--deep` means you want the drift signal by definition). `--repair` dispatches `brain.ops.repair_deep_stale` (existing primitives only — see below) and reports the pre/post-repair delta instead of a single snapshot. |
| `routine NAME [--json]` | Runs a registered `ROUTINES` entry (`app.brain.ops.ROUTINES`; currently `refresh`, `stale`, `reconcile`, `eval`, and `queries_prune`) by name — the convention `OR.J`'s cron invokes. An unregistered name is a typed `UnknownRoutineError`, non-zero exit. `reconcile`/`eval` both run report-only — a routine must be cron-safe, so neither dispatches `--repair` or `--baseline`. `queries_prune` is the one **destructive** routine, and deliberately so: unlike a repair, a retention prune is a bounded, idempotent delete of rows past a fixed window, which is exactly what a cron routine is for. |
| `eval [--set PATH] [--baseline PATH] [--no-baseline] [--strict] [--no-write] [--json]` | **(OR.K2, statistical honesty: `plan-eval-statistical-honesty`)** Scores the golden set (`planning/retrieval-golden-set.yaml` by default) against the promoted `retrieval_engine.retrieve` pipeline — recall@5, recall@10, MRR, abstain-correctness, groundedness, **`groundedness_on_hits`**, no LLM in the scoring path — and writes a dated JSON report to `planning/retrieval-eval-runs/` (skip with `--no-write`). Every run additionally stamps `aggregate_stats` — a 95% interval (Wilson for proportion metrics, seeded bootstrap for the rest) plus `n` per metric. Compares against a baseline unless `--no-baseline` is passed: an explicit `--baseline PATH` wins, otherwise the promoted pin (`planning/retrieval-eval-runs/baseline.json`) is used when one exists; prints a signed per-metric delta plus a paired, per-case `verdict` (exact sign test for proportion metrics, paired bootstrap for continuous ones) and warns — never gates — if the live corpus diverges from the pin's. **Exit code:** non-zero iff some metric's paired verdict is `regressed-significant`; `--strict` restores the old strict-sign tripwire (exit non-zero on ANY metric decrease). `groundedness_on_hits` (added by `ticket-groundedness-baseline`) is the same lexical-support mean restricted to cases that actually matched an `expect_docs` document — the headline `groundedness` scores a recall-miss as `0.0` and therefore partly re-measures recall. **Read the pair, and read `groundedness` as a band, not a target:** the metric's known structural biases and its expected healthy range are documented in [`docs/brain-rag.md` § Reading `groundedness`](brain-rag.md#reading-groundedness--it-is-a-band-not-a-target) and decomposed case-by-case in `planning/artifacts/groundedness-baseline-analysis.md`. See `docs/api-reference.md` § [Retrieval Eval Harness](api-reference.md#retrieval-eval-harness-appbraineval-syn-eval). |
| `eval promote <run> --reason "..." [--force] [--json]` | **(OR.K2, `plan-eval-statistical-honesty`)** Promotes a tracked run under `planning/retrieval-eval-runs/` to the baseline pin (`baseline.json`), guarded: non-empty `--reason`; the run must carry `corpus`, `ranking_constants`, AND `aggregate_stats` (mechanically excludes all 15 pre-statistical-honesty run files); and, if a pin already exists, `--force` is required to promote a run that is significantly worse than it. See `docs/api-reference.md` § [Retrieval Eval Harness](api-reference.md#retrieval-eval-harness-appbraineval-syn-eval). |
| `queries [--since 7d\|24h] [--abstained] [--json]` | **(OR.K1)** Reads raw `retrieval_queries` rows logged by `app/brain/query_log.py::log_retrieval` at the retrieval core's single choke point — no stored aggregation, ever. `--since` parses a `<N>d`/`<N>h` window (an invalid string is a typed, non-zero-exit error); `--abstained` filters to `abstained=true` rows. `--json` additionally includes `count` and a **read-time-computed** `abstain_rate` over the returned rows (`abstained rows / total rows`, `0.0` when empty) — never a stored rollup. See `docs/api-reference.md` § [Retrieval Query Log](api-reference.md#retrieval-query-log-appbrainquery_logpy-syn-queries-or-k1). |
| `queries --prune [--keep-days N] [--dry-run] [--json]` | Retention mode for the same table — delegates to `brain.ops.prune_queries`, deleting `retrieval_queries` rows whose `created_at` is **strictly older than** the cutoff (a row exactly at the cutoff is kept). Prints/returns `{"deleted", "kept", "cutoff", "keep_days", "dry_run"}`, with `deleted`/`kept` derived from real row counts around the delete rather than from what was requested. `--dry-run` reports the would-delete count and deletes nothing. Exits `0` on success **including a zero-deletion no-op**; non-zero only on an actual error. `--prune` is mutually exclusive with the read filters `--since`/`--abstained` (and `--keep-days`/`--dry-run` are only valid with `--prune`) — an argparse usage error, exit `2`. Retention is deletion, not aggregation (the D51 guard): nothing is rolled up or persisted at prune time, and plain `syn queries` remains the only read surface. |
| `queries mine [--since 7d\|24h] [--min-count N] [--include-singletons] [--limit N] [--json]` | **(OR.2.E)** Read-time mining, not aggregation: renders `brain.query_mining.mine_candidates` as a stdout-only, fail-loud golden-set-candidate YAML fragment (`expect_docs: []`, `id: RENAME ME`, `source: mined`/`category: mined`/`source_query_id`, with a "top hits" comment under each case). Groups `retrieval_queries` by query text, excludes `surface == "eval"` rows and queries already in the golden set, drops singletons (`--min-count` default `2`; `--include-singletons` forces `1`), and classifies survivors as `abstained` / `low-confidence-answered` / `confidently-wrong-suspect` — the last a **heuristic, never a detector**. `--json` emits full per-candidate rationale instead. **Never writes `planning/retrieval-golden-set.yaml`** — mine, edit, paste, and re-validate by hand. An empty query log exits `0` with a friendly message. See `docs/api-reference.md` § [Retrieval Query Log](api-reference.md#retrieval-query-log-appbrainquery_logpy-syn-queries-or-k1) and `planning/retrieval-eval-runs/index.md` for the full mine → edit → paste → schema test → eval → promote workflow. |

**`BRAIN_QUERY_LOG_ENABLED` — the OR.K1 query-log inertness switch:** `app/brain/query_log.py`'s
`log_retrieval` write is gated by this environment variable (`"1"`/`"true"`, case-insensitive;
anything else, including unset outside the test suite, is treated as disabled). It defaults **on**
so production entry points (`syn`, the FastAPI app, the Celery worker) log without extra
configuration; `tests/conftest.py` carries an autouse fixture forcing it off for the whole suite,
and `tests/brain/conftest.py::enable_query_log` is the opt-in fixture individual tests request to
assert on written rows. Set it explicitly (e.g. `BRAIN_QUERY_LOG_ENABLED=0 syn recall ...`) to
silence logging for a one-off invocation outside the test suite.

**`BRAIN_QUERY_LOG_KEEP_DAYS` — the retention window:** how many days of `retrieval_queries` rows
`prune_queries` (and therefore `syn queries --prune` and the `queries_prune` routine) keeps.
Resolution order is **explicit argument (`--keep-days`) > this env var > 90**, and the env var is
read at *call* time, mirroring `BRAIN_QUERY_LOG_ENABLED`'s discipline. An unparsable or non-positive
value never crashes an unattended cron run — it falls back to 90 with a `logging.warning`.

The 90-day default is deliberate rather than arbitrary: the retained window **is the sample the
retrieval golden set gets grown from** (OR.K2), so a quarter of real traffic is the floor worth
keeping. Tightening it below 90 shrinks that sample — note the trade in the ledger before doing so.

**`stale --deep` — the five drift axes (plus the `ingested/` lane):**

1. **deleted-but-embedded** — an indexed `file_path` whose file no longer exists on disk. Excludes
   `ingested/%` rows (synthetic paths, no file was ever expected) and `client_slug` diagnostic rows.
   Repairable via `prune_paths` (exact paths).
2. **section-orphans** — a `(file_path, section)` pair in the DB absent from the file's *current*
   section set (derived via `brain.chunking.chunk_by_section`) for a still-existing file — a header
   rename/removal leaks a row the incremental upsert (keyed on that same pair) never revisits. No
   targeted-delete primitive exists; `--repair` names the manual `--rebuild` follow-up instead of
   inventing a second write path.
3. **orphaned content_chunks** — a `content_chunks.doc_id` group with no `position == 0` anchor row
   (the document-anchor every `ingest_artifact`-shaped write produces first). Repairable via a
   targeted delete of the orphaned rows.
4. **dangling brain_edges** — rows with a `NULL` `target_doc_id` (kept deliberately by the loader)
   plus rows whose non-null `target_doc_id` matches no `brain_documents.doc_id`. Repairable via
   `refresh_edges` (reloads the structural graph wholesale from `mev emit-graph`).
5. **model mismatch** — rows whose `embedding_model` stamp differs from the currently configured
   `EmbeddingService`'s stamp; `NULL` stamps are counted separately as `unstamped_count`
   (informational — pre-migration rows, not drift). No automatic repair — same manual `--rebuild`
   follow-up as section-orphans.
6. **`ingested/` lane** (informational, not drift) — count and `authored_at` age range of
   `ingested/%` rows, which never appear in plain `stale`'s filesystem-only axis.
7. **ingest ceiling — `uncovered_files` / `unparseable_files` / `excluded_count`** (`OR.2.C`,
   informational, not drift) — the inverse of axes 1-2: filesystem -> DB instead of DB ->
   filesystem. All five axes above walk indexed rows asking what backs them on disk; nothing
   walked the filesystem asking which files never made it into the DB at all — the ingest ceiling
   no ranking or eval change can see past. `uncovered_files` lists files enumerated on disk with
   zero `brain_documents` rows. `unparseable_files` lists files whose YAML frontmatter fails to
   parse (`DocumentParseError`), caught during enumeration or while diffing a file's section state
   — this is the same quarantine list `index_brain.py`'s summary reports, now visible from the read
   side too, and a malformed file here no longer makes `deep_stale` raise. `excluded_count` is the
   number of files the enumeration itself excluded, broken down by reason (`skip_dir`,
   `leading_underscore`, `ephemeral_filename`) — the number that answers "should this exclusion
   rule still apply?" without changing any rule. The enumeration is always
   `index_brain._collect_files`, imported rather than reimplemented, so this axis can never drift
   from what `index_brain.py` actually indexes.

`drift` is `True` when axes 1-5 report anything; the `ingested/` lane, `unstamped_count`, and axis
7's three buckets (`uncovered_files`/`unparseable_files`/`excluded_count`) are informational only
and never flip `drift` — a file being uncovered or excluded is often correct, and folding it into
`drift` would make the flag permanently true and train the operator to ignore it. `--repair` never
touches `client_slug` diagnostic rows on any axis.

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

## `scripts/emit_task_context_fixture.py` — removed (fixture is now a frozen golden file)

Removed under `OR.X` cut 2 (D51 divestment) along with the `RESEARCH_AGENT` workflow it ran
end-to-end to produce `tests/fixtures/task_context/research_agent_task_context.json`. That fixture
stays **byte-identical** going forward — `bastion` and `engine-rs`'s
`crates/engine-contract/tests/round_trip.rs` pin its exact bytes, and re-pointing the generator at
a surviving workflow would only regenerate different bytes, forcing an unnecessary data-contract
bump and a re-pin in both downstream repos to preserve a regeneration capability nobody used. The
fixture's value was always its *shape*, not its reproducibility — see `docs/data-contract.md` §5
and `tests/fixtures/task_context/README.md` for the frozen-golden-file note.
`tests/test_task_context_fixture.py` still asserts the checked-in file parses and carries the
documented shape; it no longer re-runs generation.
