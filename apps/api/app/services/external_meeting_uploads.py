"""Confirmed uploads into an existing meeting. Content grants never grant an audience."""

from datetime import UTC, datetime
from pathlib import PurePath
from uuid import UUID

from fastapi import HTTPException
from pydantic import Field, field_validator
from sqlalchemy import select

from app.models.lab import Lab
from app.models.meeting_workspace import MeetingSpace
from app.models.research_document import ResearchDocument
from app.models.research_log import ResearchLogEntry
from app.routers import meetings
from app.services import external_access as boundary
from app.services.browser_paths import project_browser_path
from app.services.external_research_contracts import Strict
from app.services.meeting_transcript import import_original
from app.services.meeting_workspace import add_minutes_edition, sources

SCOPE = "meetings:upload"


class MeetingUpload(Strict):
    meeting_id: UUID
    request_key: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=1024 * 1024)

    @field_validator("filename")
    @classmethod
    def filename_only(cls, value):
        value.encode("utf-8")
        if any(c in "/\\" or ord(c) < 32 for c in value):
            raise ValueError("Supply a filename without a path")
        if PurePath(value).suffix.lower() not in {
            ".srt",
            ".vtt",
            ".txt",
            ".md",
            ".aimd",
        }:
            raise ValueError("Choose SRT, VTT, TXT, MD or AIMD")
        return value

    @field_validator("content")
    @classmethod
    def bounded_text(cls, value):
        if (
            not value.strip()
            or "\x00" in value
            or len(value.encode("utf-8")) > 1024 * 1024
        ):
            raise ValueError("Supply non-empty UTF-8 text up to 1 MiB")
        return value


TOOLS = {
    "preview_meeting_upload": (
        "Preview one UTF-8 file for an existing meeting ID from its Platform link. "
        "SRT/VTT/TXT imports an original transcript; MD/AIMD saves a new minutes revision. "
        "Supply the actual file text and a stable request_key. Never send a URL or change the audience. "
        "Ask the user to review the confirmation_url, then call execute_operation.",
        MeetingUpload,
        False,
    )
}


def available_tools(access):
    if SCOPE not in access.grant.scopes or (
        access.grant.project_coverage and not access.project
    ):
        return []
    return [*TOOLS, "operation_status", "execute_operation"]


async def target(db, access, identity, transcript, *, initialize=False):
    boundary.scope(access, SCOPE)
    try:
        if access.project:
            pid = await db.scalar(
                select(ResearchLogEntry.project_id).where(
                    ResearchLogEntry.id == identity
                )
            )
            if pid != access.project.id:
                boundary.fail("meeting_unavailable", 404)
            if transcript:
                await sources(
                    db, access.user, identity, write=True, initialize=initialize
                )
            entry, meeting, _ = await meetings.context(
                db, access.user, identity, "edit", lock=True
            )
            return entry, meeting
        room = await db.scalar(
            select(MeetingSpace.id).where(
                MeetingSpace.id == identity,
                MeetingSpace.lab_id == access.grant.organization_id,
                MeetingSpace.project_meeting_id.is_(None),
            )
        )
        if access.grant.project_coverage or room is None:
            boundary.fail("meeting_unavailable", 404)
        return await sources(db, access.user, identity, write=True), None
    except HTTPException as error:
        if error.status_code in (403, 404):
            boundary.fail("meeting_unavailable", 404)
        raise


async def prepare_original(db, identity, filename, content, *, save):
    try:
        return await import_original(
            db, identity, filename, content.encode("utf-8"), save=save
        )
    except HTTPException as error:
        if error.status_code in (409, 422):
            boundary.fail(
                "original_transcript_exists"
                if error.status_code == 409
                else "invalid_transcript",
                error.status_code,
            )
        raise


async def preview(db, access, args):
    from app.services.external_research import new_operation

    suffix = PurePath(args.filename).suffix.lower()
    transcript = suffix not in (".md", ".aimd")
    entry, meeting = await target(db, access, args.meeting_id, transcript)
    if transcript:
        await prepare_original(
            db, args.meeting_id, args.filename, args.content, save=False
        )
    elif len(args.content) > 200000:
        boundary.fail("minutes_too_long", 422)
    if access.project:
        lab = await db.get(Lab, access.project.lab_id)
        url = (
            project_browser_path(lab.uid, access.project.uid)
            + f"/meetings?meeting={args.meeting_id}"
        )
    else:
        url = f"/my-work?room={args.meeting_id}"
    return await new_operation(
        db,
        access,
        key=args.request_key,
        kind="meeting_upload",
        payload=args.model_dump(mode="json"),
        summary=dict(
            meeting_id=str(args.meeting_id),
            title=entry.title,
            meeting_url=url,
            filename=args.filename,
            material="transcript" if transcript else "minutes",
            audience="participants"
            if transcript or not meeting
            else meeting.visibility,
            expected_version=entry.revision,
        ),
    )


async def authorized_target(db, access, op, *, initialize=False):
    return await target(
        db,
        access,
        UUID(op.summary["meeting_id"]),
        op.summary["material"] == "transcript",
        initialize=initialize,
    )


async def execute(db, access, op):
    entry, meeting = await authorized_target(
        db, access, op, initialize=op.state == "approved"
    )
    if op.state == "succeeded":
        return boundary.operation_view(op)
    if op.state != "approved" or op.expires_at <= boundary.now():
        boundary.fail("operation_not_approved_or_expired", 409)
    if entry.revision != op.summary["expected_version"]:
        boundary.fail("meeting_changed_preview_again", 409)
    args = MeetingUpload.model_validate(op.payload)
    if op.summary["material"] == "transcript":
        receipt = await prepare_original(
            db, entry.id, args.filename, args.content, save=True
        )
    else:
        fmt = PurePath(args.filename).suffix[1:].lower()
        entry.body = args.content
        entry.revision += 1
        if meeting:
            doc = await db.get(ResearchDocument, entry.id)
            doc.format_version = fmt + ".v1"
            entry.updated_at = datetime.now(UTC)
            await meetings.revision(
                db, access.user, entry, meeting, "Meeting minutes uploaded"
            )
        else:
            entry.body_format = fmt
            entry.digest = op.digest
            add_minutes_edition(db, entry)
        receipt = {"revision": entry.revision}
    op.result = {
        "meeting_id": str(entry.id),
        "filename": args.filename,
        "links": [op.summary["meeting_url"]],
        **receipt,
    }
    op.state, op.payload = "succeeded", {}
    boundary.audit(
        db,
        access.user.id,
        "operation.executed",
        access.grant.id,
        operation_id=str(op.id),
        kind=op.kind,
    )
    return boundary.operation_view(op)
