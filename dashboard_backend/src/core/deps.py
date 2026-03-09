from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional, Set

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.db import get_db_session
from src.core.models import Permission, RolePermission, User, UserRole
from src.core.security import decode_token

security_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    """Authenticated request context including tenancy information and permissions."""

    user: User
    organization_id: uuid.UUID
    workspace_id: Optional[uuid.UUID]
    permissions: Set[str]


async def _load_user_permissions(session: AsyncSession, user_id: uuid.UUID) -> Set[str]:
    # Join: user_roles -> role_permissions -> permissions
    stmt = (
        select(Permission.name)
        .select_from(UserRole)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(UserRole.user_id == user_id)
    )
    rows = (await session.execute(stmt)).all()
    return {r[0] for r in rows}


def _http_unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def _http_forbidden(detail: str = "Not authorized") -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def _get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User:
    stmt = select(User).where(User.id == user_id, User.is_active.is_(True))
    user = (await session.execute(stmt)).scalar_one_or_none()
    if not user:
        raise _http_unauthorized("User not found or inactive")
    return user


# PUBLIC_INTERFACE
async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db_session),
    x_organization_id: Optional[str] = Header(default=None, alias="X-Organization-Id"),
    x_workspace_id: Optional[str] = Header(default=None, alias="X-Workspace-Id"),
) -> AuthContext:
    """Authenticate the request, resolve tenancy, and load permissions.

    Tenancy mode:
      - header: organization/workspace determined from X-Organization-Id / X-Workspace-Id
      - token: organization/workspace taken from JWT claims (org_id, workspace_id)
    """
    if not credentials or not credentials.credentials:
        raise _http_unauthorized()

    try:
        payload = decode_token(credentials.credentials)
    except Exception:
        raise _http_unauthorized("Invalid token")

    sub = payload.get("sub")
    if not sub:
        raise _http_unauthorized("Token missing subject")

    try:
        user_id = uuid.UUID(str(sub))
    except ValueError:
        raise _http_unauthorized("Invalid subject")

    user = await _get_user_by_id(db, user_id)
    permissions = await _load_user_permissions(db, user.id)

    settings = get_settings()
    if settings.tenancy_mode == "token":
        org_id_raw = payload.get("org_id")
        ws_id_raw = payload.get("workspace_id")
    else:
        org_id_raw = x_organization_id
        ws_id_raw = x_workspace_id

    if not org_id_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing organization id (X-Organization-Id header or org_id claim)",
        )
    try:
        org_id = uuid.UUID(str(org_id_raw))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid organization id")

    # Enforce user org membership (strong tenant boundary)
    if user.organization_id != org_id:
        raise _http_forbidden("Cross-tenant access denied")

    ws_id: Optional[uuid.UUID] = None
    if ws_id_raw:
        try:
            ws_id = uuid.UUID(str(ws_id_raw))
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid workspace id")

    return AuthContext(user=user, organization_id=org_id, workspace_id=ws_id, permissions=permissions)


def require_permission(permission: str):
    """Factory for permission dependency."""

    async def _dep(ctx: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if permission not in ctx.permissions:
            raise _http_forbidden(f"Missing permission: {permission}")
        return ctx

    return _dep
