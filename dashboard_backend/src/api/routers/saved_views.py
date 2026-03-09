from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db_session
from src.core.deps import AuthContext, get_auth_context, require_permission
from src.core.models import Dashboard, SavedView
from src.core.schemas import SavedViewCreate, SavedViewResponse
from src.realtime.manager import REALTIME_MANAGER

router = APIRouter(prefix="/dashboards/{dashboard_id}/saved-views", tags=["Saved Views"])


async def _ensure_dashboard(db: AsyncSession, *, dashboard_id: uuid.UUID, org_id: uuid.UUID, ws_id: uuid.UUID) -> None:
    dash = (
        await db.execute(
            select(Dashboard).where(
                Dashboard.id == dashboard_id,
                Dashboard.organization_id == org_id,
                Dashboard.workspace_id == ws_id,
            )
        )
    ).scalar_one_or_none()
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")


@router.get(
    "",
    response_model=List[SavedViewResponse],
    summary="List saved views",
    description="List saved views for a dashboard.",
)
# PUBLIC_INTERFACE
async def list_saved_views(
    dashboard_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db_session),
) -> List[SavedViewResponse]:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    await _ensure_dashboard(db, dashboard_id=dashboard_id, org_id=ctx.organization_id, ws_id=ctx.workspace_id)

    stmt = select(SavedView).where(
        SavedView.dashboard_id == dashboard_id,
        SavedView.organization_id == ctx.organization_id,
        SavedView.workspace_id == ctx.workspace_id,
    )
    items = (await db.execute(stmt)).scalars().all()
    return [SavedViewResponse.model_validate(i.__dict__) for i in items]


@router.post(
    "",
    response_model=SavedViewResponse,
    summary="Create saved view",
    description="Create a saved view (filters state) for a dashboard.",
)
# PUBLIC_INTERFACE
async def create_saved_view(
    dashboard_id: uuid.UUID,
    payload: SavedViewCreate,
    ctx: AuthContext = Depends(require_permission("saved_views:write")),
    db: AsyncSession = Depends(get_db_session),
) -> SavedViewResponse:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    await _ensure_dashboard(db, dashboard_id=dashboard_id, org_id=ctx.organization_id, ws_id=ctx.workspace_id)

    sv = SavedView(
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        dashboard_id=dashboard_id,
        name=payload.name,
        filters=payload.filters,
        created_by_user_id=ctx.user.id,
    )
    db.add(sv)
    await db.commit()
    await db.refresh(sv)

    await REALTIME_MANAGER.publish(
        channel_type="dashboard",
        channel_id=dashboard_id,
        message={"type": "saved_view.created", "saved_view_id": str(sv.id), "dashboard_id": str(dashboard_id)},
    )

    return SavedViewResponse.model_validate(sv.__dict__)


@router.delete(
    "/{saved_view_id}",
    status_code=204,
    summary="Delete saved view",
    description="Delete a saved view.",
)
# PUBLIC_INTERFACE
async def delete_saved_view(
    dashboard_id: uuid.UUID,
    saved_view_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("saved_views:write")),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    await _ensure_dashboard(db, dashboard_id=dashboard_id, org_id=ctx.organization_id, ws_id=ctx.workspace_id)

    stmt = select(SavedView).where(
        SavedView.id == saved_view_id,
        SavedView.dashboard_id == dashboard_id,
        SavedView.organization_id == ctx.organization_id,
        SavedView.workspace_id == ctx.workspace_id,
    )
    sv = (await db.execute(stmt)).scalar_one_or_none()
    if not sv:
        raise HTTPException(status_code=404, detail="Saved view not found")

    await db.delete(sv)
    await db.commit()

    await REALTIME_MANAGER.publish(
        channel_type="dashboard",
        channel_id=dashboard_id,
        message={"type": "saved_view.deleted", "saved_view_id": str(saved_view_id), "dashboard_id": str(dashboard_id)},
    )
