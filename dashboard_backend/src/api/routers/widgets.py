from __future__ import annotations

import datetime as dt
import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db_session
from src.core.deps import AuthContext, get_auth_context, require_permission
from src.core.models import Dashboard, Widget
from src.core.schemas import WidgetCreate, WidgetResponse, WidgetUpdate
from src.realtime.manager import REALTIME_MANAGER

router = APIRouter(prefix="/dashboards/{dashboard_id}/widgets", tags=["Widgets"])


async def _get_dashboard(db: AsyncSession, *, dashboard_id: uuid.UUID, org_id: uuid.UUID, ws_id: uuid.UUID) -> Dashboard:
    stmt = select(Dashboard).where(
        Dashboard.id == dashboard_id,
        Dashboard.organization_id == org_id,
        Dashboard.workspace_id == ws_id,
    )
    dash = (await db.execute(stmt)).scalar_one_or_none()
    if not dash:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    return dash


@router.get(
    "",
    response_model=List[WidgetResponse],
    summary="List widgets",
    description="List widgets for a dashboard.",
)
# PUBLIC_INTERFACE
async def list_widgets(
    dashboard_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db_session),
) -> List[WidgetResponse]:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    await _get_dashboard(db, dashboard_id=dashboard_id, org_id=ctx.organization_id, ws_id=ctx.workspace_id)

    stmt = select(Widget).where(
        Widget.dashboard_id == dashboard_id,
        Widget.organization_id == ctx.organization_id,
        Widget.workspace_id == ctx.workspace_id,
    )
    items = (await db.execute(stmt)).scalars().all()
    return [WidgetResponse.model_validate(i.__dict__) for i in items]


@router.post(
    "",
    response_model=WidgetResponse,
    summary="Create widget",
    description="Create a new widget on a dashboard.",
)
# PUBLIC_INTERFACE
async def create_widget(
    dashboard_id: uuid.UUID,
    payload: WidgetCreate,
    ctx: AuthContext = Depends(require_permission("widgets:write")),
    db: AsyncSession = Depends(get_db_session),
) -> WidgetResponse:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    await _get_dashboard(db, dashboard_id=dashboard_id, org_id=ctx.organization_id, ws_id=ctx.workspace_id)

    now = dt.datetime.utcnow()
    w = Widget(
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        dashboard_id=dashboard_id,
        name=payload.name,
        type=payload.type,
        config=payload.config,
        position=payload.position,
        created_by_user_id=ctx.user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(w)
    await db.commit()
    await db.refresh(w)

    await REALTIME_MANAGER.publish(
        channel_type="dashboard",
        channel_id=dashboard_id,
        message={"type": "widget.created", "widget_id": str(w.id), "dashboard_id": str(dashboard_id)},
    )
    return WidgetResponse.model_validate(w.__dict__)


@router.put(
    "/{widget_id}",
    response_model=WidgetResponse,
    summary="Update widget",
    description="Update widget properties.",
)
# PUBLIC_INTERFACE
async def update_widget(
    dashboard_id: uuid.UUID,
    widget_id: uuid.UUID,
    payload: WidgetUpdate,
    ctx: AuthContext = Depends(require_permission("widgets:write")),
    db: AsyncSession = Depends(get_db_session),
) -> WidgetResponse:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    await _get_dashboard(db, dashboard_id=dashboard_id, org_id=ctx.organization_id, ws_id=ctx.workspace_id)

    stmt = select(Widget).where(
        Widget.id == widget_id,
        Widget.dashboard_id == dashboard_id,
        Widget.organization_id == ctx.organization_id,
        Widget.workspace_id == ctx.workspace_id,
    )
    w = (await db.execute(stmt)).scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Widget not found")

    if payload.name is not None:
        w.name = payload.name
    if payload.type is not None:
        w.type = payload.type
    if payload.config is not None:
        w.config = payload.config
    if payload.position is not None:
        w.position = payload.position
    w.updated_at = dt.datetime.utcnow()

    await db.commit()
    await db.refresh(w)

    await REALTIME_MANAGER.publish(
        channel_type="dashboard",
        channel_id=dashboard_id,
        message={"type": "widget.updated", "widget_id": str(widget_id), "dashboard_id": str(dashboard_id)},
    )
    return WidgetResponse.model_validate(w.__dict__)


@router.delete(
    "/{widget_id}",
    status_code=204,
    summary="Delete widget",
    description="Delete a widget.",
)
# PUBLIC_INTERFACE
async def delete_widget(
    dashboard_id: uuid.UUID,
    widget_id: uuid.UUID,
    ctx: AuthContext = Depends(require_permission("widgets:write")),
    db: AsyncSession = Depends(get_db_session),
) -> None:
    if not ctx.workspace_id:
        raise HTTPException(status_code=400, detail="Workspace is required")
    await _get_dashboard(db, dashboard_id=dashboard_id, org_id=ctx.organization_id, ws_id=ctx.workspace_id)

    stmt = select(Widget).where(
        Widget.id == widget_id,
        Widget.dashboard_id == dashboard_id,
        Widget.organization_id == ctx.organization_id,
        Widget.workspace_id == ctx.workspace_id,
    )
    w = (await db.execute(stmt)).scalar_one_or_none()
    if not w:
        raise HTTPException(status_code=404, detail="Widget not found")

    await db.delete(w)
    await db.commit()

    await REALTIME_MANAGER.publish(
        channel_type="dashboard",
        channel_id=dashboard_id,
        message={"type": "widget.deleted", "widget_id": str(widget_id), "dashboard_id": str(dashboard_id)},
    )
