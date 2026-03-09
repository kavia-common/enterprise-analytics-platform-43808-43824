from __future__ import annotations

import datetime as dt
import uuid
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False)

    workspaces: Mapped[list["Workspace"]] = relationship(back_populates="organization", cascade="all, delete-orphan")
    users: Mapped[list["User"]] = relationship(back_populates="organization", cascade="all, delete-orphan")


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="workspaces")
    dashboards: Mapped[list["Dashboard"]] = relationship(back_populates="workspace", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_workspace_org_name"),)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="users")
    roles: Mapped[list["UserRole"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))

    permissions: Mapped[list["RolePermission"]] = relationship(back_populates="role", cascade="all, delete-orphan")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(String(255))


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[int] = mapped_column(Integer, ForeignKey("permissions.id"), primary_key=True)

    role: Mapped["Role"] = relationship(back_populates="permissions")
    permission: Mapped["Permission"] = relationship()


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("roles.id"), primary_key=True)

    user: Mapped["User"] = relationship(back_populates="roles")
    role: Mapped["Role"] = relationship()


class Dashboard(Base):
    __tablename__ = "dashboards"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    layout: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False)

    workspace: Mapped["Workspace"] = relationship(back_populates="dashboards")
    widgets: Mapped[list["Widget"]] = relationship(back_populates="dashboard", cascade="all, delete-orphan")
    saved_views: Mapped[list["SavedView"]] = relationship(back_populates="dashboard", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_dashboard_workspace_name"),
        Index("ix_dashboards_org_ws", "organization_id", "workspace_id"),
    )


class Widget(Base):
    __tablename__ = "widgets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    dashboard_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dashboards.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(64), nullable=False)  # e.g. line_chart, table
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    position: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False)

    dashboard: Mapped["Dashboard"] = relationship(back_populates="widgets")

    __table_args__ = (
        UniqueConstraint("dashboard_id", "name", name="uq_widget_dashboard_name"),
        Index("ix_widgets_org_ws_dash", "organization_id", "workspace_id", "dashboard_id"),
    )


class SavedView(Base):
    __tablename__ = "saved_views"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    dashboard_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("dashboards.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    filters: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False)

    dashboard: Mapped["Dashboard"] = relationship(back_populates="saved_views")

    __table_args__ = (
        UniqueConstraint("dashboard_id", "name", name="uq_savedview_dashboard_name"),
        Index("ix_savedviews_org_ws_dash", "organization_id", "workspace_id", "dashboard_id"),
    )


class IngestionEvent(Base):
    __tablename__ = "ingestion_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(128))
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    received_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False)

    __table_args__ = (Index("ix_ingestion_org_ws_type_time", "organization_id", "workspace_id", "event_type", "received_at"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    workspace_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), index=True)

    action: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(128))
    resource_id: Mapped[Optional[str]] = mapped_column(String(128))

    method: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    ip: Mapped[Optional[str]] = mapped_column(String(64))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    request_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=dt.datetime.utcnow, nullable=False)

    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
