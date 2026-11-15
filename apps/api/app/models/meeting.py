"""Project meetings specialize the existing revisioned document identity."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
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


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('held','planned','cancelled')", name="ck_meeting_status"
        ),
        CheckConstraint(
            "visibility IN ('project','selected')", name="ck_meeting_visibility"
        ),
        CheckConstraint(
            "time_precision IN ('date','datetime')", name="ck_meeting_precision"
        ),
    )
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("research_documents.id", ondelete="RESTRICT"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_precision: Mapped[str] = mapped_column(String(16), nullable=False)
    time_zone: Mapped[str] = mapped_column(String(64), nullable=False)
    create_digest: Mapped[str] = mapped_column(String(64), nullable=False)


class MeetingParticipant(Base):
    __tablename__ = "meeting_participants"
    __table_args__ = (
        UniqueConstraint("meeting_id", "user_id", name="uq_meeting_participant_user"),
    )
    id: Mapped[UUID] = mapped_column(
        primary_key=True, server_default=func.uuid_generate_v7()
    )
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meetings.document_id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    organization: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    attendance: Mapped[str] = mapped_column(String(16), nullable=False)


class MeetingAccess(Base):
    __tablename__ = "meeting_access"
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meetings.document_id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)


class MeetingComment(Base):
    __tablename__ = "meeting_comments"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meetings.document_id", ondelete="RESTRICT"), index=True
    )
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MeetingWorkLink(Base):
    __tablename__ = "meeting_work_links"
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meetings.document_id", ondelete="RESTRICT"), primary_key=True
    )
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("project_work.task_id", ondelete="RESTRICT"), primary_key=True
    )
    relation: Mapped[str] = mapped_column(String(16), nullable=False)
    source_revision: Mapped[int] = mapped_column(nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
