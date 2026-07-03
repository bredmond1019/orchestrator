---
type: TaskSpec
title: "Task Spec — OR.V: One graph resolver (load_brain_edges.py reads mev's resolved edges)"
description: Refactor scripts/load_brain_edges.py to consume mev emit-graph v2's resolved target_node_id/target_doc_id fields directly instead of re-resolving to_ref locally.
doc_id: or-v-graph-resolver-cleanup-tasks
layer: [engine]
project: orchestrator
status: active
keywords: [OR.V, brain_edges, emit-graph, graph resolver, load_brain_edges, mev]
related: [status, master-plan]
---

# Task Spec — OR.V: One graph resolver

**Status:** Not started · **Last run:** never

## Goal
Make `scripts/load_brain_edges.py` read mev `emit-graph` v2's already-resolved `target_node_id`/`target_doc_id` edge fields directly, deleting its duplicate local resolution (`build_node_maps()` + `resolve_ref()`), so edge resolution lives in exactly one place (mev).

## Context Pointers
- **Block:** `OR.V` — "One graph resolver — load_brain_edges.py cleanup (consumes MV.3B.V)" (`planning/state.json` → Wave 0). Last piece before `OR.H`/embedding: the graph is read directly from mev's output.
- **Upstream (Done):** mev `MV.3B.V` shipped `emit-graph` **v2** — `edges[]` now carry `target_node_id` (qualified `scope:doc_id`, or `null` when dangling/leaf) and `target_doc_id` (authored `doc_id`, non-null exactly when `target_node_id` is), and the top-level `version` is `"2"`. See `../mev/docs/cli.md` § `emit-graph` → *Output shape*. mev resolves edges with its own `resolve_edge()` and has a parity test asserting the exported fields match `check_graph`'s diagnostics.
- **Files today:** `scripts/load_brain_edges.py` (loader — the `build_node_maps()`/`resolve_ref()`/`build_edge_rows()` chain re-derives what mev now ships); `tests/test_load_brain_edges.py` (19 tests, several targeting the soon-deleted helpers); `app/database/brain_edge.py` (`BrainEdge` model — column set is unchanged, `target_node_id`/`target_doc_id`/`source_doc_id`/`scope` line up 1:1 with mev's fields).
- **Docs referencing the resolution behavior:** `docs/scripts.md` § `load_brain_edges.py` (*Resolution:* paragraph), `docs/api-reference.md` (`BrainEdge` loader description + test count).
- **CLAUDE.md rules in play:** rule 1 (behaviour change ships with tests), rule 7 (persistence stays injected via `db_session` — unchanged here), code-style rules (module docstring line 1, `raise ... from e`, `encoding="utf-8"`, no f-string logging).

## Step-by-Step Tasks
See `tasks.json` in this directory — the task list is defined there, not here.

## Acceptance Criteria
- `scripts/load_brain_edges.py` no longer defines `build_node_maps()` or `resolve_ref()`; neither name appears in the file.
- `build_edge_rows()` sets each row's `target_node_id` / `target_doc_id` from `edge["target_node_id"]` / `edge["target_doc_id"]` (read straight off the payload), **not** from any local target resolution.
- The source node is still looked up in `nodes[]` by `edge["from"]` so `source_doc_id` and `scope` are populated; an edge whose **source** is unresolvable is still skipped and logged.
- An edge with `target_node_id: null` (dangling or leaf) still produces a row with `target_node_id`/`target_doc_id` `None` — never dropped.
- The loader depends on the resolved-edge schema: a payload whose `version` is not `"2"` raises a clear `ValueError` naming the expected version (guards against silently loading a pre-v2 payload as all-dangling).
- `tests/test_load_brain_edges.py` uses a v2 fixture (`version: "2"`, edges carrying `target_node_id`/`target_doc_id`), imports no deleted symbols, and still covers: bare/scoped target read-through, dangling-target retention, unresolvable-source skip, idempotent reload, and both `main()` input paths.
- `docs/scripts.md` and `docs/api-reference.md` describe the loader as reading mev's resolved fields (no longer resolving `to_ref` itself); the api-reference test count matches the new suite.
- All gated checks in `planning/harness.json` pass (pytest, ruff net-new-lint, pylint 10.00/10, pytest-count not decreased).

## Validation Commands
```
uv run python -m pytest tests/test_load_brain_edges.py
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest
```
<!-- scripts/ is outside app/, so ruff/pylint gates cover app/ only; the targeted + full pytest runs are the authoritative gate for this script. -->

## Notes
- **Version guard (decision folded into AC):** the pre-refactor loader was deliberately version-agnostic (`validate_payload` did not check `version`) so a future mev schema bump wouldn't break it. That tolerance is now unsafe — the loader *depends* on v2's resolved fields, and a v1 payload (no target fields) would silently load every edge as dangling. So this spec adds a minimal `version == "2"` guard. Revisit if mev ships a v3 that is a superset (loosen to `>= 2`).
- `build_node_maps()` returned `(id_map, doc_id_map)`; only the source-side `id_map` survives (needed for `source_doc_id`/`scope`). Inline it as a simple `{n["id"]: n for n in nodes if n.get("id")}` rather than keeping a named helper, per the block's "delete build_node_maps()" intent.
- Leaf targets: mev sets `target_node_id: null` for leaf (doc-id-less) targets as well as true danglers. Reading the field directly preserves the old behavior (local `resolve_ref` only matched doc_id-bearing nodes, so leaves were null before too).

## Amendment Log
<!-- Append-only. Pipeline stages append one dated line here when they deviate from the spec. -->
_No amendments yet._
