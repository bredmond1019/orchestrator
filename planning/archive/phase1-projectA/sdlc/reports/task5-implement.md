# Implementation Report — phase1-projectA-task5

**Date:** 2026-06-20
**Plan:** planning/phase1-projectA/tasks.md
**Scope:** Task 5

## What Was Built or Changed
- `app/workflows/content_pipeline_workflow_nodes/digest_renderer.py` — pure-function static-HTML renderer (no DB, no node imports): `render_artifact_page` writes one dumb static page per item into `output_dir/<category>/<artifact_id>.html`; `regenerate_category_index` rewrites `index.html` linking every page in the category. Includes `_esc` HTML escaping and `_render_list` helpers. No JS/search/tagging (D22). `open(..., encoding="utf-8")`.
- `app/workflows/content_pipeline_workflow_nodes/storage_node.py` — `StorageNode(Node)`: for every item it (a) embeds the summary text at write time via `EmbeddingService().embed_text(...)`, (b) persists a `LearningArtifact` through `GenericRepository` via the shared `db_session` factory inside the single `_persist` seam (deployment-agnostic; connection string comes from `DatabaseUtils`/env per rule 7), and (c) writes the static HTML page + regenerates the category index. Output dir from `CONTENT_DIGEST_DIR` env (not hardcoded). Reads `SummaryOutput` via `task_context.get_node_output("SummarizerNode")["result"]`.
- `tests/workflows/content_pipeline/test_storage_node.py` — 7 hermetic tests (mock embedding service + captured `_persist` + `tmp_path` dir): 1024-dim embedding persisted, embedding written at write time, HTML page written, category index regenerated, node output recorded, YouTube source-type derivation, renderer escaping/index linking.

## Files Created or Modified
| File | Action |
|---|---|
| app/workflows/content_pipeline_workflow_nodes/digest_renderer.py | created |
| app/workflows/content_pipeline_workflow_nodes/storage_node.py | created |
| tests/workflows/content_pipeline/test_storage_node.py | created |

## Validation Output
**Commands run:**
```
cd app && uv run python -c 'import workflows.content_pipeline_workflow_nodes.storage_node'  -> OK
cd app && uv run python -c 'import main' / 'import worker.config' / 'import database.session' / 'import database.repository'  -> all OK
uv run python -m ruff check app/  -> All checks passed
uv run python -m pylint app/  -> 10.00/10
uv run python -m pytest  -> 280 passed
uv run python -m pytest --collect-only -q  -> 280 tests collected
uv run python -m pytest tests/workflows/content_pipeline/test_storage_node.py -q  -> 7 passed
```
**Result:** PASSED

Note: `cd app && alembic upgrade head` is the only validation command not run green here — it fails on `connection refused` because no local Postgres is running. That is environmental and owned by Task 2 (migrations were not touched by this task); the downstream Test stage runs it against a live DB.

## Decisions and Trade-offs
- **`get_node_output("SummarizerNode")["result"]` (no `.output`).** The breakdown pseudocode read `["result"].output`, but the merged `SummarizerNode` stores the `SummaryOutput` directly via `update_node(node_name=..., result=result.output)`, so the value under `"result"` is already the `SummaryOutput`. Matched the actual upstream contract and seeded tests accordingly.
- **`id=task_context.event.artifact_id` set at construction.** The `LearningArtifact.id` column default (`uuid.uuid4`) only fires at INSERT, so `artifact.id` would be `None` when `_persist` is monkeypatched (no flush) — breaking the HTML filename and the recorded `artifact_id`. The Task 1 event schema exposes `artifact_id` as "the stable identity used when the LearningArtifact is persisted"; using it gives a stable id immediately and ties the digest filename to the event identity.
- **`source_type` derived from which fetch node ran.** Fetch nodes (Task 3) do not stamp `source_type`; a `FetchTranscriptNode` output implies `youtube`, otherwise `article`, with an explicit `source_type` on the fetch output winning. This keeps the artifact correct for YouTube sources rather than defaulting everything to `article`.
- **Persistence seam.** `_persist` is the single persistence method using the framework's `db_session` factory (same pattern the worker uses); tests monkeypatch it so no real DB is touched. Task 7 wires the workflow/worker boundary consistently.
- **Test path.** Placed under `tests/workflows/content_pipeline/test_storage_node.py` per the tasks.md file-ownership line (the package `__init__.py` already exists), rather than the breakdown's `tests/workflows/test_content_storage_node.py`.

## Follow-up Work
- Task 7 wires `SummarizerNode → StorageNode → BlogDecisionRouterNode` into the workflow graph and confirms the repository-injection boundary; documenting `CONTENT_DIGEST_DIR` in `app/.env.example` is deferred to Task 7 (shared file, kept out of this task's set to avoid a merge collision).

## git diff --stat
```
 .../digest_renderer.py                             | 107 +++++++++++++++
 .../storage_node.py                                | 110 +++++++++++++++
 .../content_pipeline/test_storage_node.py          | 150 +++++++++++++++++++++
 3 files changed, 367 insertions(+)
```
