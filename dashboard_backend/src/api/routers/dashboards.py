from __future__ import annotations

import datetime as dt
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db_session
from src.core.deps import AuthContext, get_auth_context, require_permission
from src.core.models import Dashboard, Workspace
from src.core.schemas import DashboardCreate, DashboardResponse, DashboardUpdate
from src.realtime.manager import REALTIME_MANAGER

router = APIRouter(prefix="/dashboards", tags=["Dashboards"])


async def _ensure_workspace_access(db: AsyncSession, *, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    ws = (await db.execute(select(Workspace).where(Workspace.id == ws_id, Workspace.organization_id == org_id))).scalar_one_or_none()
    if not ws:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found")


@router.get(
    "",
    response_model=List[DashboardResponse],
    summary="List dashboards",
    description="List dashboards within the authenticated organization/workspace.",
)
# PUBLIC_INTERFACE
async def list_dashboards(
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db_session),
) -> List[DashboardResponse]:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required (X-Workspace-Id or workspace_id claim)")
    await _ensure_workspace_access(db, org_id=ctx.organization_id, ws_id=ctx.workspace_id)

    stmt = select(Dashboard).where(
        Dashboard.organization_id == ctx.organization_id,
        Dashboard.workspace_id == ctx.workspace_id,
    )
    items = (await db.execute(stmt)).scalars().all()
    return [DashboardResponse.model_validate(i.__dict__) for i in items]


@router.post(
    "",
    response_model=DashboardResponse,
    summary="Create dashboard",
    description="Create a new dashboard in the current workspace.",
)
# PUBLIC_INTERFACE
async def create_dashboard(
    payload: DashboardCreate,
    ctx: AuthContext = Depends(require_permission("dashboards:write")),
    db: AsyncSession = Depends(get_db_session),
) -> DashboardResponse:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    await _ensure_workspace_access(db, org_id=ctx.organization_id, ws_id=ctx.workspace_id)

    now = dt.datetime.utcnow()
    dash = Dashboard(
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        name=payload.name,
        description=payload.description,
        layout=payload.layout,
        created_by_user_id=ctx.user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(dash)
    await db.commit()
    await db.refresh(dash)

    await REALTIME_MANAGER.publish(
        channel_type="workspace",
        channel_id=ctx.workspace_id,
        message={"type": "dashboard.created", "dashboard_id": str(dash.id)},
    )

    return DashboardResponse.model_validate(dash.__dict__)


@router.get(
    "/{dashboard_id}",
    response_model=DashboardResponse,
    summary="Get dashboard",
    description="Get a dashboard by id within the current org/workspace.",
)
# PUBLIC_INTERFACE
async def get_dashboard(
    dashboard_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db_session),
) -> DashboardResponse:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    stmt = select(Dashboard).where(
        Dashboard.id == dashboard_id,
        Dashboard.organization_id == ctx.organization_id,
        Dashboard.workspace_id == ctx.workspace_id,
    )
    dash = (await db.execute(stmt)).scalar_one_or_none()
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return DashboardResponse.model_validate(dash.__dict__)


@router.put(
    "/{dashboard_id}",
    response_model=DashboardResponse,
    summary="Update dashboard",
    description="Update dashboard name/description/layout.",
)
# PUBLIC_INTERFACE
async def update_dashboard(
    dashboard_id: uuid.UUID,
    payload: DashboardUpdate,
    ctx: AuthContext = Depends(require_permission("dashboards:write")),
    db: AsyncSession = Depends(get_db_session),
) -> DashboardResponse:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    stmt = select(Dashboard).where(
        Dashboard.id == dashboard_id,
        Dashboard.organization_id == ctx.organization_id,
        Dashboard.workspace_id == ctx.workspace_id,
    )
    dash = (await db.execute(stmt)).scalar_one_or_none()
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    if payload.name is not None:
        dash.name = payload.name
    if payload.description is not None:
        dash.description = payload.description
    if payload.layout is not None:
        dash.layout = payload.layout
    dash.updated_at = dt.datetime.utcnow()

    await db.commit()
    await db.refresh(dash)

    await REALTIME_MANAGER.publish(
        channel_type="dashboard",
        channel_id=dash.id,
        message={"type": "dashboard.updated", "dashboard_id": str(dash.id)},
    )

    return DashboardResponse.model_validate(dash.__dict__)


@router.delete(
    "/{dashboard_id}",
    status_code=204,
    summary="Delete dashboard",
    description="Delete a dashboard and its widgets/saved views.",
)
# PUBLIC_INTERFACE
async def delete_dashboard(
    dashboard_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("dashboards:write")),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    stmt = select(Dashboard).where(
        Dashboard.id == dashboard_id,
        Dashboard.organization_id == ctx.organization_id,
        Dashboard.workspace_id == ctx.workspace_id,
    )
    dash = (await db.execute(stmt)).scalar_one_or_none()
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")

    await db.delete(dash)
    await db.commit()

    await REALTIME_MANAGER.publish(
        channel_type="workspace",
        channel_id=ctx.workspace_id,
        message={"type": "dashboard.deleted", "dashboard_id": str(dashboard_id)},
    )
