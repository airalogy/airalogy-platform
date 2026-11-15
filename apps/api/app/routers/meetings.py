"""Project meeting workflows with one document and one identity per action item."""

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select

from app.database import DBSession
from app.models.meeting import (
    Meeting,
    MeetingAccess,
    MeetingComment,
    MeetingParticipant,
    MeetingWorkLink,
)
from app.models.project_work import ProjectWork
from app.models.research import ResearchTask
from app.models.research_document import ResearchDocument
from app.models.research_log import (
    ResearchLogEntry,
    ResearchLogRevision,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.document_browse import date_bounds
from app.services.knowledge import canonical_digest
from app.services.meetings import (
    MeetingContent,
    authorize_meeting,
    meeting_read_condition,
)
from app.services.project_work import project_context, visible_snapshot, work_snapshot
from app.services.project_work_contracts import WorkCreate
from app.services.research_runtime import has_research_capability

router = APIRouter(prefix="/meetings", tags=["meetings"])


class Create(MeetingContent):
    id: UUID
    project_id: UUID


class Update(MeetingContent):
    expected_revision: int = Field(ge=1)


class Comment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    body: str = Field(min_length=1, max_length=10000)


class WorkLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: UUID
    expected_revision: int = Field(ge=1)


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    expected_revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=255)
    assignee_user_id: UUID | None = None
    planned_end: date | None = None


async def context(db, user, identity, permission="read", lock=False):
    entry = await db.scalar(
        select(ResearchLogEntry)
        .where(ResearchLogEntry.id == identity)
        .with_for_update()
        if lock
        else select(ResearchLogEntry).where(ResearchLogEntry.id == identity)
    )
    if not entry or entry.archived_at or not entry.project_id:
        raise HTTPException(404, "Meeting unavailable")
    project = await project_context(
        db, user, entry.project_id, write=permission != "read"
    )
    meeting = await authorize_meeting(db, user, entry, permission)
    if meeting is None:
        raise HTTPException(404, "Meeting unavailable")
    return entry, meeting, project


async def people(db, meeting_id):
    participants = (
        await db.scalars(
            select(MeetingParticipant)
            .where(MeetingParticipant.meeting_id == meeting_id)
            .order_by(MeetingParticipant.id)
        )
    ).all()
    grants = (
        await db.scalars(
            select(MeetingAccess)
            .where(MeetingAccess.meeting_id == meeting_id)
            .order_by(MeetingAccess.user_id)
        )
    ).all()
    return (
        [
            {
                "user_id": p.user_id,
                "name": p.name,
                "organization": p.organization,
                "attendance": p.attendance,
            }
            for p in participants
        ],
        [{"user_id": g.user_id, "role": g.role} for g in grants],
    )


async def set_people(db, user, project, entry, data):
    previous_people, previous_access = await people(db, entry.id)
    names = {p["user_id"]: p["name"] for p in previous_people if p["user_id"]}
    grants = {g["user_id"]: g["role"] for g in previous_access}
    members = {}
    for identity in {p.user_id for p in data.participants if p.user_id} | {
        g.user_id for g in data.access
    }:
        member = await db.get(User, identity)
        if not member or (
            identity not in names
            and identity not in grants
            and not await has_research_capability(
                db, user=member, project=project, capability="log.read"
            )
        ):
            raise HTTPException(
                422,
                "Account participants and access recipients must have current project access",
            )
        members[identity] = member
    for grant in data.access:
        if grants.get(grant.user_id) == grant.role:
            continue
        if not await has_research_capability(
            db, user=members[grant.user_id], project=project, capability="log.read"
        ):
            raise HTTPException(
                422, "New access recipients need current project access"
            )
        if grant.role in {"editor", "commenter"} and not await has_research_capability(
            db, user=members[grant.user_id], project=project, capability="log.write"
        ):
            raise HTTPException(
                422, "Editors and commenters need current project write access"
            )
    await db.execute(
        delete(MeetingParticipant).where(MeetingParticipant.meeting_id == entry.id)
    )
    await db.execute(delete(MeetingAccess).where(MeetingAccess.meeting_id == entry.id))
    for participant in data.participants:
        value = participant.model_dump()
        if participant.user_id:
            value["name"] = (
                names.get(participant.user_id)
                or members[participant.user_id].name
                or members[participant.user_id].username
            )
        db.add(MeetingParticipant(id=uuid4(), meeting_id=entry.id, **value))
    for grant in data.access:
        db.add(MeetingAccess(meeting_id=entry.id, **grant.model_dump()))


