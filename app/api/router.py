"""API router — event ingestion and health check."""

from fastapi import APIRouter

from api import endpoint, graph, health

router = APIRouter()
router.include_router(endpoint.router, prefix="/events", tags=["events"])
router.include_router(health.router, tags=["health"])
router.include_router(graph.router, tags=["workflows"])
