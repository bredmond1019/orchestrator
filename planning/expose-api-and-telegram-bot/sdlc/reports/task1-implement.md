---
type: ImplementationReport
title: Implementation Report — expose-api-and-telegram-bot Task 1
description: API key auth + CORSMiddleware added to FastAPI app; security dependency gates POST /events/; test_endpoint.py updated to bypass auth in dispatch tests.
---

# Implementation Report — expose-api-and-telegram-bot-task1

**Date:** 2026-06-23
**Plan:** planning/expose-api-and-telegram-bot/tasks.md
**Scope:** Task 1 — API key auth + CORS (API hardening)

## What Was Built or Changed

- `app/api/security.py` (already present from prior merge): `require_api_key` FastAPI dependency.
  Reads `ORCHESTRATION_API_KEY` from env at request time; returns 503 if unset (fail-closed), 401
  if header is missing or mismatched. Uses `hmac.compare_digest` for timing safety.
- `app/main.py` (already present from prior merge): `CORSMiddleware` with origins from
  `ALLOWED_ORIGINS` env (comma-split; default `https://learn-agentic-ai.com`). Open vs. protected
  routes documented in module docstring.
- `app/api/endpoint.py` (already present from prior merge): `POST /events/` router carries
  `dependencies=[Depends(require_api_key)]`. Flush-before-send_task ghost-row guard preserved.
- `tests/api/test_security.py` (already present from prior merge): 7 unit tests covering all auth
  scenarios (503/401/202) and schema registry completeness.
- `tests/api/test_endpoint.py` (modified in this worktree): Added `require_api_key` dependency
  override to the `endpoint_context` fixture so existing dispatch/DB/Celery tests bypass auth.
  Auth-specific coverage lives in `test_security.py`. Also added the import.

Note: the worktree was initialized as a sparse checkout that excluded `tests/`. Running
`git sparse-checkout add tests` restored the directory before any changes were made.

## Files Created or Modified

| File | Action |
|---|---|
| `app/api/security.py` | present (from prior merge into base branch) |
| `app/main.py` | present (from prior merge into base branch) |
| `app/api/endpoint.py` | present (from prior merge into base branch) |
| `tests/api/test_security.py` | present (from prior merge into base branch) |
| `tests/api/test_endpoint.py` | modified — auth bypass in fixture |
| `planning/expose-api-and-telegram-bot/sdlc/reports/task1-implement.md` | updated |

## Validation Output

**Commands run:**
```
uv run python -m ruff check app/
cd app && uv run python -c 'import main'
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
```

**Result:** PASSED

## Decisions and Trade-offs

- **Auth bypass via dependency override**: `test_endpoint.py` dispatch tests focus on payload
  validation, DB commit, and Celery enqueue — not auth. Using FastAPI's dependency override to
  bypass `require_api_key` in those tests cleanly separates concerns. Auth tests belong in
  `test_security.py` and remain intact.
- **`str | None = Header(None)`**: Declaring the header optional at the FastAPI level so missing
  header produces 401 (not FastAPI's default 422 for required headers). The None check in the
  dependency body produces the correct response code.
- **503 for unset env var**: Distinguishes operator misconfiguration from a bad key; fail-closed
  prevents accidental unauthenticated access if env var wasn't injected.
- **Routes left open**: `GET /health` and `GET /workflows*` have no auth dependency so monitoring
  probes work without credentials. Documented in the module docstring.

## Follow-up Work

- Task 3 will add `ORCHESTRATION_API_KEY` and `ALLOWED_ORIGINS` to both `.env.example` files.
- Task 4 will document `require_api_key` in `docs/api-reference.md` and the CORS middleware in
  `docs/configuration.md`.

## git diff --stat

```
 tests/api/test_endpoint.py | 5 +++++
 1 file changed, 5 insertions(+)
```