async def revision(db, user, entry, meeting, summary):
    from app.routers.research_documents import _document_snapshot

    doc = await db.get(ResearchDocument, entry.id)
    participants, access = await people(db, entry.id)
    snapshot = _document_snapshot(entry, doc)
    snapshot["meeting"] = {
        "status": meeting.status,
        "visibility": meeting.visibility,
        "time_precision": meeting.time_precision,
        "time_zone": meeting.time_zone,
        "scheduled_at": meeting.scheduled_at.isoformat()
        if meeting.scheduled_at
        else None,
        "participants": [
            {**p, "user_id": str(p["user_id"]) if p["user_id"] else None}
            for p in participants
        ],
        "access": [{**a, "user_id": str(a["user_id"])} for a in access],
    }
    db.add(
        ResearchLogRevision(
            log_entry_id=entry.id,
            revision=entry.revision,
            snapshot=snapshot,
            change_summary=summary,
            created_by_user_id=user.id,
        )
    )


async def payload(db, user, entry, meeting, project, detail=True):
    participants, access = await people(db, entry.id)
    writer = await has_research_capability(
        db, user=user, project=project, capability="log.write"
    )
    own = entry.created_by_user_id == user.id
    role = next((a["role"] for a in access if a["user_id"] == user.id), None)
    result = {
        "id": entry.id,
        "project_id": entry.project_id,
        "title": entry.title,
        "body": entry.body if detail else "",
        "revision": entry.revision,
        "status": meeting.status,
        "visibility": meeting.visibility,
        "occurred_at": entry.occurred_at if meeting.status == "held" else None,
        "scheduled_at": meeting.scheduled_at,
        "time_precision": meeting.time_precision,
        "time_zone": meeting.time_zone,
        "participants": participants,
        "access": access if own else [],
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "can_manage": own and writer,
        "can_edit": writer and (own or role == "editor"),
        "can_comment": writer
        and (own or meeting.visibility == "project" or role in {"commenter", "editor"}),
        "can_create_work": writer,
    }
    if detail:
        rows = (
            await db.execute(
                select(MeetingWorkLink, ResearchTask, ProjectWork)
                .join(ResearchTask, ResearchTask.id == MeetingWorkLink.task_id)
                .join(ProjectWork, ProjectWork.task_id == ResearchTask.id)
                .where(
                    MeetingWorkLink.meeting_id == entry.id,
                    ResearchTask.archived_at.is_(None),
                )
            )
        ).all()
        result["work"] = [
            {
                "relation": link.relation,
                "source_revision": link.source_revision,
                "item": await visible_snapshot(
                    db, user, project, work_snapshot(task, work)
                ),
            }
            for link, task, work in rows
        ]
    return result


@router.get("/members")
async def meeting_members(
    current_user: CurrentUser, db_session: DBSession, project_id: UUID
):
    from app.models.lab import LabUser

    project = await project_context(db_session, current_user, project_id)
    candidates = (
        await db_session.scalars(
            select(User)
            .join(LabUser, LabUser.user_id == User.id)
            .where(LabUser.lab_id == project.lab_id)
            .order_by(User.name, User.id)
        )
    ).all()
    result = []
    for user in candidates:
        if await has_research_capability(
            db_session, user=user, project=project, capability="log.read"
        ):
            result.append(
                {
                    "id": user.id,
                    "name": user.name,
                    "username": user.username,
                    "can_write": await has_research_capability(
                        db_session, user=user, project=project, capability="log.write"
                    ),
                }
            )
    return {"members": result}


