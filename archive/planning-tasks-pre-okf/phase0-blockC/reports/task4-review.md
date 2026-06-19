# Review Report — tasks.md Task 4

**Date:** 2026-06-08
**Plan:** planning/tasks/phase0-blockC/tasks.md
**Scope:** Task 4
**Implement report:** found
**Test report:** found
**Overall verdict:** PASS

## Acceptance Criteria

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | `uv run pytest` passes with zero failures and zero errors | MET | 5 passed in 0.57s — all tests in suite pass |
| 2 | `pytest --collect-only` exits with zero errors | MET | 5 tests collected, no import errors |
| 3 | Ghost-row regression: `send_task` raise → Event table empty | MET | `test_failed_enqueue_does_not_commit_event` PASSED; session.query(Event).count() == 0 confirmed |
| 4 | Successful enqueue → one committed Event row | MET | `test_successful_enqueue_commits_event` PASSED; session.query(Event).count() == 1 confirmed |
| 5 | No new pylint/ruff errors introduced by this fix | MET | Only pre-existing errors in other files; endpoint.py adds no new violations (W0105 was pre-existing before Task 4) |
| 6 | `customer_care` workflow files untouched | MET | No changes to customer_care_workflow* files in this task |

## Fresh Test Run

**Commands run:**
```
uv run pytest --collect-only
uv run pytest -v
uv run pylint app/api/endpoint.py
uv run ruff check app/api/endpoint.py
```

**Output:**
```
# pytest --collect-only
5 tests collected

# pytest -v
tests/api/test_endpoint.py::TestEndpointGhostRow::test_failed_enqueue_does_not_commit_event PASSED
tests/api/test_endpoint.py::TestEndpointGhostRow::test_successful_enqueue_commits_event PASSED
tests/database/test_repository.py::TestExists::test_returns_true_when_row_present PASSED
tests/database/test_repository.py::TestExists::test_returns_false_when_no_row PASSED
tests/database/test_repository.py::TestExists::test_no_attribute_error_raised PASSED
5 passed in 0.57s

# pylint app/api/endpoint.py
app/api/endpoint.py:14:0: W0105: String statement has no effect (pre-existing)
(no errors attributable to Task 4)

# ruff check app/api/endpoint.py
I001 Import block is un-sorted (pre-existing — same import block existed before fix)
B008 Depends in arg default (pre-existing — Depends was already in signature before Task 4)
```

Result: PASS

## CLAUDE.md Rule Violations

None. Task 4 bypasses `GenericRepository.create()` and manages the session directly — this is explicitly called out in the task spec as intentional, required by the two-phase commit semantics.

## Issues Found

**Pre-existing ruff/pylint issues (not introduced by Task 4):**
- `app/api/endpoint.py:1` — `I001` unsorted imports: pre-existing; the `from database.repository import GenericRepository` line was in the same unsorted block before the fix. Task 4 removed that import and added nothing that changed the sort order of remaining imports.
- `app/api/endpoint.py:39` — `B008` Depends in arg default: pre-existing; `session: Session = Depends(db_session)` was in the original endpoint before any Task 4 changes.
- `app/api/endpoint.py:14` — `W0105` module docstring after imports: pre-existing per the implement report.
- Broader `pylint` exit code 30 and `ruff` 73-error count: all pre-existing issues in files not touched by Task 4 (core/task.py, core/nodes/router.py, core/nodes/agent.py, etc.).

**Implementation correctness note:**
The task spec shows an explicit `repository.session.commit()` call at the end of the fix. The actual implementation omits this call and relies on `db_session()`'s `session.commit()` after `yield`. This is correct: `db_session()` in `app/database/session.py:27` calls `session.commit()` after the route handler returns successfully, and `session.rollback()` if an exception is raised. The behavior is identical to the spec's intent.

## Verdict

PASS. The ghost-row bug is correctly fixed: the endpoint now stages the event with `session.add()` + `session.flush()` (assigns `event.id` without committing), calls `send_task`, and relies on `db_session()`'s post-yield commit. If `send_task` raises, the `db_session()` generator rolls back automatically — no orphaned row. Both regression tests pass (failure path leaves Event table empty; success path commits one row). No new errors were introduced by this fix. Pre-existing ruff/pylint issues exist in other files throughout `app/` but are not attributable to Task 4 and were present before the fix.
