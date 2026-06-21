---
type: Plan
title: Price Scout Workflow — deferred plan
description: Deferred plan to bring the Price Scout price-finder into this orchestrator as a Python Playwright workflow (search → extract → rank → LLM pick-winner).
---

# Price Scout Workflow — deferred plan

**Status:** Deferred — not started. Pick up when ready (after the Price Scout skill has been
run end-to-end enough to harvest stable selectors and edge cases).

**Origin:** Cross-repo with the `price-scout` project. The governing architecture decision
lives there: `price-scout/planning/decisions/D2-architecture-python-playwright-orchestrator.md`.
Read that first.

## Goal

Bring the Price Scout price-finder into this orchestrator as a workflow: given an item
name/description, search a marketplace (Mercado Livre first, Amazon later), rank the cheapest
listings using the actual **sale** price, and pick a clear winner with a verifiable product
link — using an LLM only for the fuzzy judgment step.

## Why it belongs here

- The fuzzy steps (ambiguous-match resolution, value-per-unit reasoning, cross-site dedup)
  want an LLM, and this repo already hosts the agent/tool-use node infrastructure.
- **Python Playwright is first-class** (Microsoft-maintained), so scraping + LLM judgment stay
  in one stack, one test suite (`pytest`), one deploy (existing docker) — no cross-language glue.

## Proposed shape (maps onto the existing node model)

Chain-of-Responsibility nodes (mirrors `app/core/nodes/` + `app/workflows/*_nodes/`):

```
SearchNode → ExtractNode → RankNode → PickWinnerNode (agent) → RenderNode
```

- **`PriceScoutService`** in `app/services/` — owns the browser session and the deterministic
  core (navigate → extract → normalize → rank). Mirrors `ArticleExtractionService`.
- **Marketplace adapters** — one per site implementing a shared interface
  (`search_url`, card selector, `extract(card) -> Listing`, sponsored-link rule). Mercado Livre
  first; Amazon as a second adapter. Ranking/winner/render stay site-agnostic.
- **`PickWinnerNode`** — an agent node reusing `app/core/nodes/agent.py` / `tool_use.py` for
  the judgment step. The deterministic path works without it (simple lookups skip the LLM).

## Deterministic mechanics already proven (port from the skill)

These were validated by hand via `playwright-cli` and must carry into the Python adapter:

1. **Mercado Livre ad-redirect:** the first Enter from the homepage often lands on a sponsored
   container (`_Container_` / `#origin=ads`) with unrelated products — re-search from the
   results page and confirm the title is `<X> | Mercado Livre` before extracting.
2. **Sale-price scoping:** read prices inside `.poly-price__current` — discounted cards carry a
   *second* `.andes-money-amount__fraction` for the struck-through original.
3. **Verifiable links:** filter out sponsored cards — their links are
   `click1.mercadolivre.com.br` trackers, not direct product URLs.
4. **BRL parsing:** `.` = thousands, `,` = decimals.

## Caveat: Playwright in a Celery worker

- `sync_api` works in a prefork worker; install browser binaries in the worker image
  (`playwright install chromium`).
- Browser nodes are heavy — give them a dedicated queue / concurrency limit so a scrape does
  not starve light LLM tasks.

## Open questions for when we pick this up

- One-shot lookup vs. **watch-a-price-over-time** workflow (scheduling + alert-on-drop)?
- Where the result is persisted / whether it touches the shared data contract (D20).
- Amazon's heavier bot detection (CAPTCHA / headers / stealth) — scope as its own adapter spike.

## Entry criteria (do not start before)

- The `price-scout` skill (`ml-price-finder`) has been run end-to-end on Mercado Livre (and an
  Amazon stub) enough to harvest stable selectors and edge cases.
