---
type: ImplementationReport
title: Implementation Report — expose-api-and-telegram-bot Task 1
description: API key auth + CORSMiddleware added to FastAPI app; security dependency gates POST /events/.
---

# Implementation Report — expose-api-and-telegram-bot-task1

**Date:** 2026-06-23
**Plan:** planning/expose-api-and-telegram-bot/tasks.md
**Scope:** Task 1 — API key auth + CORS (API hardening)

## What Was Built or Changed

- `app/api/security.py` (new): `require_api_key` FastAPI dependency. Reads `ORCHESTRATION_API_KEY`
  from env at request time; returns 503 if unset (fail-closed), 401 if header missing or mismatched.
  Uses `hmac.compare_digest` to prevent timing-based side-channel attacks. Header declared
  `str | None = Header(None)` so missing header yields 401 (not FastAPI's default 422).
- `app/main.py` (edit): Added `CORSMiddleware` with origins from `ALLOWED_ORIGINS` env
  (comma-split; default `https://learn-agentic-ai.com`). Docstring updated to document which
  routes are open vs. protected.
- `app/api/endpoint.py` (edit): `POST /events/` router now carries
  `dependencies=[Depends(require_api_key)]`. The flush-before-send_task ghost-row guard is
  preserved unchanged.
- `tests/api/test_security.py` (new): 7 unit tests covering all auth scenarios and schema
  registry completeness.
- `tests/__init__.py` (new): empty init to make `tests/` a package.
- `tests/api/__init__.py` (new): empty init to make `tests/api/` a package.

## Files Created or Modified

| File | Action |
|---|---|
| `app/api/security.py` | created |
| `app/main.py` | modified |
| `app/api/endpoint.py` | modified |
| `tests/api/test_security.py` | created |
| `tests/__init__.py` | created |
| `tests/api/__init__.py` | created |

## Validation Output

**Commands run:**
```
uv run python -m ruff check app/
uv run python -m pylint app/
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run python -m pytest --collect-only -q
uv run python -m pytest
```

**Result:** PASSED

## Decisions and Trade-offs

- **`str | None = Header(None)` vs `str = Header(...)`**: FastAPI returns 422 when a required
  header is absent. Declaring the header optional and checking for `None` in the dependency body
  produces the semantically correct 401 response for a missing auth header.
- **503 for unset env var**: Distinguishes operator misconfiguration from an invalid key;
  fail-closed prevents the app from accidentally serving unauthenticated requests if the env
  was not injected. This mirrors the pattern in `app/services/embedding_service.py`.
- **Routes left open**: `GET /health` and `GET /workflows*` carry no auth dependency so they
  remain reachable for monitoring probes without credentials. Documented in the module docstring.
- **CORS at app level**: `CORSMiddleware` is added in `main.py` (not per-router) so it applies
  to all routes including health and workflow graph endpoints, which is the correct behavior.

## Follow-up Work

- Task 3 will add `ORCHESTRATION_API_KEY` and `ALLOWED_ORIGINS` to both `.env.example` files.
- Task 4 will document `require_api_key` in `docs/api-reference.md` and the CORS middleware in
  `docs/configuration.md`.

## git diff --stat

```
 app/api/endpoint.py |  3 ++-
 app/main.py         | 34 +++++++++++++++++++++++++++++++++-
 2 files changed, 35 insertions(+), 2 deletions(-)
```
