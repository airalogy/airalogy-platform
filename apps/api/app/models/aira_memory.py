"""Account-private, explicitly chosen communication preferences (no research data)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AiraMemory(Base):
    __tablename__ = "aira_memories"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(default=True)
    revision: Mapped[int] = mapped_column(default=0)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    # Bounded account-private suggestion state and one undo receipt.
    interaction: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AiraMemoryEvent(Base):
    """Audit/idempotency metadata only; never retain deleted preference values."""

    __tablename__ = "aira_memory_events"
    __table_args__ = (
        UniqueConstraint("user_id", "request_id", name="uq_aira_memory_request"),
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[UUID] = mapped_column()
    action: Mapped[str] = mapped_column(String(32))
    keys: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
