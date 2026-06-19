# Implementation Report — phase0-blockD-task10

**Date:** 2026-06-10
**Plan:** planning/tasks/phase0-blockD/tasks.md
**Scope:** Task 10 — Clean API Contract

## What Was Built or Changed
- Created `app/api/health.py` — `GET /health` returning a typed `HealthResponse(status, version)`.
- Created `app/api/schema_registry.py` — `SCHEMA_MAP` mapping `WorkflowRegistry` enum names to event schema classes (CUSTOMER_CARE, CONTENT_PIPELINE).
- Created `app/api/models.py` — typed request/response models: `EventPayload(workflow_type, data)` and `TaskAcceptedResponse(task_id, message)`.
- Rewrote `app/api/endpoint.py` — replaced the hardcoded `CustomerCareEventSchema` handler with a generic dispatcher: looks up the schema by `workflow_type`, returns 422 for unknown types or invalid `data`, persists via flush-before-send (no ghost row), and returns a typed `TaskAcceptedResponse` body.
- Updated `app/api/router.py` — includes the new health router with module docstring on line 1.
- Updated `app/main.py` — added OpenAPI metadata (`title`, `description`, `version="0.1.0"`).
- Rewrote `tests/api/test_endpoint.py` — covers valid dispatch (202), unknown workflow_type (422), invalid data (422), ghost-row prevention (500, 0 rows), successful commit (202, 1 row), and health (200).

## Files Created or Modified
| File | Action |
|---|---|
| app/api/health.py | created |
| app/api/schema_registry.py | created |
| app/api/models.py | created |
| app/api/endpoint.py | modified |
| app/api/router.py | modified |
| app/main.py | modified |
| tests/api/test_endpoint.py | modified |

## Validation Output
**Commands run:**
```
uv run pytest
uv run ruff check app/
uv run pylint app/
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
cd app && uv run python -c "from workflows.workflow_registry import WorkflowRegistry; WorkflowRegistry.CONTENT_PIPELINE"
```
**Results:**
```
pytest:  174 passed in 0.84s
ruff:    All checks passed!
pylint:  Your code has been rated at 10.00/10 (previous run: 10.00/10, +0.00)
imports: ACCEPTANCE IMPORTS OK (main app, celery_app, CONTENT_PIPELINE all import cleanly)
endpoint tests: 6 passed (valid 202, unknown 422, invalid-data 422, ghost-row 500, commit 202, health 200)
```
Status: PASSED

## Decisions and Trade-offs
- Validation of `data` against the resolved schema raises 422 with `exc.errors()` as detail, matching FastAPI's native 422 shape for body validation, so unknown-type and bad-data both surface as 422 per spec.
- Kept the flush-before-send ghost-row fix (Known Bug in `api/endpoint.py`): `session.add` + `session.flush` inside the request, `send_task` after; a send failure rolls back via `db_session`, leaving zero rows.
- Health router mounted without a prefix so `GET /health` is reachable at the root, satisfying the acceptance criterion.
- Added a non-spec `test_invalid_data_returns_422` case to exercise the schema-validation branch (acceptance only required unknown-type and health; this strengthens coverage without scope creep).

## Follow-up Work
- None for Task 10. The `data: dict` field on `EventPayload` is intentionally untyped at the envelope level; per-workflow typing is enforced by `SCHEMA_MAP` validation. Future workflows just add a `SCHEMA_MAP` entry.

## git diff --stat
```
 app/api/endpoint.py        | 97 +++++++++++++++++++++++-----------------------
 app/api/router.py          | 13 ++-----
 app/main.py                | 11 +++++-
 tests/api/test_endpoint.py | 71 +++++++++++++++++++++------------
 4 files changed, 108 insertions(+), 84 deletions(-)
```
(New untracked files not shown by diff --stat: app/api/health.py, app/api/schema_registry.py, app/api/models.py)
