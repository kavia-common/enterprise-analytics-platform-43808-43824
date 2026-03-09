from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.deps import AuthContext, get_auth_context, require_permission
from src.user_behavior_analytics.behavior_analyzer import BehaviorAnalyticsError, BehaviorAnalyzer

router = APIRouter(prefix="/behavior", tags=["Behavior Analytics"])


class BehaviorEventIn(BaseModel):
    """Incoming behavior event payload.

    Note: occurred_at supports ISO strings (Pydantic parses to datetime).
    """

    event_type: str = Field(..., min_length=1, max_length=128, description="Event name/type (e.g., page.view)")
    occurred_at: Optional[datetime] = Field(
        default=None,
        description="Event timestamp. If omitted, server assigns current UTC time.",
    )
    source: Optional[str] = Field(default=None, max_length=128, description="Event source label")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Small metadata object. Values are sanitized/truncated by analyzer.",
    )


class BehaviorIngestRequest(BaseModel):
    """Request model for ingesting multiple behavior events."""

    events: List[BehaviorEventIn] = Field(..., min_length=1, description="List of behavior events to ingest")
    max_events: int = Field(
        default=10_000,
        ge=1,
        le=100_000,
        description="Analyzer capacity for this request. Hard-limited to avoid excessive memory usage.",
    )


class BehaviorIngestResponse(BaseModel):
    """Response model for behavior ingestion."""

    ingested: int = Field(..., description="Number of events ingested into the analyzer for this request")
    summary: Dict[str, Any] = Field(..., description="Basic summary of the ingested events")


class BehaviorSummaryResponse(BaseModel):
    """Basic analytics summary response."""

    total_events: int = Field(..., description="Total number of events provided")
    unique_event_types: int = Field(..., description="Number of distinct event types")
    event_counts: Dict[str, int] = Field(..., description="Counts per event type")
    top_event_types: List[List[Any]] = Field(
        ...,
        description="Top event types as list of [event_type, count] pairs (JSON-friendly).",
    )


class FunnelRequest(BaseModel):
    """Request model for computing a simple ordered funnel count."""

    events: List[BehaviorEventIn] = Field(..., min_length=1, description="List of events to analyze")
    steps: List[str] = Field(
        ...,
        min_length=1,
        description="Ordered list of event_type names representing the funnel steps",
    )
    max_events: int = Field(
        default=10_000,
        ge=1,
        le=100_000,
        description="Analyzer capacity for this request. Hard-limited to avoid excessive memory usage.",
    )


class FunnelResponse(BaseModel):
    """Response model for funnel analysis."""

    steps: List[str] = Field(..., description="Funnel steps used for the computation")
    completed: int = Field(..., description="Number of completed funnels detected (greedy, non-overlapping)")


def _to_event_dict(e: BehaviorEventIn) -> Mapping[str, Any]:
    """Convert validated Pydantic event into analyzer-friendly dict."""
    return {
        "event_type": e.event_type,
        "occurred_at": e.occurred_at,
        "source": e.source,
        "metadata": e.metadata,
    }


@router.post(
    "/events",
    response_model=BehaviorIngestResponse,
    summary="Ingest behavior events (in-memory)",
    description=(
        "Validate and ingest behavior events using the in-process BehaviorAnalyzer. "
        "This endpoint does not persist events; it returns a basic summary for the provided batch."
    ),
    responses={400: {"model": dict}, 401: {"model": dict}, 403: {"model": dict}},
)
# PUBLIC_INTERFACE
async def ingest_behavior_events(
    payload: BehaviorIngestRequest,
    ctx: AuthContext = Depends(require_permission("ingestion:write")),
) -> BehaviorIngestResponse:
    """Ingest a batch of behavior events and return basic summary stats.

    Security/tenancy:
      - Requires auth and `ingestion:write` permission.
      - Does not persist or log payload contents.
      - Uses conservative input validation in BehaviorAnalyzer.

    Args:
        payload: Batch of events plus analyzer max_events capacity.
        ctx: Auth context (permission enforced).

    Returns:
        Ingest count and summary statistics.
    """
    # ctx is intentionally unused beyond auth/permission enforcement.
    _ = ctx

    try:
        analyzer = BehaviorAnalyzer(max_events=payload.max_events)
        analyzer.add_events([_to_event_dict(e) for e in payload.events])
        counts = analyzer.event_counts()
        return BehaviorIngestResponse(
            ingested=sum(counts.values()),
            summary={
                "total_events": sum(counts.values()),
                "unique_event_types": len(counts),
                "event_counts": counts,
                # tuples become lists for JSON compatibility
                "top_event_types": [list(x) for x in analyzer.top_event_types(limit=10)],
            },
        )
    except BehaviorAnalyticsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/summary",
    response_model=BehaviorSummaryResponse,
    summary="Summarize a batch of behavior events",
    description="Return counts/top event types for a provided batch of events (no persistence).",
    responses={400: {"model": dict}, 401: {"model": dict}},
)
# PUBLIC_INTERFACE
async def summarize_behavior_events(
    payload: BehaviorIngestRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> BehaviorSummaryResponse:
    """Summarize a batch of events.

    This is useful for client-side or admin tooling to quickly compute high-level stats.

    Args:
        payload: Batch of events plus analyzer capacity.
        ctx: Auth context (authenticated).

    Returns:
        Basic counts and top event types.
    """
    _ = ctx

    try:
        analyzer = BehaviorAnalyzer(max_events=payload.max_events)
        analyzer.add_events([_to_event_dict(e) for e in payload.events])
        counts = analyzer.event_counts()
        return BehaviorSummaryResponse(
            total_events=sum(counts.values()),
            unique_event_types=len(counts),
            event_counts=counts,
            top_event_types=[list(x) for x in analyzer.top_event_types(limit=10)],
        )
    except BehaviorAnalyticsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post(
    "/funnel",
    response_model=FunnelResponse,
    summary="Compute funnel completion count",
    description=(
        "Compute how many times an ordered funnel is completed in the provided event list "
        "(not necessarily contiguous; greedy non-overlapping)."
    ),
    responses={400: {"model": dict}, 401: {"model": dict}},
)
# PUBLIC_INTERFACE
async def compute_funnel(
    payload: FunnelRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> FunnelResponse:
    """Compute a simple funnel completion count for a batch of events.

    Args:
        payload: Events + funnel steps.
        ctx: Auth context (authenticated).

    Returns:
        Funnel steps and number of completed funnels.
    """
    _ = ctx

    try:
        analyzer = BehaviorAnalyzer(max_events=payload.max_events)
        analyzer.add_events([_to_event_dict(e) for e in payload.events])
        completed = analyzer.funnel_count(payload.steps)
        return FunnelResponse(steps=payload.steps, completed=completed)
    except BehaviorAnalyticsError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
