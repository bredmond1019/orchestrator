"""FastAPI application entry point."""

from api.router import router as process_router
from fastapi import FastAPI

app = FastAPI(
    title="Agentic Orchestration API",
    description=(
        "Event-driven AI pipeline framework: "
        "FastAPI → Celery → Workflow DAG → TaskContext."
    ),
    version="0.1.0",
)
app.include_router(process_router)
