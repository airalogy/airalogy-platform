"""Lightweight coordination is a specialization of ResearchTask, not a second TODO.

ResearchTask owns identity, project, title, goal, state and revision. This table
contains only planning fields; an automation Run remains a separate execution.
ResearchEvent is the immutable history/discussion/decision ledger for both.
"""

from datetime import date
from uuid import UUID

from sqlalchemy import JSON, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ProjectWork(Base):
    __tablename__ = "project_work"

    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_tasks.id", ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False)
    assignee_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    collaborator_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    planned_start: Mapped[date | None] = mapped_column(Date)
    planned_end: Mapped[date | None] = mapped_column(Date)
    blocker: Mapped[str] = mapped_column(Text, nullable=False, default="")
    next_step: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dependency_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    create_digest: Mapped[str] = mapped_column(String(64), nullable=False)
