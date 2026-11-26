"""Private meeting recordings, verbatim text and source-backed Aira proposals."""

import asyncio
import hashlib
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Literal
from urllib.parse import quote
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.database import DBSession
from app.libs.file_storage import (
    default_storage_backend,
    get_file_with_stream,
    upload_file,
)
from app.models.chat import ChatModel
from app.models.meeting import MeetingParticipant
from app.models.meeting_workspace import (
    MeetingAudio,
    MeetingSpacePerson,
    MeetingTranscript,
)
from app.models.project_guest import OrganizationGuestProfile
from app.models.project_person import ProjectPerson
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.chat_models import enabled_chat_model_types, require_ai_enabled
from app.services.meeting_drafts import DraftTurn, draft_meeting
from app.services.meeting_transcript import Cue, export_transcript, parse_transcript
from app.services.meeting_workspace import guest, links, sources
from app.services.model_usage import create_usage_context
from app.services.organization_ai import bind_organization
from app.services.project_people import organization_accounts

router = APIRouter(prefix="/meeting-workspace/rooms", tags=["meeting source material"])
FORMATS = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
}


class Edit(BaseModel):
    expected_revision: int = Field(ge=1)
    cues: list[Cue] = Field(min_length=1, max_length=20000)


async def speaker_people(db, space):
    if space.project_meeting_id:
        rows = await db.execute(
            select(MeetingParticipant.user_id, ProjectPerson.user_id)
            .outerjoin(ProjectPerson, ProjectPerson.id == MeetingParticipant.person_id)
            .where(
                MeetingParticipant.meeting_id == space.id,
                MeetingParticipant.attendance != "absent",
            )
        )
        participants = {uid or linked for uid, linked in rows}
        from app.routers.meetings import meeting_members

        owner = await db.get(User, space.owner_id)
        (project_id,) = await links(db, space)
        candidates = (await meeting_members(owner, db, project_id))["members"]
        people = {
            p["id"]: (p["display_name"] or p["name"], p["username"], p["name"])
            for p in candidates
        }
    else:
        participants = set(
            await db.scalars(
                select(MeetingSpacePerson.user_id).where(
                    MeetingSpacePerson.meeting_id == space.id
                )
            )
        )
        people = {
            u.id: (name, u.username, u.name)
            for u, name in await db.execute(organization_accounts(space.lab_id))
        }
    participants.add(space.owner_id)
    from app.routers.my_work import readable_projects

    owner = await db.get(User, space.owner_id)
    projects = set(await links(db, space)) & set(
        await readable_projects(db, owner, "visible", None)
    )
    for project_id in projects:
        guests = await db.execute(
            select(User, OrganizationGuestProfile.display_name)
            .outerjoin(
                OrganizationGuestProfile,
                (OrganizationGuestProfile.user_id == User.id)
                & (OrganizationGuestProfile.lab_id == space.lab_id),
            )
            .where(guest(project_id, User.id))
        )
        for user, name in guests:
            people.setdefault(
                user.id, (name or user.name or user.username, user.username, user.name)
            )
    directory = [
        dict(
            id=str(uid),
            name=name,
            username=username,
            aliases=[alias],
            participant=uid in participants,
        )
        for uid, (name, username, alias) in people.items()
    ]
    return sorted(
        directory,
        key=lambda p: (not p["participant"], p["name"].casefold(), p["username"]),
    )


def suggestions(cues, people):
    def normalized(name):
        return (
            unicodedata.normalize("NFKC", name or "")
            .strip()
            .removeprefix("@")
            .casefold()
        )

    accounts = defaultdict(list)
    for person in sorted(people, key=lambda p: not p["participant"]):
        for key in {
            normalized(x)
            for x in (person["name"], person["username"], *person["aliases"])
        } - {""}:
            accounts[key].append(person["id"])
    return {
        name: accounts[normalized(name)]
        for name in dict.fromkeys(c["speaker"] for c in cues if c["speaker"])
    }


@router.get("/{identity}/speakers")
async def recommend(identity: UUID, user: CurrentUser, db: DBSession):
    space = await sources(db, user, identity, owner=True)
    transcript = await db.get(MeetingTranscript, identity)
    if not space or not transcript:
        raise HTTPException(404, "Transcript unavailable")
    people = await speaker_people(db, space)
    return {"people": people, "matches": suggestions(transcript.cues, people)}


@router.get("/{identity}/sources")
async def source_info(identity: UUID, user: CurrentUser, db: DBSession):
    await sources(db, user, identity)
    transcript = await db.get(MeetingTranscript, identity)
    audio = await db.get(MeetingAudio, identity)
    return dict(
        transcript=dict(
            filename=transcript.filename,
            revision=transcript.revision,
            cues=transcript.cues,
        )
        if transcript
        else None,
        audio=bool(audio),
    )


@router.post("/{identity}/transcript")
async def import_transcript(
    identity: UUID, file: UploadFile, user: CurrentUser, db: DBSession
):
    await sources(db, user, identity, write=True)
    original = await file.read(4 * 1024 * 1024 + 1)
    if len(original) > 4 * 1024 * 1024:
        raise HTTPException(413, "Transcript exceeds 4 MiB")
    previous = await db.get(MeetingTranscript, identity)
    if previous:
        if original != previous.original:
            raise HTTPException(409, "This meeting already has an original transcript")
        return {"revision": previous.revision}
    filename = Path(file.filename or "").name[:255]
    try:
        cues = parse_transcript(filename, original)
    except ValueError as exc:
        raise HTTPException(422, "Invalid transcript: " + str(exc)[:200]) from None
    db.add(
        MeetingTranscript(
            meeting_id=identity,
            original=original,
            filename=filename,
            revision=1,
            cues=[cue.model_dump() for cue in cues],
        )
    )
    await db.commit()
    return {"revision": 1}


