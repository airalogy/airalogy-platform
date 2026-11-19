"""Commercial books are opt-in, independent of Research Task compute budgets."""

from datetime import datetime
from uuid import UUID

from app.models.base import Base
from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column


class OperationsOrganization(Base):
    __tablename__ = "operations_organizations"
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("labs.id"), primary_key=True
    )
    enabled: Mapped[bool]
    revision: Mapped[int]


class OperationsBook(Base):
    __tablename__ = "operations_books"
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id"), primary_key=True
    )
    enabled: Mapped[bool]
    revision: Mapped[int]


class OperationsGrant(Base):
    __tablename__ = "operations_grants"
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("operations_books.project_id"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(12))


class OperationsEntry(Base):
    __tablename__ = "operations_entries"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("operations_books.project_id"), index=True
    )
    kind: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(12))
    revision: Mapped[int]
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    verified_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OperationsEvent(Base):
    __tablename__ = "operations_events"
    __table_args__ = (
        UniqueConstraint("project_id", "request_id", name="uq_operations_request"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("operations_books.project_id"), index=True
    )
    entry_id: Mapped[UUID] = mapped_column(
        ForeignKey("operations_entries.id"), index=True
    )
    request_id: Mapped[UUID]
    digest: Mapped[str] = mapped_column(String(64))
    actor_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reason: Mapped[str]
    before: Mapped[dict | None] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)


class OperationsProof(Base):
    """A restricted original referenced by a ledger or by its audit history."""

    __tablename__ = "operations_proofs"
    file_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_files.id"), primary_key=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("operations_books.project_id"), index=True
    )