@router.get("")
async def list_meetings(
    current_user: CurrentUser,
    db_session: DBSession,
    project_id: UUID,
    q: str = Query("", max_length=200),
    participant_id: UUID | None = None,
    status: Literal["held", "planned", "cancelled"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    time_zone: str = "UTC",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    project = await project_context(db_session, current_user, project_id)
    start, end = date_bounds(date_from, date_to, time_zone)
    query = (
        select(ResearchLogEntry, Meeting)
        .join(Meeting, Meeting.document_id == ResearchLogEntry.id)
        .where(
            ResearchLogEntry.project_id == project.id,
            ResearchLogEntry.archived_at.is_(None),
            meeting_read_condition(current_user.id),
        )
    )
    if q:
        query = query.where(
            ResearchLogEntry.title.icontains(q, autoescape=True)
            | ResearchLogEntry.body.icontains(q, autoescape=True)
        )
    if participant_id:
        query = query.where(
            ResearchLogEntry.id.in_(
                select(MeetingParticipant.meeting_id).where(
                    MeetingParticipant.user_id == participant_id
                )
            )
        )
    if status:
        query = query.where(Meeting.status == status)
    if start:
        query = query.where(ResearchLogEntry.occurred_at >= start)
    if end:
        query = query.where(ResearchLogEntry.occurred_at < end)
    total = await db_session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db_session.execute(
            query.order_by(
                ResearchLogEntry.occurred_at.desc(), ResearchLogEntry.id.desc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return {
        "items": [
            await payload(db_session, current_user, e, m, project, False)
            for e, m in rows
        ],
        "total": total,
        "can_write": await has_research_capability(
            db_session, user=current_user, project=project, capability="log.write"
        ),
    }


@router.post("")
async def create_meeting(
    data: Create, current_user: CurrentUser, db_session: DBSession
):
    project = await project_context(
        db_session, current_user, data.project_id, write=True, lock=True
    )
    digest = canonical_digest(data.model_dump(mode="json"))
    existing = await db_session.get(Meeting, data.id)
    if existing:
        entry, meeting, project = await context(db_session, current_user, data.id)
        if (
            entry.created_by_user_id != current_user.id
            or meeting.create_digest != digest
        ):
            raise HTTPException(
                409, "Meeting creation key belongs to different content"
            )
        return await payload(db_session, current_user, entry, meeting, project)
    if await db_session.get(ResearchLogEntry, data.id):
        raise HTTPException(409, "Document ID already exists")
    entry = ResearchLogEntry(
        id=data.id,
        scope_type="project",
        lab_id=project.lab_id,
        project_id=project.id,
        kind="meeting",
        title=data.title,
        body=data.body,
        occurred_at=data.occurred_at or data.scheduled_at or datetime.now(UTC),
        created_by_user_id=current_user.id,
        revision=1,
    )
    db_session.add(entry)
    await db_session.flush()
    db_session.add(
        ResearchDocument(
            id=entry.id,
            format_version="aimd.v1",
            state="draft",
            record_data={},
            file_ids=[],
            tags=[],
            collection="",
            origin={},
        )
    )
    await db_session.flush()
    meeting = Meeting(
        document_id=entry.id,
        **{
            k: getattr(data, k)
            for k in [
                "status",
                "visibility",
                "scheduled_at",
                "time_precision",
                "time_zone",
            ]
        },
        create_digest=digest,
    )
    db_session.add(meeting)
    await db_session.flush()
    await set_people(db_session, current_user, project, entry, data)
    await db_session.flush()
    await revision(db_session, current_user, entry, meeting, "Meeting created")
    await db_session.commit()
    return await payload(db_session, current_user, entry, meeting, project)


@router.get("/{meeting_id}")
async def get_meeting(
    meeting_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    entry, meeting, project = await context(db_session, current_user, meeting_id)
    return await payload(db_session, current_user, entry, meeting, project)


@router.put("/{meeting_id}")
async def update_meeting(
    meeting_id: UUID, data: Update, current_user: CurrentUser, db_session: DBSession
):
    entry, meeting, project = await context(
        db_session, current_user, meeting_id, "edit", lock=True
    )
    if entry.revision != data.expected_revision:
        raise HTTPException(409, "Meeting changed. Reload and compare before saving.")
    if entry.created_by_user_id != current_user.id:
        current_people, _ = await people(db_session, meeting_id)
        old = [
            {**p, "user_id": str(p["user_id"]) if p["user_id"] else None}
            for p in current_people
        ]
        new = [p.model_dump(mode="json") for p in data.participants]
        if data.visibility != meeting.visibility or data.access or old != new:
            raise HTTPException(
                403, "Only the author changes audience and participants"
            )
    else:
        await set_people(db_session, current_user, project, entry, data)
    entry.title, entry.body = data.title, data.body
    entry.occurred_at = data.occurred_at or data.scheduled_at or entry.occurred_at
    entry.revision += 1
    entry.updated_at = datetime.now(UTC)
    for key in ["status", "visibility", "scheduled_at", "time_precision", "time_zone"]:
        setattr(meeting, key, getattr(data, key))
    await db_session.flush()
    await revision(db_session, current_user, entry, meeting, "Meeting updated")
    await db_session.commit()
    return await payload(db_session, current_user, entry, meeting, project)


@router.get("/{meeting_id}/comments")
async def list_comments(
    meeting_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    page: int = Query(1, ge=1),
):
    await context(db_session, current_user, meeting_id)
    query = (
        select(MeetingComment, User)
        .join(User, User.id == MeetingComment.author_id)
        .where(MeetingComment.meeting_id == meeting_id)
    )
    total = await db_session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db_session.execute(
            query.order_by(MeetingComment.created_at, MeetingComment.id)
            .offset((page - 1) * 50)
            .limit(50)
        )
    ).all()
    return {
        "items": [
            {
                "id": c.id,
                "body": c.body,
                "author": {"id": u.id, "name": u.name, "username": u.username},
                "created_at": c.created_at,
            }
            for c, u in rows
        ],
        "total": total,
    }


@router.post("/{meeting_id}/comments")
async def add_comment(
    meeting_id: UUID, data: Comment, current_user: CurrentUser, db_session: DBSession
):
    await context(db_session, current_user, meeting_id, "comment")
    if not data.body.strip():
        raise HTTPException(422, "Comment cannot be empty")
    await db_session.scalar(
        select(User.id).where(User.id == current_user.id).with_for_update()
    )
    existing = await db_session.get(MeetingComment, data.id)
    if existing:
        if (
            existing.meeting_id != meeting_id
            or existing.author_id != current_user.id
            or existing.body != data.body.strip()
        ):
            raise HTTPException(409, "Comment key belongs to another request")
        return {"id": existing.id}
    db_session.add(
        MeetingComment(
            id=data.id,
            meeting_id=meeting_id,
            author_id=current_user.id,
            body=data.body.strip(),
        )
    )
    await db_session.commit()
    return {"id": data.id}


@router.post("/{meeting_id}/work")
async def link_work(
    meeting_id: UUID, data: WorkLink, current_user: CurrentUser, db_session: DBSession
):
    entry, meeting, project = await context(
        db_session, current_user, meeting_id, "comment", lock=True
    )
    if entry.revision != data.expected_revision:
        raise HTTPException(
            409, "Meeting changed; review the saved meeting before linking work"
        )
    task = await db_session.get(ResearchTask, data.task_id)
    work = await db_session.get(ProjectWork, data.task_id)
    if not task or not work or task.project_id != project.id or task.archived_at:
        raise HTTPException(422, "Choose an existing work item in this project")
    if not await db_session.get(MeetingWorkLink, (meeting_id, task.id)):
        db_session.add(
            MeetingWorkLink(
                meeting_id=meeting_id,
                task_id=task.id,
                relation="discussed",
                source_revision=entry.revision,
                created_by_user_id=current_user.id,
            )
        )
        await db_session.commit()
    return await payload(db_session, current_user, entry, meeting, project)


@router.post("/{meeting_id}/actions")
async def create_action(
    meeting_id: UUID, data: Action, current_user: CurrentUser, db_session: DBSession
):
    from app.routers.project_work import append_event, apply_content, validate_content

    entry, meeting, project = await context(
        db_session, current_user, meeting_id, "comment", lock=True
    )
    await project_context(db_session, current_user, project.id, write=True, lock=True)
    content = WorkCreate(
        id=data.id,
        project_id=project.id,
        title=data.title,
        assignee_user_id=data.assignee_user_id,
        planned_end=data.planned_end,
        evidence=[
            {
                "kind": "document",
                "id": str(meeting_id),
                "version": str(data.expected_revision),
            }
        ],
    )
    digest = canonical_digest(content.model_dump(mode="json"))
    task = await db_session.get(ResearchTask, data.id)
    if task:
        work = await db_session.get(ProjectWork, data.id)
        link = await db_session.get(MeetingWorkLink, (meeting_id, data.id))
        if (
            not work
            or not link
            or task.created_by_user_id != current_user.id
            or work.create_digest != digest
        ):
            raise HTTPException(409, "Action request ID belongs to different content")
        return await payload(db_session, current_user, entry, meeting, project)
    if entry.revision != data.expected_revision:
        raise HTTPException(
            409, "Meeting changed; review the saved minutes before creating an action"
        )
    await validate_content(db_session, current_user, project, content, data.id)
    task = ResearchTask(
        id=data.id,
        lab_id=project.lab_id,
        project_id=project.id,
        title=content.title,
        goal="",
        owner_user_id=current_user.id,
        created_by_user_id=current_user.id,
        revision=1,
    )
    work = ProjectWork(task_id=data.id, create_digest=digest)
    apply_content(task, work, content)
    db_session.add(task)
    await db_session.flush()
    db_session.add(work)
    await db_session.flush()
    db_session.add(
        MeetingWorkLink(
            meeting_id=meeting_id,
            task_id=task.id,
            relation="created",
            source_revision=entry.revision,
            created_by_user_id=current_user.id,
        )
    )
    await append_event(
        db_session,
        current_user,
        task,
        "created",
        {"snapshot": work_snapshot(task, work), "request_digest": digest},
        data.id,
    )
    await db_session.commit()
    return await payload(db_session, current_user, entry, meeting, project)
