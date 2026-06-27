---
type: Plan
title: Price Scout Workflow — ingest + analyze
description: Plan to register a PRICE_SCOUT workflow that ingests a completed Price Scout search result via POST /events/ and runs an LLM analysis node over it (persist → analyze → structured verdict).
doc_id: price-scout-workflow
layer: [engine]
project: orchestrator
status: active
keywords: [price scout, PRICE_SCOUT, workflow, cross-repo, LLM analysis, data contract]
related: [data-contract, workflows, master-plan]
---

# Price Scout Workflow — ingest + analyze

**Status:** Ready to build. Sequencing agreed with the `price-scout` owner: **orchestrator
first** (register the workflow + bump the data contract), **then** wire the Price Scout client
to the live endpoint.

**Origin:** Cross-repo with the `price-scout` project. The governing architecture decision lives
there: `price-scout/planning/decisions/D3-price-scout-as-user-facing-app.md` (Price Scout is a
standalone user-facing app that delegates to this orchestrator via a feature-flagged `/events`
client). The earlier D2 framing — orchestrator owns the browser — is superseded.

> **This plan was rewritten 2026-06-22.** The previous version assumed the orchestrator does the
> scraping (Playwright `SearchNode → ExtractNode → RankNode` running inside a Celery worker). That
> is **obsolete.** Under D3, **Price Scout scrapes, enriches, and ranks entirely on its own** and
> sends this orchestrator an *already-finished* result. The orchestrator does **no** browser work,
> has **no** marketplace adapters, and carries **no** Playwright-in-Celery concern. Its job is to
> **ingest the finished result and reason over it.**

## Goal

Register a `PRICE_SCOUT` workflow that accepts a completed Price Scout search (the ranked winner +
clean candidates for one product across one or more marketplaces) and produces a structured
**analysis verdict** — is this a good deal, is the price anomalous, what's the recommendation —
using one LLM node. The deterministic price-finding is already done upstream; this workflow adds
judgment and a persisted record.

## How Price Scout behaves (the producer side — context you need)

Price Scout is a separate FastAPI app (its own repo, runs on **:8000**). On every completed search
it calls a feature-flagged client (`price_scout/orchestrator_client.py`) that does a
fire-and-forget `httpx.post` to this orchestrator. Key facts that constrain our side:

- **The flag defaults OFF** (`PRICE_SCOUT_EMIT_EVENTS`). Nothing fires until both (a) this endpoint
  is live and (b) the operator flips the flag. So we can build and ship the workflow with zero risk
  to the running Price Scout app.
- **The payload is already in our envelope shape.** Price Scout's `PriceScoutEvent` is literally
  `{"workflow_type": "PRICE_SCOUT", "data": {...}}` — it `model_dump()`s straight onto our
  `EventPayload = {workflow_type: str, data: dict}`. No envelope translation is needed on either side.
- **Delivery is best-effort.** The client swallows all errors and treats any `< 300` as success, so
  our `202 Accepted` is exactly what it expects. It will **not** retry, and it must never be blocked
  — our endpoint already returns 202 immediately and processes via Celery, which fits.
