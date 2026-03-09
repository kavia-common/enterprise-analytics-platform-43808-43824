from __future__ import annotations

import uuid
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routers import (
    dashboards_router,
    ingestion_router,
    observability_router,
    realtime_router,
    saved_views_router,
    widgets_router,
)
from src.api.routers.auth import router as auth_router
from src.core.config import get_settings
from src.core.db import get_db_session
from src.core.deps import AuthContext, get_auth_context
from src.core.models import Role, UserRole
from src.core.schemas import ErrorResponse, UserResponse
from src.middleware.audit import AuditLoggingMiddleware

openapi_tags: List[Dict[str, Any]] = [
    {"name": "Auth", "description": "Authentication endpoints (signup/login)."},
    {"name": "Dashboards", "description": "CRUD APIs for dashboards."},
    {"name": "Widgets", "description": "CRUD APIs for widgets within dashboards."},
    {"name": "Saved Views", "description": "Saved filter/view configurations per dashboard."},
    {"name": "Ingestion", "description": "Data ingestion endpoints for analytics events."},
    {
        "name": "WebSocket",
        "description": "Real-time websocket endpoint. Connect to /ws/realtime?token=<JWT> and subscribe via messages.",
    },
    {"name": "Observability", "description": "Health/readiness/metrics endpoints."},
]

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    description="Enterprise-grade, multi-tenant analytics dashboard backend (RBAC + tenancy enforced).",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AuditLoggingMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Return consistent error payloads without leaking internals."""
    return ErrorResponse(detail=str(exc.detail)).model_dump(), exc.status_code  # FastAPI will normalize


@app.middleware("http")
async def attach_audit_context(request: Request, call_next):
    """Attach audit-related fields to request.state if auth headers are present.

    This best-effort approach ensures audit logs contain org/workspace/user when possible.
    """
    # Default: do not authenticate here (avoid double work). We only parse if Authorization exists
    # and ignore failures (do not change request outcome).
    auth = request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        # Lightweight decode in deps is strict; here we only try to stash ids for audit middleware
        token = auth.split(" ", 1)[1].strip()
        try:
            from src.core.security import decode_token

            payload = decode_token(token)
            sub = payload.get("sub")
            org_id = payload.get("org_id") or request.headers.get("X-Organization-Id")
            ws_id = payload.get("workspace_id") or request.headers.get("X-Workspace-Id")
            if sub:
                request.state.user_id = uuid.UUID(str(sub))
            if org_id:
                request.state.organization_id = uuid.UUID(str(org_id))
            if ws_id:
                request.state.workspace_id = uuid.UUID(str(ws_id))
        except Exception:
            pass

    return await call_next(request)


@app.get(
    "/auth/me",
    response_model=UserResponse,
    tags=["Auth"],
    summary="Get current user",
    description="Return authenticated user profile and role names.",
    responses={401: {"model": ErrorResponse}},
)
# PUBLIC_INTERFACE
async def me(ctx: AuthContext = Depends(get_auth_context), db: AsyncSession = Depends(get_db_session)) -> UserResponse:
    """Return the currently authenticated user profile."""
    # Load role names
    stmt = (
        select(Role.name)
        .select_from(UserRole)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == ctx.user.id)
    )
    roles = [r[0] for r in (await db.execute(stmt)).all()]
    user_dict = {
        "id": ctx.user.id,
        "organization_id": ctx.user.organization_id,
        "email": ctx.user.email,
        "full_name": ctx.user.full_name,
        "is_active": ctx.user.is_active,
        "created_at": ctx.user.created_at,
        "roles": roles,
    }
    return UserResponse.model_validate(user_dict)


# Keep auth signup/login under /auth/*
app.include_router(auth_router)
app.include_router(dashboards_router)
app.include_router(widgets_router)
app.include_router(saved_views_router)
app.include_router(ingestion_router)
app.include_router(observability_router)
app.include_router(realtime_router)


@app.get(
    "/",
    tags=["Observability"],
    summary="Root health check",
    description="Legacy health check endpoint (liveness). Prefer /_obs/health.",
)
# PUBLIC_INTERFACE
def root_health_check():
    """Simple liveness endpoint."""
    return {"message": "Healthy"}
