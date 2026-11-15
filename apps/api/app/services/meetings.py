"""Meeting contracts and a shared predicate for every document access surface."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import exists, or_, select

from app.models.meeting import Meeting, MeetingAccess
from app.models.research_log import ResearchLogEntry


class Participant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID | None = None
    name: str = Field(default="", max_length=255)
    organization: str = Field(default="", max_length=255)
    attendance: Literal["attended", "invited", "absent", "unknown"] = "attended"

    @model_validator(mode="after")
    def identity(self):
        self.name = self.name.strip()
        if not self.user_id and not self.name:
            raise ValueError("An external participant needs a name")
        return self


class Access(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    role: Literal["viewer", "commenter", "editor"] = "commenter"


class MeetingContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(default="", max_length=200000)
    status: Literal["held", "planned", "cancelled"] = "held"
    occurred_at: datetime | None = None
    scheduled_at: datetime | None = None
    time_precision: Literal["date", "datetime"] = "date"
    time_zone: str = Field(default="UTC", max_length=64)
    visibility: Literal["project", "selected"] = "project"
    participants: list[Participant] = Field(default_factory=list, max_length=100)
    access: list[Access] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def coherent(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("A meeting needs a title")
        try:
            ZoneInfo(self.time_zone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Unknown meeting timezone") from None
        if self.status == "held" and self.occurred_at is None:
            raise ValueError("Record the actual meeting date")
        for field in ["occurred_at", "scheduled_at"]:
            value = getattr(self, field)
            if value and value.tzinfo is None:
                raise ValueError("Meeting times must include a timezone")
        if self.status == "held" and self.occurred_at > datetime.now(UTC) + timedelta(
            minutes=5
        ):
            raise ValueError("A future meeting should be marked as planned")
        for values in [
            [x.user_id for x in self.participants if x.user_id],
            [x.user_id for x in self.access],
        ]:
            if len(set(values)) != len(values):
                raise ValueError("Do not add an account twice")
        return self


def meeting_read_condition(user_id, entry=ResearchLogEntry):
    """Caller still enforces project/log access; this only narrows meeting access."""
    has_meeting = exists(
        select(Meeting.document_id).where(Meeting.document_id == entry.id)
    ).correlate(entry)
    visible_meeting = exists(
        select(Meeting.document_id).where(
            Meeting.document_id == entry.id, Meeting.visibility == "project"
        )
    ).correlate(entry)
    grant = exists(
        select(MeetingAccess.meeting_id).where(
            MeetingAccess.meeting_id == entry.id, MeetingAccess.user_id == user_id
        )
    ).correlate(entry)
    return or_(
        ~has_meeting, visible_meeting, entry.created_by_user_id == user_id, grant
    )


async def authorize_meeting(db, user, entry, permission="read"):
    meeting = await db.get(Meeting, entry.id)
    if meeting is None:
        return None
    owner = entry.created_by_user_id == user.id
    grant = await db.get(MeetingAccess, (entry.id, user.id))
    role = grant.role if grant else None
    if not owner and meeting.visibility == "selected" and not role:
        raise HTTPException(404, "Meeting unavailable")
    if permission == "manage" and not owner:
        raise HTTPException(
            403, "Only the meeting author manages audience and participants"
        )
    if permission == "edit" and not owner and role != "editor":
        raise HTTPException(403, "Meeting editing permission required")
    if (
        permission == "comment"
        and not owner
        and meeting.visibility == "selected"
        and role not in {"commenter", "editor"}
    ):
        raise HTTPException(403, "Meeting comment permission required")
    return meeting


async def require_shareable_meeting_source(db, entry):
    meeting = await db.get(Meeting, entry.id)
    if meeting and meeting.visibility == "selected":
        raise HTTPException(
            403,
            "A selected-audience meeting cannot be copied into a wider document or template. Prepare and review a separate shareable summary.",
        )
