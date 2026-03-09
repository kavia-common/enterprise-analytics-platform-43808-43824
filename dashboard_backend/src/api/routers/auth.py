from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db_session
from src.core.models import Organization, Role, User, UserRole, Workspace
from src.core.schemas import LoginRequest, SignupRequest, TokenResponse, UserResponse
from src.core.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Auth"])


async def _ensure_default_roles(session: AsyncSession) -> None:
    """Create minimal default roles if missing."""
    for name in ("admin", "editor", "viewer"):
        existing = (await session.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
        if not existing:
            session.add(Role(name=name, description=f"Default {name} role"))
    await session.commit()


@router.post(
    "/signup",
    response_model=TokenResponse,
    summary="Signup",
    description="Create a new organization, workspace, and initial admin user. Returns an access token.",
    responses={400: {"model": dict}, 409: {"model": dict}},
)
# PUBLIC_INTERFACE
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db_session)) -> TokenResponse:
    """Signup endpoint for bootstrapping a tenant."""
    await _ensure_default_roles(db)

    existing_user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if existing_user:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    existing_org = (await db.execute(select(Organization).where(Organization.name == payload.organization_name))).scalar_one_or_none()
    if existing_org:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Organization name already exists")

    org = Organization(name=payload.organization_name)
    db.add(org)
    await db.flush()

    ws = Workspace(organization_id=org.id, name=payload.workspace_name)
    db.add(ws)
    await db.flush()

    user = User(
        organization_id=org.id,
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        is_active=True,
    )
    db.add(user)
    await db.flush()

    admin_role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one()
    db.add(UserRole(user_id=user.id, role_id=admin_role.id))

    await db.commit()

    token, expires_in = create_access_token(
        subject=str(user.id),
        claims={"org_id": str(org.id), "workspace_id": str(ws.id), "roles": ["admin"]},
    )
    return TokenResponse(access_token=token, expires_in_seconds=expires_in)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login",
    description="Authenticate by email/password and return a JWT access token.",
    responses={401: {"model": dict}},
)
# PUBLIC_INTERFACE
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db_session)) -> TokenResponse:
    """Login endpoint."""
    user = (await db.execute(select(User).where(User.email == payload.email, User.is_active.is_(True)))).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Workspace claim is optional (frontend can pass headers); set to null in token claim if not known.
    token, expires_in = create_access_token(subject=str(user.id), claims={"org_id": str(user.organization_id)})
    return TokenResponse(access_token=token, expires_in_seconds=expires_in)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Return the authenticated user's profile (requires Bearer token).",
)
# PUBLIC_INTERFACE
async def me(
    credentials=Depends(lambda: None),  # placeholder for OpenAPI grouping; actual auth enforced in route below
):
    raise HTTPException(status_code=500, detail="This route is registered in main with proper dependencies")
