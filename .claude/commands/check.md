# Check — Run the full test suite and verify the app and worker construct cleanly.

## Instructions

1. Run the full test suite:
   ```
   uv run pytest
   ```
2. Verify the ASGI app object constructs (no port binding):
   ```
   cd app && uv run python -c "from main import app"
   ```
3. Verify the Celery app object constructs (no worker process):
   ```
   cd app && uv run python -c "from worker.config import celery_app"
   ```
4. Report failures concisely: list failing test names, import errors, or construction errors. If everything passes, say so in one line.

## Context / Files to Read

None — this command runs live commands only.
