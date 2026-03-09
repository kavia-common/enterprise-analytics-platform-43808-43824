from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Error message")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in_seconds: int = Field(..., description="Seconds until token expiry")


class SignupRequest(BaseModel):
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, max_length=128, description="User password (min 8 chars)")
    full_name: Optional[str] = Field(default=None, max_length=200, description="Optional full name")
    organization_name: str = Field(..., min_length=2, max_length=200, description="New organization name")
    workspace_name: str = Field(default="Default", min_length=1, max_length=200, description="Initial workspace name")


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=8, max_length=128, description="User password")


class UserResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    email: EmailStr
    full_name: Optional[str]
    is_active: bool
    created_at: datetime

    roles: List[str] = Field(default_factory=list, description="Role names assigned to user")


class DashboardCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Dashboard name")
    description: Optional[str] = Field(default=None, max_length=500, description="Dashboard description")
    layout: Dict[str, Any] = Field(default_factory=dict, description="Dashboard layout JSON")


class DashboardUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=500)
    layout: Optional[Dict[str, Any]] = None


class DashboardResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    description: Optional[str]
    layout: Dict[str, Any]
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class WidgetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Widget name")
    type: str = Field(..., min_length=1, max_length=64, description="Widget type")
    config: Dict[str, Any] = Field(default_factory=dict, description="Widget configuration JSON")
    position: Dict[str, Any] = Field(default_factory=dict, description="Grid position/size JSON")


class WidgetUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    type: Optional[str] = Field(default=None, min_length=1, max_length=64)
    config: Optional[Dict[str, Any]] = None
    position: Optional[Dict[str, Any]] = None


class WidgetResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    dashboard_id: uuid.UUID
    name: str
    type: str
    config: Dict[str, Any]
    position: Dict[str, Any]
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class SavedViewCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="Saved view name")
    filters: Dict[str, Any] = Field(default_factory=dict, description="Saved filter state JSON")


class SavedViewResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    dashboard_id: uuid.UUID
    name: str
    filters: Dict[str, Any]
    created_by_user_id: uuid.UUID
    created_at: datetime


class IngestionEventCreate(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=128, description="Event type")
    source: Optional[str] = Field(default=None, max_length=128, description="Event source identifier")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event payload JSON")


class IngestionEventResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    workspace_id: uuid.UUID
    event_type: str
    source: Optional[str]
    payload: Dict[str, Any]
    received_at: datetime


RealtimeChannelType = Literal["workspace", "dashboard"]


class RealtimeSubscribeRequest(BaseModel):
    channel_type: RealtimeChannelType = Field(..., description="Subscription channel type")
    channel_id: uuid.UUID = Field(..., description="Workspace ID or Dashboard ID depending on channel_type")
