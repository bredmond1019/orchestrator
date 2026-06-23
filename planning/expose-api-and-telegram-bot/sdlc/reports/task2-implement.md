# Implementation Report — expose-api-and-telegram-bot-task2

**Date:** 2026-06-23
**Plan:** planning/expose-api-and-telegram-bot/tasks.md
**Scope:** Task 2

## What Was Built or Changed

- `integrations/__init__.py` — top-level integrations package
- `integrations/telegram/__init__.py` — Telegram sub-package
- `integrations/telegram/config.py` — env-driven config with fail-fast validation for required vars; validates CF Access pair coherence
- `integrations/telegram/client.py` — `submit_event()` using `httpx`; fire-and-forget `POST /events/`; attaches `X-API-Key` and optional CF Access headers
- `integrations/telegram/bot.py` — long-poll bot; `/digest <url>` command + bare-URL shorthand; chat-id allowlist; replies "Queued ✅"; `# TODO(scale)` webhook migration marker
- `integrations/telegram/README.md` — run/deploy/extend instructions + webhook migration note
- `tests/__init__.py` — test root package (new)
- `tests/integrations/__init__.py` — integrations test package
- `tests/integrations/telegram/__init__.py` — Telegram test package
- `tests/integrations/telegram/test_client.py` — 9 httpx-only tests; always runs (no telegram dep needed)
- `tests/integrations/telegram/test_bot.py` — 16 tests guarded by `pytest.importorskip("telegram")`; covers URL validation, allowlist filter, digest handler, bare-URL handler, CF header passthrough
- `pyproject.toml` — added `[project.optional-dependencies] telegram = ["python-telegram-bot>=21"]`; added `pytest-asyncio>=1.4.0` to dev group
- `pytest.ini` — `pythonpath = app .` (was `app`) so `integrations.*` is importable; added `asyncio_mode = auto`

## Files Created or Modified

| File | Action |
|---|---|
| `integrations/__init__.py` | created |
| `integrations/telegram/__init__.py` | created |
| `integrations/telegram/config.py` | created |
| `integrations/telegram/client.py` | created |
| `integrations/telegram/bot.py` | created |
| `integrations/telegram/README.md` | created |
| `tests/__init__.py` | created |
| `tests/integrations/__init__.py` | created |
| `tests/integrations/telegram/__init__.py` | created |
| `tests/integrations/telegram/test_client.py` | created |
| `tests/integrations/telegram/test_bot.py` | created |
| `pyproject.toml` | modified |
| `pytest.ini` | modified |

## Validation Output

**Commands run:**
```
uv run python -m ruff check app/ integrations/
cd app && uv run python -c 'import main'
cd app && uv run python -c 'import worker.config'
cd app && uv run python -c 'import database.session'
cd app && uv run python -c 'import database.repository'
uv run python -m ruff check app/
uv run python -m pylint app/
uv run python -m pytest --collect-only -q
uv run python -m pytest
```

**Result:** PASSED

## Decisions and Trade-offs

- **pytest-asyncio auto mode**: Bot handlers are async (they `await` Telegram API calls). Added `pytest-asyncio` and `asyncio_mode = auto` to pytest.ini rather than rewriting handlers to be sync; this matches the python-telegram-bot v21 async API.
- **httpx mock via monkey-patch**: `test_client.py` patches `httpx.post` directly on the module under test rather than using `respx` or `pytest-httpx`. This keeps the test self-contained with no additional mock library deps while still verifying request headers, path, and payload.
- **`importorskip` guard**: Bot tests guard on `telegram` (the python-telegram-bot package name), which means they are skipped cleanly when the optional extra is absent — exactly as specified.
- **config.py not loaded at module import**: `load_config()` is a function, not a module-level object, so importing `integrations.telegram.config` does not trigger env validation. The bot only calls `load_config()` inside `main()`.

## Follow-up Work

- Tasks 3 and 4 (deploy config + docs) are out of scope for this task.
- The `# TODO(scale)` webhook migration comment in `bot.py` documents the upgrade path.

## git diff --stat

```
 integrations/__init__.py                                        |  1 +
 integrations/telegram/__init__.py                               |  1 +
 integrations/telegram/bot.py                                    |  1 +
 integrations/telegram/client.py                                 |  1 +
 integrations/telegram/config.py                                 |  1 +
 integrations/telegram/README.md                                 |  1 +
 pyproject.toml                                                  |  4 +++
 pytest.ini                                                      |  3 +-
 tests/__init__.py                                               |  1 +
 tests/integrations/__init__.py                                  |  1 +
 tests/integrations/telegram/__init__.py                         |  1 +
 tests/integrations/telegram/test_bot.py                        |  1 +
 tests/integrations/telegram/test_client.py                     |  1 +
 uv.lock                                                         | 89 +++++++++++++++++++
 planning/expose-api-and-telegram-bot/sdlc/reports/task2-implement.md | 1 +
```