@router.put("/{identity}/transcript")
async def edit_transcript(identity: UUID, data: Edit, user: CurrentUser, db: DBSession):
    space = await sources(db, user, identity, write=True)
    row = await db.get(MeetingTranscript, identity)
    if not row or row.revision != data.expected_revision:
        raise HTTPException(409, "Transcript changed; review before saving")
    if sum(len(c.text) + len(c.speaker) for c in data.cues) > 4 * 1024 * 1024:
        raise HTTPException(413, "Transcript exceeds 4 MiB")
    candidates = {p["id"]: p["name"] for p in await speaker_people(db, space)}
    revised = []
    for index, cue in enumerate(data.cues):
        account = str(cue.account_id) if cue.account_id else None
        previous = row.cues[index] if index < len(row.cues) else {}
        if account and previous.get("account_id") == account:
            name = previous.get("account_name") or candidates.get(account)
        elif account and account not in candidates:
            raise HTTPException(422, "Choose an eligible speaker account")
        else:
            name = candidates.get(account)
        revised.append(dict(cue.model_dump(mode="json"), account_name=name))
    row.cues = revised
    row.revision += 1
    await db.commit()
    return {"revision": row.revision}


@router.get("/{identity}/transcript/{fmt}")
async def download(
    identity: UUID,
    fmt: Literal["original", "txt", "srt", "vtt"],
    user: CurrentUser,
    db: DBSession,
):
    await sources(db, user, identity)
    row = await db.get(MeetingTranscript, identity)
    if not row:
        raise HTTPException(404, "Transcript unavailable")
    try:
        content = (
            row.original
            if fmt == "original"
            else export_transcript(
                [
                    Cue(
                        **{k: v for k, v in c.items() if k != "account_name"}
                    ).model_copy(
                        update={"speaker": c.get("account_name") or c["speaker"]}
                    )
                    for c in row.cues
                ],
                fmt,
            )
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    name = row.filename if fmt == "original" else f"transcript.{fmt}"
    return Response(
        content,
        media_type="text/vtt" if fmt == "vtt" else "application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(name, safe='')}",
        },
    )


@router.post("/{identity}/audio")
async def attach_audio(
    identity: UUID, file: UploadFile, user: CurrentUser, db: DBSession
):
    await sources(db, user, identity, write=True)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in FORMATS:
        raise HTTPException(422, "Unsupported audio format")
    size, digest = 0, hashlib.sha256()
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > 256 * 1024 * 1024:
            raise HTTPException(413, "Recording exceeds 256 MiB")
        digest.update(chunk)
    if not size:
        raise HTTPException(422, "Empty recording")
    key = f"meeting-recordings/{identity}/{digest.hexdigest()}"
    old = await db.get(MeetingAudio, identity)
    if old:
        if old.storage_key != key:
            raise HTTPException(409, "This meeting already has a recording")
        return {"audio": True}
    await file.seek(0)
    backend = default_storage_backend()
    await upload_file(key, file.file, FORMATS[ext], size, backend)
    db.add(
        MeetingAudio(
            meeting_id=identity, storage_key=key, mime=FORMATS[ext], backend=backend
        )
    )
    await db.commit()
    return {"audio": True}


@router.get("/{identity}/audio")
async def playback(identity: UUID, user: CurrentUser, db: DBSession):
    await sources(db, user, identity)
    row = await db.get(MeetingAudio, identity)
    if not row:
        raise HTTPException(404, "Recording unavailable")
    return StreamingResponse(
        get_file_with_stream(row.storage_key, row.backend),
        media_type=row.mime,
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{identity}/draft")
async def propose_minutes(identity: UUID, user: CurrentUser, db: DBSession):
    space = await sources(db, user, identity, owner=True)
    transcript = await db.get(MeetingTranscript, identity)
    if not space or not transcript:
        raise HTTPException(422, "Import the meeting transcript first")
    await bind_organization(db, space.lab_id)
    require_ai_enabled()
    usage = create_usage_context(
        feature="meeting.draft", user_id=user.id, lab_id=space.lab_id
    )
    parts = []
    current = []
    length = 0
    for cue in transcript.cues:
        text = f"{cue.get('account_name') or cue['speaker']} {cue['text']}".strip()
        for start in range(0, len(text), 15000):
            line = text[start : start + 15000]
            if current and length + len(line) + 1 > 15500:
                parts.append("\n".join(current))
                current, length = [], 0
            current.append(line)
            length += len(line) + 1
    if current:
        parts.append("\n".join(current))
    proposal = None
    enabled = enabled_chat_model_types()
    if not enabled:
        raise HTTPException(503, "No meeting model configured")
    model = ChatModel(model_type=enabled[0]).name
    try:
        for part in parts:
            async with asyncio.timeout(90):
                reply = await draft_meeting(
                    DraftTurn(project_id=identity, message=part, previous=proposal),
                    model,
                    usage,
                )
            proposal = reply.draft or proposal
    except (TimeoutError, httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "Aira could not prepare the draft") from exc
    if not proposal:
        raise HTTPException(422, "Insufficient material for minutes")
    db.expire_all()
    await db.refresh(user)
    await sources(db, user, identity, owner=True)
    return proposal
