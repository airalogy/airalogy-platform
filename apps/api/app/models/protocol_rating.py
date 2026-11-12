"""Version-specific opinions and auditable use receipts, not an execution engine."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ProtocolUse(Base):
    __tablename__ = "protocol_uses"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_protocol_use_request"),
        UniqueConstraint("research_run_id", name="uq_protocol_use_run"),
        CheckConstraint(
            "outcome IN ('as_planned','adjusted','stopped','unknown')",
            name="ck_protocol_use_outcome",
        ),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    protocol_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocol_versions.id"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(128))
    research_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("research_protocol_runs.id")
    )
    outcome: Mapped[str] = mapped_column(String(32))
    is_real: Mapped[bool] = mapped_column(default=False)
    public: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)
    comment: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProtocolUseRecord(Base):
    __tablename__ = "protocol_use_records"
    # A Record identity belongs to at most one receipt, across ALL its revisions.
    record_id: Mapped[UUID] = mapped_column(primary_key=True)
    record_version: Mapped[int] = mapped_column()
    use_id: Mapped[UUID] = mapped_column(ForeignKey("protocol_uses.id"), index=True)


class ProtocolRating(Base):
    __tablename__ = "protocol_ratings"
    __table_args__ = (
        UniqueConstraint(
            "protocol_version_id", "user_id", name="uq_protocol_rating_user_version"
        ),
        CheckConstraint("score BETWEEN 1 AND 5", name="ck_protocol_rating_score"),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    protocol_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("protocol_versions.id"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    use_id: Mapped[UUID | None] = mapped_column(ForeignKey("protocol_uses.id"))
    score: Mapped[int] = mapped_column()
    comment: Mapped[str] = mapped_column(Text, default="")
    conditions: Mapped[str] = mapped_column(Text, default="")
    public: Mapped[bool] = mapped_column(default=False)
    active: Mapped[bool] = mapped_column(default=True)
    revision: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProtocolRatingRevision(Base):
    __tablename__ = "protocol_rating_revisions"
    __table_args__ = (
        UniqueConstraint("kind", "object_id", "revision", name="uq_rating_revision"),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    kind: Mapped[str] = mapped_column(String(16))
    object_id: Mapped[UUID] = mapped_column(index=True)
    revision: Mapped[int] = mapped_column()
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
