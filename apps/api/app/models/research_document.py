"""AIMD working documents compose with the existing revisioned Research Log.

The Log entry is the sole owner of title/body/scope/revisions. Submitted results
are immutable snapshots, independent of Protocol-bound legacy Records.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ResearchDocument(Base):
    __tablename__ = "research_documents"
    __table_args__ = (
        CheckConstraint(
            "state IN ('draft', 'submitted')", name="ck_research_document_state"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        ForeignKey("research_log_entries.id", ondelete="CASCADE"), primary_key=True
    )
    format_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="aimd.v1"
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    record_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    file_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    collection: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    origin: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ResearchDocumentSubmission(Base):
    __tablename__ = "research_document_submissions"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "source_revision", name="uq_document_submission_revision"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_revision: Mapped[int] = mapped_column(nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ResearchMaterial(Base):
    """Source metadata for a standalone, already scope-authorized ResearchFile."""

    __tablename__ = "research_materials"

    id: Mapped[UUID] = mapped_column(
        ForeignKey("research_files.id", ondelete="RESTRICT"), primary_key=True
    )
    source_note: Mapped[str] = mapped_column(String(4000), nullable=False, default="")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    request_key: Mapped[UUID] = mapped_column(nullable=False, unique=True)


class ResearchDocumentDerivation(Base):
    __tablename__ = "research_document_derivations"
    __table_args__ = (
        UniqueConstraint(
            "document_id", "source_revision", "kind", name="uq_document_derivation"
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_revision: Mapped[int] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    knowledge_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_items.id", ondelete="RESTRICT")
    )
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