- **Target URL.** The client currently defaults to `http://localhost:8000/events` (wrong — that's
  Price Scout's *own* port, and missing the trailing slash). The PS-side wiring step below fixes it
  to `http://localhost:8080/events/`. Our endpoint is mounted at `/events/` (trailing slash; a
  bare `/events` 307-redirects and can drop the POST body).

### The `data` contract (what arrives in `payload.data`)

`data` is Price Scout's `PriceScoutEventData`. Our `PriceScoutEventSchema` must mirror it
field-for-field (this orchestrator owns the canonical schema and validates against it):

```
PriceScoutEventData:
  product_name:  str                      # the raw user query
  marketplaces:  list[str]                # e.g. ["mercado_livre", "amazon"]
  winner:        EnrichedListing | None   # the per-unit-ranked pick (may be None on a blocked/empty scrape)
  candidates:    list[EnrichedListing]    # clean, non-suspect listings only (suspect/demoted are EXCLUDED upstream — D9)
```

`EnrichedListing` (the nested object — mirror all of it):

```
# raw card fields (from Listing)
  title:      str
  price:      str          # display string, e.g. "R$ 28,15"
  num:        float        # numeric price used for ranking
  url:        str          # direct product link
  was:        str          # struck-through original price, if on sale ("" otherwise)
  discount:   str          # discount-% string if present ("" otherwise)
  source:     str          # "mercado_livre" | "amazon" | ...
# enrichment fields (from enrich.enrich_listing)
  size_value:    float | None
  unit_family:   "volume" | "weight" | None
  pack:          int             # default 1
  unit_price:    float | None    # the per-unit price the ranking is based on
  unit_label:    str | None      # e.g. "R$/L"
  size_inferred: bool
  is_clean:      bool            # always True here (candidates are clean-only)
  reason:        str
```

Notes that matter for the schema/analysis:
- `winner` can be `None` (a blocked-captcha / rate-limited / empty scrape still emits an event with
  no winner). The schema must allow it and the persist/analyze nodes must handle the empty case.
- `candidates` are **clean-only** — Price Scout already dropped suspect/demoted items (D9 #1). If we
  later decide we want the demoted pool, that's a coordinated change in *both* repos' contracts.
- Ranking is by **`unit_price`** (per-unit), not absolute `num`. The analysis prompt should reason
  in per-unit terms when present, falling back to `num` when `unit_price` is None.

## Proposed shape (maps onto the existing node model)

A two-node Chain-of-Responsibility workflow (mirrors `ResearchAgentWorkflow`):

```
PersistPriceEventNode → AnalyzePriceNode (agent, terminal)
```

- **`PersistPriceEventNode`** — plain `Node` (`app/core/nodes/base.py`). Normalizes the validated
  event and stores a JSON-serializable snapshot under `nodes[self.node_name]` (use `to_jsonable`).
  No LLM. Cheap, deterministic, gives a persisted record even if the analysis node fails.
- **`AnalyzePriceNode`** — `AgentNode` (`app/core/nodes/agent.py`), `OutputType = PriceVerdictOutput`,
  Anthropic provider (latest Opus/Sonnet). Calls `run_agent_recorded()` so per-node telemetry
  (input / usage / output) lands per the data contract. System prompt loaded from a `.j2` via
  `PromptManager` — **no inline prompt text** (repo convention; see `app/prompts/*.j2`). Handle the
  `winner is None` case explicitly (verdict = "no result" rather than a hallucinated deal).

### `PriceVerdictOutput` (proposed — confirm fields)

```
PriceVerdictOutput:
  deal_quality:    "great" | "fair" | "poor" | "no_result"
  anomaly_flag:    bool          # price looks too-good / suspicious / out of expected range
  recommendation:  str           # short human-facing call, e.g. "Buy the 2L now" / "Wait"
  reasoning:       str           # 1–3 sentences citing per-unit price / sale / spread
```

## Concrete change list (this repo)

New files:
1. `app/schemas/price_scout_schema.py` — `PriceScoutEventSchema` (+ nested `EnrichedListingModel`)
   mirroring the contract above, and `PriceVerdictOutput`.
2. `app/workflows/price_scout_workflow_nodes/__init__.py`
3. `app/workflows/price_scout_workflow_nodes/persist_price_event_node.py`
4. `app/workflows/price_scout_workflow_nodes/analyze_price_node.py`
5. `app/workflows/price_scout_workflow.py` — `PriceScoutWorkflow(WorkflowSchema(...))`,
   `start=PersistPriceEventNode`, `Persist → Analyze` (terminal).
6. `app/prompts/price_scout_analysis.j2` — the analysis system prompt.

Edits:
7. `app/workflows/workflow_registry.py` — add `PRICE_SCOUT = PriceScoutWorkflow`.
8. `app/api/schema_registry.py` — add `WorkflowRegistry.PRICE_SCOUT.name: PriceScoutEventSchema`.
   (The schema-registry-completeness test fails if you register the workflow without this — good
   guardrail; do both together.)

Tests:
9. Schema validation (valid payload incl. `winner=None`; bad data → `ValidationError`).
10. `POST /events/` → 202 on a valid PRICE_SCOUT payload; 422 on unknown type / invalid data.
11. `GET /workflows/PRICE_SCOUT/graph` returns the two nodes + the edge.
12. Node-level: persist stores a serializable snapshot; analyze produces a `PriceVerdictOutput`
    (LLM mocked) and handles the empty-winner case.

Data contract:
13. **`docs/data-contract.md` → v1.1.0** (additive minor: new `PRICE_SCOUT` `workflow_type` + its
    event schema documented). Add a changelog row. Per the brain's update protocol + D20,
    **re-pin `bastion/docs/data-contract.md`** and note in both `planning/status.md` files.

## Downstream: Price Scout wiring (other repo, after this ships)

- `price_scout/orchestrator_client.py` — change `_DEFAULT_ORCHESTRATOR_URL` to
  `http://localhost:8080/events/`. No payload change (envelope already correct).
- `tests/test_orchestrator_client.py` — assert the envelope keys + that `PriceScoutEventData`
  validates against this orchestrator's `PriceScoutEventSchema` (shared fixture is ideal).
- Supersede `price-scout` decision D9 with a new append-only decision recording the live target +
  that the contract is now active.
- Flip `PRICE_SCOUT_EMIT_EVENTS=1` locally and run an e2e smoke (orchestrator on 8080, PS web on
  8000): do a search → confirm an `events` row + a `PriceVerdictOutput`.

## Open questions

- **Verdict fields** — confirm `PriceVerdictOutput` above (numeric score? explicit buy/wait signal?).
- **Watch-a-price-over-time** — still deferred. This plan is one-shot ingest+analyze. Tracking
  history / alert-on-drop would need a product-identity/dedupe key and a history store; revisit only
  if a real need appears.
- **Demoted candidates** — Price Scout sends clean-only (D9 #1). Revisit (coordinated, both repos)
  only if the analysis genuinely needs the suspect pool.

## Entry criteria

Met. Price Scout's `ml-price-finder` path is shipped end-to-end (Phases 0–4 done), selectors for
Mercado Livre + Amazon are stable, and the event producer (`orchestrator_client.py`) exists and is
dormant behind a flag.
