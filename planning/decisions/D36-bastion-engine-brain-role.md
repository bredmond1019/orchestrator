---
type: Decision
title: D36 — This repo is Bastion's Engine + Python-half-of-Brain; adopt the program plan
description: Adopt the brain's Bastion program (D24/D25/D26) locally — this repo is the Engine and the Python half of the Brain; Project F ≡ Block B, Project G ≡ Block S; add Brain-side blocks O/J/C/P/L/R + cost-control I; sequence demand-first; keep the A–H numbering.
doc_id: D36-bastion-engine-brain-role
layer: [engine, brain]
project: orchestrator
status: active
keywords: [Bastion Engine, Python brain, program blocks, demand-first, brain RAG]
related: [master-plan, app-architecture-overview, brain-rag]
---

# D36 — This repo is Bastion's Engine + Python-half-of-Brain; adopt the program plan

> **Narrowed by brain D42 (2026-07-02).** The Engine layer now gains a Rust implementation: a fresh
> `engine-rs` (core tier) is built as a parallel pilot and is the graduation target for workflow
> execution. This repo keeps its **Python half of the Brain** role and stays the prototyping-Engine +
> production path until `engine-rs` reaches data-contract parity; the D20/D30 data contract is the seam
> both engines write. `engine-rs` embeds in `bastion serve`. The "Console never shares engine code" framing
> is superseded only for the *language of the Engine* — the read-only-observer relationship over the data
> contract still holds. See brain `docs/decisions/D42-rust-engine-parallel-pilot.md` and D41.

**Decided:** This repo plays **two of Bastion's five layers** — the **Engine** (the LLM/agent
workflow runtime) and the **Python half of the Brain** (`brain-rag`: semantic retrieval, indexing, the
memory/entity store). The brain's Bastion program plan
(`agentic-portfolio/planning/bastion-product/`, governed by brain **D24/D25/D26**) is authoritative for
cross-repo order and seams. This decision adopts it locally and records the concrete consequences for
this repo's `master-plan.md`:

1. **Project F ≡ brain-program `OR.B`** — "semantic search over the corpus" *is* the Brain's semantic
   layer; the two are unified (brain D26 F≡B). F is no longer a standalone Phase-2 extra but the
   Wave-0 semantic-retrieval half of the Brain (populate the store, confirm `"brain"`-corpus Q&A;
   retrieval already shipped in Project D).
2. **Project G ≡ brain-program `OR.S`** — agent memory is the Brain's memory capability: the store is
   Brain data, the workflows (ingest-time extraction, dream-time consolidation on Claude) are Engine,
   the Console reads it. Reframed so **clients, companies, products, and SOPs are first-class
   entities**, keyed by `workspace_id`.
3. **New Brain-side blocks** are added to the master-plan in the `/generate-master-plan` block-contract
   format and owned here: **`OR.O`** (widen the index corpus to all sub-repo docs), **`OR.J`** (freshness loop —
   auto-reindex on commit), **`OR.C`** (multi-workspace Brain — Python half), **`OR.P`** (semantic code search),
   **`OR.L`** (answer-time grounding — citation verify + abstain), **`OR.R`** (Brain-as-MCP-server — Python
   server half of the MCP split), and the **Python half of `OR.I`** (the abort endpoint + server-side budget
   gate the Console's kill switch triggers, per brain D25).
4. **Demand-first sequencing.** Post-checkpoint work follows the brain's demand-first wave table, not
   the old phase order: Wave 0 = `OR.B` + `OR.O` (after the private Tailscale face); Project E moves to
   Wave 4 ✲. The brain wave table is the authoritative order; the local crosswalk is the legibility
   bridge.
5. **The A–H project numbering is preserved.** It is referenced across `status.md`, `decisions/`, and
   `CLAUDE.md`; the alignment is additive (reframings + new blocks + a crosswalk), not a renumber.

**Why:** Bastion is the brain's now-primary program, and this repo's master-plan predated the
reframing — it described an isolated "project library A–H" with no awareness of its Engine/Brain role,
and its status table was stale (Projects A–D shown as not-started though all are Done and the
competence checkpoint passed). Leaving it unaligned would let the project plan drift from the
cross-repo program, hiding load-bearing work (the freshness loop, the abort endpoint, the
Brain-as-MCP-server) that this repo, and only this repo, must build. Anchoring to the brain plan keeps
a single source of truth for *order and seams* while this repo keeps a self-sufficient block spec to
execute against.

**Rejected:**
- **Re-numbering Projects A–H to match the demand-first waves.** Cleaner as a single sequence, but
  cascades into `status.md`, every decision that cites a project letter, and `CLAUDE.md`, and reads as
  a disruptive rewrite for no execution benefit. A crosswalk gives the same legibility additively.
- **Keeping Projects F and G as standalone items.** Contradicts brain D26 (F≡B, memory-as-Brain-
  capability) and would duplicate the Brain's semantic/memory layers as if they were separate
  features, inviting drift.
- **Copying the brain's full wave table / block detail into this repo.** Violates the brain's
  "link, don't duplicate" rule and guarantees the two plans diverge. The brain owns the cross-repo
  order; this repo mirrors only the blocks it executes, cross-referenced by block letter + wave.

*Adopts brain D24 (Python/Rust seam + harvested substrate), D25 (Console read-only for state;
mutations triggered through the Engine/Factory), and D26 (Bastion-the-system naming, demand-first
posture, F≡B unification, MCP server/client split, code-aware Brain, memory as a Brain capability).
Supersedes the scope of local D17 (Rust "appliance shell" → the Console layer). Recorded
2026-06-25.*
