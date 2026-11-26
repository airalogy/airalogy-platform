"""Organization meetings and the private source material attached to meetings."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MeetingSpace(Base):
    __tablename__ = "meeting_spaces"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    lab_id: Mapped[UUID] = mapped_column(ForeignKey("labs.id"), index=True)
    # Existing project meetings keep their original document and minutes.
    project_meeting_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("meetings.document_id"), unique=True
    )
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(512), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    body_format: Mapped[str] = mapped_column(String(12), default="aimd")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(default=1)
    digest: Mapped[str] = mapped_column(String(64))


class MeetingSpaceProject(Base):
    __tablename__ = "meeting_space_projects"
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meeting_spaces.id"), primary_key=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id"), primary_key=True
    )


class MeetingSpacePerson(Base):
    __tablename__ = "meeting_space_people"
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meeting_spaces.id"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)


class MeetingMinutesEdition(Base):
    __tablename__ = "meeting_minutes_editions"
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meeting_spaces.id"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(512))
    body: Mapped[str] = mapped_column(Text)
    body_format: Mapped[str] = mapped_column(String(12))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MeetingMinutesShare(Base):
    __tablename__ = "meeting_minutes_shares"
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meeting_spaces.id"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    revision: Mapped[int]


class MeetingTranscript(Base):
    __tablename__ = "meeting_transcripts"
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meeting_spaces.id"), primary_key=True
    )
    original: Mapped[bytes] = mapped_column(LargeBinary)
    filename: Mapped[str] = mapped_column(String(255))
    cues: Mapped[list] = mapped_column(JSON)
    revision: Mapped[int]


class MeetingAudio(Base):
    __tablename__ = "meeting_audio"
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meeting_spaces.id"), primary_key=True
    )
    storage_key: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(128))
    backend: Mapped[str] = mapped_column(String(64))


class MeetingFollowUp(Base):
    __tablename__ = "meeting_follow_ups"
    id: Mapped[UUID] = mapped_column(primary_key=True)
    meeting_id: Mapped[UUID] = mapped_column(
        ForeignKey("meeting_spaces.id"), index=True
    )
    source_revision: Mapped[int]
    owner_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    project_id: Mapped[UUID | None] = mapped_column(ForeignKey("projects.id"))
    project_work_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("project_work.task_id"), unique=True
    )
    assignee_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    audience: Mapped[str] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    due: Mapped[date | None]
    state: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int]
    digest: Mapped[str] = mapped_column(String(64))


class MeetingFollowUpReader(Base):
    __tablename__ = "meeting_follow_up_readers"
    task_id: Mapped[UUID] = mapped_column(
        ForeignKey("meeting_follow_ups.id"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
