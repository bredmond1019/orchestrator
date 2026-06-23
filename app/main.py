"""FastAPI application entry point.

CORS origins are driven by the ``ALLOWED_ORIGINS`` environment variable
(comma-separated list; default ``https://learn-agentic-ai.com``).

Open (unauthenticated) routes:
  - ``GET /health``   — readiness probe, publicly reachable.
  - ``GET /workflows*`` — workflow graph inspection, safe to expose.

Protected routes:
  - ``POST /events/`` — requires ``X-API-Key`` header (see ``api.security``).
"""

import os

from api.router import router as process_router
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_DEFAULT_ORIGINS = "https://learn-agentic-ai.com"


def _get_allowed_origins() -> list[str]:
    """Return the list of allowed CORS origins from env, with a safe default."""
    raw = os.environ.get("ALLOWED_ORIGINS", _DEFAULT_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(
    title="Agentic Orchestration API",
    description=(
        "Event-driven AI pipeline framework: "
        "FastAPI → Celery → Workflow DAG → TaskContext."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(process_router)
