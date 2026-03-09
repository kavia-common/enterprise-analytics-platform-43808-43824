from __future__ import annotations

import time
import uuid
from typing import Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.db import ASYNC_SESSION_FACTORY
from src.core.models import AuditLog


def _safe_user_agent(user_agent: Optional[str]) -> Optional[str]:
    if not user_agent:
        return None
    # Truncate to reduce risk of log injection / huge values
    return user_agent[:500]


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """Persist an audit log record for each HTTP request.

    - Does not log request bodies (avoid sensitive leakage).
    - Stores correlation request_id (X-Request-Id or generated uuid4).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        start = time.perf_counter()

        response: Response
        try:
            response = await call_next(request)
        finally:
            duration_ms = int((time.perf_counter() - start) * 1000)

            # Attempt to pull auth context info from request.state (set by auth dependency in routes)
            org_id = getattr(request.state, "organization_id", None)
            ws_id = getattr(request.state, "workspace_id", None)
            user_id = getattr(request.state, "user_id", None)

            # Determine action heuristic
            action = f"http.{request.method.lower()}"

            async with ASYNC_SESSION_FACTORY() as session:  # type: AsyncSession
                try:
                    session.add(
                        AuditLog(
                            organization_id=org_id,
                            workspace_id=ws_id,
                            user_id=user_id,
                            action=action,
                            resource_type=None,
                            resource_id=None,
                            method=request.method,
                            path=str(request.url.path),
                            status_code=getattr(response, "status_code", 500),
                            ip=request.client.host if request.client else None,
                            user_agent=_safe_user_agent(request.headers.get("User-Agent")),
                            request_id=request_id,
                            details={"duration_ms": duration_ms},
                        )
                    )
                    await session.commit()
                except Exception:
                    # Never break the request due to audit logging failure
                    await session.rollback()

        response.headers["X-Request-Id"] = request_id
        return response
