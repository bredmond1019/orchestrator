# Check — Lint, run the full test suite, and verify the app and worker construct cleanly.

## Instructions

1. Run the linter:
   ```
   uv run pylint app/
   ```
2. Run the full test suite:
   ```
   uv run pytest
   ```
3. Verify the ASGI app object constructs (no port binding):
   ```
   cd app && uv run python -c "from main import app"
   ```
4. Verify the Celery app object constructs (no worker process):
   ```
   cd app && uv run python -c "from worker.config import celery_app"
   ```
5. Report failures concisely: list pylint errors, failing test names, or construction errors. If everything passes, say so in one line.

## Context / Files to Read

None — this command runs live commands only.
