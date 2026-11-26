from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class ApiEndpoint(Base):
    __tablename__ = "api_endpoints"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False, default="GET")
    headers_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    snapshots: Mapped[list[SchemaSnapshot]] = relationship(
        back_populates="endpoint", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_api_endpoints_is_active", "is_active"),)


class MonitorRun(Base):
    __tablename__ = "monitor_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    endpoints_checked: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    snapshots_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    diffs_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('running','success','partial_failure','failed')",
            name="ck_monitor_runs_status",
        ),
        Index("ix_monitor_runs_started_at_desc", "started_at"),
    )


class SchemaSnapshot(Base):
    __tablename__ = "schema_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    monitor_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitor_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    schema_hash: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_time_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    response_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalized_schema_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    raw_sample_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    fetch_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    endpoint: Mapped[ApiEndpoint] = relationship(back_populates="snapshots")

    __table_args__ = (
        Index("ix_schema_snapshots_hash", "schema_hash"),
        Index("ix_schema_snapshots_endpoint_created", "endpoint_id", "created_at"),
    )


class SchemaDiff(Base):
    __tablename__ = "schema_diffs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    old_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schema_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    new_snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schema_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    change_type: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    old_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_value_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    new_value_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('breaking','risky','safe')",
            name="ck_schema_diffs_severity",
        ),
        Index("ix_schema_diffs_endpoint_created", "endpoint_id", "created_at"),
        Index("ix_schema_diffs_path", "path"),
        Index("ix_schema_diffs_severity", "severity"),
        Index("ix_schema_diffs_new_snapshot", "new_snapshot_id"),
    )


class Changelog(Base):
    __tablename__ = "changelogs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_endpoints.id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schema_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    diff_ids: Mapped[Any] = mapped_column(JSONB, nullable=False)
    diff_set_hash: Mapped[str] = mapped_column(Text, nullable=False)
    generated_text: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("snapshot_id", "diff_set_hash", name="uq_changelog_snapshot_diffset"),
        Index("ix_changelogs_endpoint_created", "endpoint_id", "created_at"),
    )
