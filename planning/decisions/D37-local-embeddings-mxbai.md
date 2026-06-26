---
type: Decision
title: D37 — Embeddings go local (mxbai-embed-large via Ollama), not Voyage
description: For the Brain vector store, use a local 1024-dim embedding model (mxbai-embed-large via Ollama) instead of Voyage. Pulls the Project H local-embedding step forward (per D35), keeps EMBEDDING_DIM=1024 so no migration is needed, and makes index_brain.py --rebuild free and repeatable. Revisit a hosted/larger model when real clients justify it.
---

# D37 — Embeddings go local (mxbai-embed-large via Ollama), not Voyage

**Decided:** The Brain vector store (`brain_documents.embedding`) is populated by a **local embedding
model — `mxbai-embed-large` served by Ollama** on the Mac Mini — rather than the Voyage API. The
`EmbeddingService(model, dims)` provider seam (already built for exactly this, see its docstring and
**D35**) is repointed from `voyageai.Client` to an Ollama embeddings call in `embed_text` /
`embed_batch`. No other code, schema, or retrieval change.

## Why

1. **The free tier wall forced the choice now.** The first live `index_brain.py --rebuild` (brain-rag
   Block H) was blocked by Voyage's free tier — 3 RPM / 10K TPM with no payment method — and the
   indexer has no backoff, so the full 109-file corpus could not be embedded. The realistic options
   were "add Voyage billing" or "go local." For a single-operator brain with no paying clients yet,
   adding a card to a metered API for a personal knowledge base is the wrong trade.
2. **This is the Project H local step, pulled forward.** D35 already committed to "top-tier models
   first, then introduce local/open-weight **via Project H**." D37 executes that local step early and
   narrowly — **for embeddings only** — because the rate limit made it the path of least resistance,
   not because chat-model quality is in question. D35's posture (prefer strong models for *reasoning*)
   is unchanged; this is purely the embedding provider.
3. **1024-dim ⇒ zero migration.** `mxbai-embed-large` outputs **1024** dimensions, matching
   `EMBEDDING_DIM = 1024` (set for `voyage-2`). The `Vector(1024)` column, the HNSW index, and the
   `content_tsv` FTS half are all untouched. Picking a 384- or 768-dim model (e.g. `all-MiniLM`,
   `nomic-embed-text`) would have forced a migration; we deliberately chose the dimension-matching
   model to avoid that.
4. **Free + repeatable dissolves the "pay once" constraint.** The brain-rag-improvements plan was
   shaped around getting the corpus perfect before a single expensive Voyage pass. Local embeddings
   make `--rebuild` free and repeatable, so the corpus can be re-embedded freely as it grows
   (Block O) or the model is upgraded — a strictly better operating posture for a fast-moving brain.
5. **Trivial to run.** `mxbai-embed-large` is ~670 MB download / ~1–2 GB resident — negligible on the
   M1 16 GB Mac Mini that already hosts the orchestrator's Postgres and runs `llama3.1` (~4.7 GB) for
   `rag-engine-rs`. Co-locating the embedder with the DB keeps the whole `--rebuild` loop local.
6. **Quality is sufficient here.** `mxbai-embed-large` is a strong open MTEB-competitive retrieval
   model; for a ~109-doc personal brain the delta vs Voyage is immaterial, and the FTS re-rank
   (`ts_rank` over `content_tsv`) carries the keyword half regardless of the vector model.

## Rejected alternatives

- **Add a Voyage payment method.** Unlocks standard rate limits and stays $0 under the 200M free-token
  grant — but ties a personal knowledge base to a metered hosted API and a billing relationship with
  no client value yet. Reconsider only if a hosted embedder's quality is ever shown to matter for a
  paying engagement.
- **Reuse `rag-engine-rs`'s Flask `all-MiniLM-L6-v2` service (384-dim).** Free and local, but 384-dim
  forces a schema migration + HNSW rebuild, runs an extra service, couples two repos, and uses an
  older/weaker model. More work for a worse result.
- **`nomic-embed-text` via Ollama (768-dim).** Good and local, but 768 ≠ 1024 ⇒ migration. Not worth
  it when a 1024-dim local model exists.

## Scope / revisit

- **Implementation is deferred** to an at-home session (install Ollama on the Mini → `ollama pull
  mxbai-embed-large` → repoint `EmbeddingService` → `--rebuild` → Block H smoke tests). Until then the
  Brain vector store is empty (schema migrated, write-path verified) — **not blocking** other work;
  only Brain semantic retrieval (Block B) waits on it.
- **Revisit when real clients justify it:** a multi-tenant or higher-recall need may warrant a larger
  local model or a hosted embedder. Any model change means a free local `--rebuild` (and a migration
  only if the new model's dimension ≠ 1024). This decision is cheap to reverse by design.

## References

- D35 (top-tier models first, then local/open-weight via Project H) — D37 executes its local step for embeddings.
- D36 (this repo is the Engine + Python half of the Brain) — the Brain store this populates.
- brain-rag Block H + the embedding-provider note: `docs/brain-rag.md`; the deviation-log entry in
  `planning/status.md`; brain `planning/brain-rag-improvements/implementation-report.md`.
- `app/services/embedding_service.py` (the `model`/`dims` provider seam); `app/database/brain_document.py` (`EMBEDDING_DIM = 1024`).
