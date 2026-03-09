from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db_session

router = APIRouter(prefix="/_obs", tags=["Observability"])

HTTP_REQUESTS = Counter("http_requests_total", "Total HTTP requests", ["method", "path", "status"])
HTTP_LATENCY = Histogram("http_request_latency_seconds", "HTTP request latency", ["method", "path"])


@router.get(
    "/health",
    summary="Health check",
    description="Liveness probe endpoint.",
)
# PUBLIC_INTERFACE
async def health() -> dict:
    """Return basic liveness."""
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Readiness check",
    description="Readiness probe endpoint. Validates DB connectivity.",
)
# PUBLIC_INTERFACE
async def ready(db: AsyncSession = Depends(get_db_session)) -> dict:
    """Validate dependencies are reachable (DB)."""
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description="Prometheus scrape endpoint.",
)
# PUBLIC_INTERFACE
async def metrics() -> Response:
    """Expose Prometheus metrics."""
    data = generate_latest()
    return Response(content=data, media_type=CONTENT_TYPE_LATEST)
