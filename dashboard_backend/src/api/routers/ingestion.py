from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.db import get_db_session
from src.core.deps import AuthContext, require_permission
from src.core.models import IngestionEvent
from src.core.schemas import IngestionEventCreate, IngestionEventResponse
from src.realtime.manager import REALTIME_MANAGER

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])


@router.post(
    "/events",
    response_model=IngestionEventResponse,
    summary="Ingest an event",
    description="Store an analytics/telemetry event for the current org/workspace and notify realtime subscribers.",
)
# PUBLIC_INTERFACE
async def ingest_event(
    payload: IngestionEventCreate,
    ctx: AuthContext = Depends(require_permission("ingestion:write")),
    db: AsyncSession = Depends(get_db_session),
) -> IngestionEventResponse:
    if not ctx.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace is required (X-Workspace-Id or workspace_id claim)",
        )

    event = IngestionEvent(
        organization_id=ctx.organization_id,
        workspace_id=ctx.workspace_id,
        event_type=payload.event_type,
        source=payload.source,
        payload=payload.payload,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    # Notify workspace channel listeners
    await REALTIME_MANAGER.publish(
        channel_type="workspace",
        channel_id=ctx.workspace_id,
        message={
            "type": "ingestion.event",
            "event_id": str(event.id),
            "event_type": event.event_type,
        },
    )
    return IngestionEventResponse.model_validate(event.__dict__)
