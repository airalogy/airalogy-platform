"""Delegated credentials are separate from browser sessions and legacy API keys."""

from datetime import datetime
from typing import ClassVar
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ExternalAccessPolicy(Base):
    __tablename__ = "external_access_policies"
    lab_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(default=False)
    blocked_fields: Mapped[list] = mapped_column(JSON, default=list)
    revision: Mapped[int] = mapped_column(default=1)


class ExternalGrant(Base):
    __tablename__ = "external_grants"
    __table_args__ = (
        CheckConstraint(
            "num_nonnulls(project_id, organization_id) = 1",
            name="ck_external_grant_target",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE")
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    oauth_client_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("external_oauth_clients.id", ondelete="SET NULL"), nullable=True
    )
    audience: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    name: Mapped[str] = mapped_column(String(100))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_prefix: Mapped[str] = mapped_column(String(20))
    scopes: Mapped[list] = mapped_column(JSON)
    auth_version: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    json_exclude_fields: ClassVar[list[str]] = ["token_hash", "auth_version"]


class ExternalOperation(Base):
    __tablename__ = "external_operations"
    __table_args__ = (
        UniqueConstraint(
            "grant_id", "request_key", name="uq_external_operation_request"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    grant_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_grants.id", ondelete="CASCADE"), index=True
    )
    request_key: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(32))
    protocol_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("protocols.id", ondelete="CASCADE"), nullable=True
    )
    protocol_version_id: Mapped[UUID | None] = mapped_column(nullable=True)
    policy_revision: Mapped[int] = mapped_column()
    digest: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default="pending")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ExternalAudit(Base):
    __tablename__ = "external_access_audit"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    grant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("external_grants.id", ondelete="SET NULL"), nullable=True
    )
    event: Mapped[str] = mapped_column(String(80))
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExternalProjectReceipt(Base):
    __tablename__ = "external_project_receipts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "contract_number", name="uq_external_project_contract"
        ),
    )
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id", ondelete="CASCADE"), primary_key=True
    )
    request_id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True
    )
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    digest: Mapped[str] = mapped_column(String(64))
    contract_number: Mapped[str | None] = mapped_column(String(128))
