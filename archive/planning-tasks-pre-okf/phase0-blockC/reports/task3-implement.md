# Fix Pass 1 — phase0-blockC.md Task 3

**Date:** 2026-06-08
**Plan:** planning/tasks/phase0-blockC.md
**Scope:** Task 3
**Fix pass:** 1
**Review report consumed:** planning/tasks/reports/phase0-blockC-task3-review.md
**Prior verdict:** PARTIAL

## Failures Addressed

| # | Failing Criterion / Issue | Fix Applied |
|---|---|---|
| 1 | `session.py:11 C0103` — `_engine` not UPPER_CASE (invalid-name) | Renamed `_engine` → `_ENGINE`; updated all references in `_get_engine()` |
| 2 | `session.py:15 W0603` — Using the global statement (global-statement) | Added `# pylint: disable=global-statement` inline on the `global _ENGINE` line |
| 3 | `config.py:20 C0303` — Trailing whitespace on blank line (trailing-whitespace) | Removed trailing spaces from the blank line inside `get_redis_url()` |

## Files Created or Modified

| File | Action |
|---|---|
| app/database/session.py | modified |
| app/worker/config.py | modified |
| tests/conftest.py | modified (prior pass — unchanged this fix) |

## Validation Output

**Commands run:**
```
uv run pylint app/database/session.py app/worker/config.py
uv run pylint app/
uv run pytest -v
cd app && uv run python -c "from database.session import Base, db_session; print('session: OK')"
cd app && uv run python -c "from worker.config import celery_app; print('worker config: OK')"
```

**Results:**
```
-------------------------------------------------------------------
Your code has been rated at 10.00/10 (previous run: 9.19/10, +0.81)
Exit: 0

(full app/ run: pre-existing issues in other files, exit 30 — no new Task 3 violations)

============================= test session starts ==============================
platform darwin -- Python 3.12.13, pytest-9.0.3, pluggy-1.6.0
configfile: pytest.ini
testpaths: tests
collected 3 items

tests/database/test_repository.py::TestExists::test_returns_true_when_row_present PASSED
tests/database/test_repository.py::TestExists::test_returns_false_when_no_row PASSED
tests/database/test_repository.py::TestExists::test_no_attribute_error_raised PASSED
3 passed in 0.02s

session: OK
worker config: OK
```
Status: PASSED

## Changes Made

- `app/database/session.py:11` — renamed module-level sentinel from `_engine` to `_ENGINE` (UPPER_CASE satisfies pylint C0103)
- `app/database/session.py:14–18` — updated all references from `_engine` to `_ENGINE`; added `# pylint: disable=global-statement` inline on the `global` line
- `app/worker/config.py:20` — removed trailing whitespace from blank line inside `get_redis_url()`

## Decisions and Trade-offs

- Chose inline `# pylint: disable=global-statement` over refactoring to a mutable container (`_engine_holder = [None]`) — the global pattern is already in place and the disable comment is the minimal targeted fix.
- Renamed to `_ENGINE` (UPPER_CASE) rather than adding another disable comment — cleaner and consistent with pylint's expectation for module-level names.

## git diff --stat

```
 app/database/session.py | 24 +++++++++++-------------
 app/worker/config.py    | 14 +++++++++++---
 tests/conftest.py       | 23 ++++++++++++++++++++++-
 3 files changed, 44 insertions(+), 17 deletions(-)
```
