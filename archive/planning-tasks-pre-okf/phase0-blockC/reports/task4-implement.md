# Implementation Report — tasks.md Task 4

**Date:** 2026-06-08
**Plan:** planning/tasks/phase0-blockC/tasks.md
**Scope:** Task 4

## What Was Built or Changed

- Fixed ghost-row bug in `app/api/endpoint.py`: replaced `repository.create(obj=event)` (which committed before `send_task`) with `session.add(event)` + `session.flush()`. The row is now staged within the open transaction; `db_session()` rolls back automatically if `send_task` raises — no orphaned row possible.
- Removed the `GenericRepository` instantiation and import from the endpoint; the endpoint now manages the session directly since it requires two-phase commit semantics the generic method doesn't model.
- Created `tests/api/test_endpoint.py` with two regression tests:
  - `test_failed_enqueue_does_not_commit_event` — mocks `send_task` to raise; asserts 500 response and empty `Event` table.
  - `test_successful_enqueue_commits_event` — mocks `send_task` to return successfully; asserts 202 response and one committed `Event` row.
- Used `StaticPool` + `check_same_thread=False` in the test engine to share the in-memory SQLite connection across FastAPI's sync thread pool.

## Files Created or Modified

| File | Action |
|---|---|
| app/api/endpoint.py | modified |
| tests/api/test_endpoint.py | created |

## Validation Output

**Commands run:**
```
uv run pytest tests/api/test_endpoint.py -v
uv run pytest -v
cd app && uv run python -c "from main import app"
cd app && uv run python -c "from worker.config import celery_app"
cd app && uv run python -c "from database.session import Base, db_session"
cd app && uv run python -c "from api.endpoint import handle_event"
uv run pylint app/api/endpoint.py
```

**Results:**
```
tests/api/test_endpoint.py::TestEndpointGhostRow::test_failed_enqueue_does_not_commit_event PASSED
tests/api/test_endpoint.py::TestEndpointGhostRow::test_successful_enqueue_commits_event PASSED
tests/database/test_repository.py::TestExists::test_returns_true_when_row_present PASSED
tests/database/test_repository.py::TestExists::test_returns_false_when_no_row PASSED
tests/database/test_repository.py::TestExists::test_no_attribute_error_raised PASSED

5 passed in 0.57s

app/api/endpoint.py rated at 9.52/10
(W0105 is pre-existing — the module docstring placed after imports, not introduced here)
```
Status: PASSED

## Decisions and Trade-offs

- **Direct session management vs. `GenericRepository.create()`:** The task spec calls this out explicitly: the endpoint bypasses `GenericRepository` and manages the session directly because it needs two-phase commit semantics (stage → enqueue → commit only on success). This is intentional. `GenericRepository.create()` is a convenience method that commits immediately; it's not the right tool when the commit must be conditional.
- **`StaticPool` for SQLite in tests:** FastAPI runs sync route handlers in a thread pool executor. SQLite connections are not thread-safe by default. `StaticPool` + `check_same_thread=False` is the standard pattern for sharing an in-memory SQLite database across threads in tests.
- **`raise_server_exceptions=False` on `TestClient`:** Required so that when `send_task` raises and the endpoint propagates an unhandled exception, the test receives a 500 response object rather than having the exception re-raised into the test. Dependency cleanup (rollback) runs server-side before the response is returned, so the database state is correct when the assertion runs.

## Follow-up Work

- None for Task 4. Tasks 5–13 cover the remaining bug fixes and the full test suite.

## git diff --stat

```
 app/api/endpoint.py | 13 +++++--------
 1 file changed, 5 insertions(+), 8 deletions(-)+
tests/api/test_endpoint.py (new file, 74 lines)
```
