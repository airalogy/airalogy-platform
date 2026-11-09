"""Delegated snapshots and external execution provenance; no implicit sharing."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ExternalSnapshot(Base):
    __tablename__ = "external_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "grant_id", "request_key", name="uq_external_snapshot_request"
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    grant_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_grants.id", ondelete="RESTRICT"), index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    request_key: Mapped[str] = mapped_column(String(100))
    request_digest: Mapped[str] = mapped_column(String(64))
    policy_revision: Mapped[int] = mapped_column()
    selection: Mapped[dict] = mapped_column(JSON)
    content: Mapped[dict] = mapped_column(JSON)
    digest: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExternalAnalysisSource(Base):
    __tablename__ = "external_analysis_sources"
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), primary_key=True
    )
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_snapshots.id", ondelete="RESTRICT"), index=True
    )
    grant_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_grants.id", ondelete="RESTRICT")
    )


class ExternalAnalysisFile(Base):
    __tablename__ = "external_analysis_files"
    __table_args__ = (
        UniqueConstraint("run_id", "filename", name="uq_external_analysis_filename"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    blob_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_file_blobs.id", ondelete="RESTRICT")
    )
    filename: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16))


class ExternalOAuthClient(Base):
    __tablename__ = "external_oauth_clients"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    redirect_uris: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExternalOAuthCode(Base):
    __tablename__ = "external_oauth_codes"
    code_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_oauth_clients.id", ondelete="CASCADE")
    )
    grant_id: Mapped[UUID] = mapped_column(
        ForeignKey("external_grants.id", ondelete="CASCADE")
    )
    redirect_uri: Mapped[str] = mapped_column(String(2048))
    challenge: Mapped[str] = mapped_column(String(43))
    resource: Mapped[str] = mapped_column(String(2048))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
