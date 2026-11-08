"""Private navigation history; never a source of resource permissions."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ProjectVisit(Base):
    __tablename__ = "project_visits"
    __table_args__ = (Index("ix_project_visits_user_time", "user_id", "visited_at"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    visited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    target: Mapped[dict] = mapped_column(JSON, nullable=False)
