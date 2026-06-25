---
type: Decision
title: D36 — This repo is Bastion's Engine + Python-half-of-Brain; adopt the program plan
description: Adopt the brain's Bastion program (D24/D25/D26) locally — this repo is the Engine and the Python half of the Brain; Project F ≡ Block B, Project G ≡ Block S; add Brain-side blocks O/J/C/P/L/R + cost-control I; sequence demand-first; keep the A–H numbering.
---

# D36 — This repo is Bastion's Engine + Python-half-of-Brain; adopt the program plan

**Decided:** This repo plays **two of Bastion's five layers** — the **Engine** (the LLM/agent
workflow runtime) and the **Python half of the Brain** (`brain-rag`: semantic retrieval, indexing, the
memory/entity store). The brain's Bastion program plan
(`agentic-portfolio/planning/bastion-product/`, governed by brain **D24/D25/D26**) is authoritative for
cross-repo order and seams. This decision adopts it locally and records the concrete consequences for
this repo's `master-plan.md`:

1. **Project F ≡ brain-program Block B** — "semantic search over the corpus" *is* the Brain's semantic
   layer; the two are unified (brain D26 F≡B). F is no longer a standalone Phase-2 extra but the
   Wave-0 semantic-retrieval half of the Brain (populate the store, confirm `"brain"`-corpus Q&A;
   retrieval already shipped in Project D).
2. **Project G ≡ brain-program Block S** — agent memory is the Brain's memory capability: the store is
   Brain data, the workflows (ingest-time extraction, dream-time consolidation on Claude) are Engine,
   the Console reads it. Reframed so **clients, companies, products, and SOPs are first-class
   entities**, keyed by `workspace_id`.
3. **New Brain-side blocks** are added to the master-plan in the `/generate-master-plan` block-contract
   format and owned here: **O** (widen the index corpus to all sub-repo docs), **J** (freshness loop —
   auto-reindex on commit), **C** (multi-workspace Brain — Python half), **P** (semantic code search),
   **L** (answer-time grounding — citation verify + abstain), **R** (Brain-as-MCP-server — Python
   server half of the MCP split), and the **Python half of I** (the abort endpoint + server-side budget
   gate the Console's kill switch triggers, per brain D25).
4. **Demand-first sequencing.** Post-checkpoint work follows the brain's demand-first wave table, not
   the old phase order: Wave 0 = Block B + O (after the private Tailscale face); Project E moves to
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
