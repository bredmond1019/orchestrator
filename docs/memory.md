---
type: Reference
title: Memory Layer — Entities, Episodes, and Durable Facts
description: The block OR.S memory capability — Peer/AgentEpisode/SemanticMemory models, the two-stage ingest/consolidation pipeline, decay, contradiction handling, and the loader's cosine/NL query modes.
doc_id: memory
layer: [brain, engine]
project: orchestrator
status: active
keywords: [memory, Peer, AgentEpisode, SemanticMemory, decay, contradiction, Honcho, workspace_id, MemoryLoaderNode, D35]
related: [api-reference, brain-rag, workspace-contract, workflows, D25-honcho-reference, D35-top-tier-models]
---

# Memory Layer — Entities, Episodes, and Durable Facts

Block **OR.S** — the Brain's memory capability. Clients, companies, products, and SOPs are
first-class **entities** (`Peer`) that accumulate **episodes** (`AgentEpisode`, what happened) and
distill **durable facts** (`SemanticMemory`, what's true) across interactions, so the Brain can
answer *"what did I last discuss with client X, what's their status, what rate did I quote."*

This is Brain data with an Engine pipeline around it: the three models are plain SQLAlchemy rows,
and `app/memory/` is a standalone, importable module with no coupling to any one workflow — any
workflow that needs "what do we know about peer X" attaches `MemoryLoaderNode` to its own DAG.

## Reference architecture (D25)

The design follows [Honcho](https://github.com/plastic-labs/honcho)'s reference architecture
(decision `planning/decisions/D25-honcho-reference.md`, read before writing code): a
**two-stage pipeline** (fast ingest-time extraction / deep dream-time consolidation), a
**multi-peer entity model**, and an **NL query interface**. The implementation here is custom
(not Honcho) — built for domain specificity, privacy-first deployment, and full traceability, per
D25's "build your own for production" call.

## Two-stage pipeline

```
per interaction                    dream-time (nightly / on-demand)
--------------                     ---------------------------------
MemoryIngestWorkflow                MemoryConsolidationWorkflow

IngestTimeExtractionNode            LoadMemoryContextNode
    -> MemoryWriteNode                  -> ConsolidationNode (Claude only, D35)
                                             -> ConsolidationWriteNode
```

- **`MemoryIngestWorkflow`** — fast, per-interaction: extracts an episode summary, outcome, tags,
  and candidate facts from one interaction (`IngestTimeExtractionNode`), then writes the episode
  and upserts the facts (`MemoryWriteNode`, composing `EpisodeWriteService` +
  `UpsertMemoryNode`). Candidate facts carry only a free-text `contradicts_hint` — resolving that
  hint to a concrete existing row id is deferred to dream-time consolidation; ingest-time writes
  candidate facts as plain new rows.
- **`MemoryConsolidationWorkflow`** — dream-time: deep reasoning across a peer's (or every peer's,
  the nightly-batch case) accumulated episodes and current facts, to distill durable facts,
  resolve contradictions (proposing a concrete `contradicts_fact_id`), and refresh
  `Peer.representation`. *Scheduling* the nightly run (Celery beat/cron) is deployment config and
  explicitly out of scope for this block — both workflows are ordinary event-dispatched workflows,
  like every other workflow in this repo.

Both workflows share exactly one write path for facts — `UpsertMemoryNode` — so the
never-overwrite contradiction rule has a single implementation regardless of which stage produced
the fact.

See [`workflows.md`](workflows.md) and [`api-reference.md`](api-reference.md) for full node-level
detail on both workflows; class-level detail on every memory abstraction is in
[api-reference.md](api-reference.md#peer-sqlalchemy-model).

## The three models

| Model | Table | Purpose |
|---|---|---|
| `Peer` | `peers` | The entity anchor — a client, company, product, sop, or user (`PeerType` StrEnum). Owns a stream of episodes and the facts distilled from them. `representation` is the dream-time-refreshed durable summary. |
| `AgentEpisode` | `agent_episodes` | One row per interaction — the fast, ingest-time capture of "what happened." Raw material dream-time consolidation reasons over. |
| `SemanticMemory` | `semantic_memories` | One row per durable fact about a peer, distilled from episodes (or written directly at ingest time). Decays in confidence over time; never overwritten in place. |

`AgentEpisode.embedding` and `SemanticMemory.embedding` are `pgvector` `Vector(1024)` columns,
matching the `mxbai-embed-large` 1024-dim default used elsewhere in this repo (OR.H). Full column
tables are in [api-reference.md](api-reference.md).

### `workspace_id` addressing

Every `Peer` is scoped by `workspace_id` — the [D47 workspace-contract](workspace-contract.md)
name (`brain.toml` `[[repos]].slug` format). Matching is a verbatim string comparison, never
fuzzy: the same `peer_id` in two different workspaces never collides in a query scoped by
workspace, and a query scoped to workspace X never returns workspace Y's entities. This block
builds the *entity store* only — indexing the brain repo's business/operational docs into the
brain corpus is out of scope here (that's `OR.O`/`OR.C` territory); the "status with client X"
answer cites episodes/facts, not corpus chunks.

## Confidence decay

Implemented as pure functions in `app/memory/decay.py` — no I/O, no mutation of the stored
`confidence` column. A fact's *effective* confidence at query/write time is computed on the fly:

```
effective_confidence = confidence * decay_factor ** weeks_elapsed
```

`weeks_elapsed` is the number of **whole weeks** between the fact's last write (`updated_at`, or
`created_at` when never updated) and now — fractional weeks truncate toward zero, and a negative
delta (clock skew) returns `0.0` rather than a negative exponent. The default `decay_factor` is
`0.95` (`SemanticMemory.DEFAULT_DECAY_FACTOR`), so the reference case is `confidence * 0.95 **
weeks_elapsed`. Decay is applied in two places, both reads, never a background job:

- **`UpsertMemoryNode`** — before comparing/lowering a contradicted fact's confidence.
- **`MemoryLoaderNode`** — for NL-question-mode ranking.

## Contradictions never overwrite

When an incoming fact contradicts an existing `SemanticMemory` row (identified by
`contradicts_fact_id`), `UpsertMemoryNode`:

1. Loads the contradicted row and computes its *current* effective confidence (decay applied
   first, so the comparison isn't against a stale written value).
2. Lowers that decayed confidence by a fixed penalty (`CONTRADICTION_PENALTY = 0.5`) and writes it
   back to the row's `confidence` column, bumping `updated_at`.
3. Inserts a **new** `SemanticMemory` row for the incoming fact.

The old row is **never** mutated in any other way and **never** deleted — both rows persist,
linked by evidence (`evidence_episode_ids`), so the full history survives. A dangling
`contradicts_fact_id` (row doesn't exist) is a silent no-op, not a raised error, so one malformed
contradiction hint never aborts a whole upsert batch.

`ConsolidationNode` only *proposes* a `contradicts_fact_id` per fact (from the loaded context);
`UpsertMemoryNode` is what actually enforces never-overwrite when that id is written.

## `MemoryLoaderNode` — two query modes

Session-start (or any-time) top-k memory loading, scoped by `workspace_id` and optionally
`peer_id`. Exactly one of two modes must be supplied per call:

- **Cosine mode** (`query_embedding`) — a caller-supplied embedding is compared against every
  in-scope `SemanticMemory.fact` embedding by cosine similarity; ranked by similarity alone.
- **NL-question mode** (`question`) — the question is embedded via `EmbeddingService` and facts
  are ranked by `similarity * effective_confidence`, so a stale, decayed fact that's still
  semantically close ranks below a fresher fact of similar relevance.

Optionally also returns the peer's most recent `AgentEpisode` summaries (`include_episodes=True`),
ordered by recency, not similarity — this is what feeds a cited "what's the status with client X"
answer: the answer step cites the returned episode/fact ids and summaries directly.

**Context budget.** The target is to keep injected representations to 5-10% of the context
window (D25's Honcho token-efficiency finding). `MemoryLoaderNode` estimates the token cost
(chars // 4) of what it loaded and logs a warning — never raises — when that estimate exceeds the
configured budget (`DEFAULT_CONTEXT_WINDOW_TOKENS = 8000`, `DEFAULT_BUDGET_RATIO = 0.10`). This is
a soft guard, not a hard failure.

### First consumer (block OR.M)

For the whole of block OR.S, `MemoryLoaderNode` had **zero consumers** outside its own package
and tests — the write path (`EpisodeWriteService`/`UpsertMemoryNode`) was wired, but nothing ever
read the tier back. Block **OR.M** gives it its first: `RetrieveChunksNode._memory_expand`
(`app/workflows/document_qa_workflow_nodes/retrieve_chunks_node.py`, `DOCUMENT_QA` workflow's
Stage 1d) calls `MemoryLoaderNode().retrieve()` in **cosine mode** — passing the query embedding
`RetrieveChunksNode` already computed via `EmbeddingService`, never `question` (NL mode would
re-embed the identical string for no benefit) — and adapts each returned fact into a `via="memory"`
retrieval candidate, decayed via the fact's own `effective_confidence`. See
[`docs/brain-rag.md`](brain-rag.md#memory-expansion-stage-1d-orm) for the request-shape and
ranking detail, and [`docs/api-reference.md`](api-reference.md#retrievechunksnode) for the
mechanics.

**Attaching `MemoryLoaderNode` elsewhere.** Nothing about the node is `DOCUMENT_QA`-specific — per
design decision 1 it is a standalone module with no coupling to any one workflow. Any other node
or workflow that wants "what do we know about peer X" attaches a `MemoryLoaderNode` to its own DAG
the same way: instantiate it, call `.retrieve(workspace_id=..., ...)` directly (as
`_memory_expand` does), or drop it in as a `process()`-chain node and read
`task_context.get_node_output("MemoryLoaderNode")["result"]`. It degrades gracefully when the
host event has no `workspace_id` — returns `{"facts": [], "episodes": []}` rather than raising
`AttributeError` — so it is safe to attach to a workflow whose event schema doesn't declare the
field at all.

## D35 — consolidation stays on Claude, never local

Per `planning/decisions/D35-top-tier-models.md` (frontier-only rule): weak models produce
confident-but-wrong durable facts, so `ConsolidationNode.get_agent_config()` pins
`ModelProvider.CLAUDE_CODE_SDK` unconditionally — `tests/workflows/test_memory_consolidation_workflow.py`
asserts this directly, so a config drift to a local model fails CI. Ingest-time extraction
(`IngestTimeExtractionNode`) has no such constraint: it ships on the default Claude provider today,
but is an explicit local-model routing candidate for `OR.U`/Project H to evaluate later. Routing is
always a `get_agent_config()`/`model_provider` change (CLAUDE.md standing rule 7), never an `if` in
a node.

## Prompts

Both agent nodes load their system prompts from `.j2` files via `PromptManager` (CLAUDE.md
standing rule 2) — no system prompt is hardcoded in Python:

- `app/prompts/memory_ingest_extraction.j2` — `IngestTimeExtractionNode`.
- `app/prompts/memory_consolidation.j2` — `ConsolidationNode`.

## Workflow registration

Both workflows are registered in both registries (CLAUDE.md standing rule 6, enforced by
`tests/api/test_endpoint.py::TestSchemaRegistryCompleteness`):

- `app/workflows/workflow_registry.py` — `WorkflowRegistry.MEMORY_INGEST` /
  `WorkflowRegistry.MEMORY_CONSOLIDATION`.
- `app/api/schema_registry.py` — mapped to `MemoryIngestEventSchema` / `MemoryConsolidationEventSchema`.

## Test coverage

The heavier Project G test bar (master-plan Project G library entry) — six mandated families, all
present:

| Family | Test file |
|---|---|
| Decay | `tests/memory/test_decay.py` |
| Contradiction handling | `tests/memory/test_upsert_memory_node.py` |
| Multi-peer isolation | `tests/memory/test_memory_loader_node.py`, `tests/database/test_memory_models.py` |
| Ingest extraction | `tests/workflows/test_memory_ingest_workflow.py` |
| Loader retrieval ordering (both modes) | `tests/memory/test_memory_loader_node.py` |
| Consolidation schema validity + D35 guard | `tests/workflows/test_memory_consolidation_workflow.py` |

Plus `tests/memory/test_episode_write_service.py` (peer accumulation) and
`tests/workflows/test_memory_e2e.py` (end-to-end accumulation across interactions + cited
"status with client X" answer, agent seam mocked).

## Deferred / out of scope

Hard boundaries for this block (see `planning/master-plan.md` `### OR.S` and the OR.S task spec's
design decision 7):

- **Model routing** of ingest/consolidation beyond the D35 Claude-only guard — `OR.U`/Project H's
  job.
- **Local models for consolidation** — never, per D35, regardless of routing work elsewhere.
- **Nightly scheduling wiring** (Celery beat/cron for `MemoryConsolidationWorkflow`) — deployment
  config, the `OR.J`-style trigger problem, not this block's.
- **Console read surfaces** (bastion) over this data — a separate Console-layer block.
- **Indexing the brain repo's business/operational docs** into the brain corpus — that's
  `OR.O`/`OR.C` territory; this block is the entity store, not the corpus.

## Migration

`app/alembic/versions/a3b4c5d6e7f8_create_memory_layer_tables.py` — hand-authored migration
creating `peers`, `agent_episodes`, and `semantic_memories`, applying cleanly to the single
alembic head (mirrors `f6a7b8c9d0e1_create_eval_runs_and_results_tables.py`'s hand-authored
style).
