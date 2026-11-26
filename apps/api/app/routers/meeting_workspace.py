"""Participant-only cross-project meetings, confirmed minutes and scoped follow-up."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select

from app.database import DBSession
from app.models.lab import Lab, LabUser
from app.models.meeting_workspace import (
    MeetingFollowUp,
    MeetingFollowUpReader,
    MeetingMinutesShare,
    MeetingSpace,
)
from app.models.project import Project
from app.models.project_guest import OrganizationGuestProfile
from app.models.research import ResearchTask
from app.models.research_log import ResearchLogEntry
from app.models.user import User
from app.routers.depends import CurrentUser, guest_endpoint
from app.services.knowledge import canonical_digest
from app.services.meetings import lock_meeting_key
from app.services.meeting_workspace import (
    add_minutes_edition,
    guest,
    links,
    member,
    restricted_tasks,
    room_view,
    set_links,
    sources,
    unavailable,
)
from app.services.project_people import organization_accounts
from app.services.project_work import project_context
from app.services.project_work_contracts import PUBLIC_STATES, WorkCreate

router = APIRouter(prefix="/meeting-workspace", tags=["meetings"])


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Room(Strict):
    id: UUID
    lab_id: UUID
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(max_length=200000)
    body_format: Literal["md", "aimd"] = "aimd"
    occurred_at: datetime
    project_ids: list[UUID] = Field(default_factory=list, max_length=50)
    participants: list[UUID] = Field(default_factory=list, max_length=200)
    expected_revision: int = Field(ge=0)

    @field_validator("occurred_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Include a time zone")
        return value


class Share(Strict):
    revision: int = Field(ge=1)
    users: list[UUID] = Field(max_length=200)


class Action(Strict):
    id: UUID
    expected_revision: int = Field(ge=1)
    audience: Literal["personal", "selected", "project"] = "personal"
    project_id: UUID | None = None
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10000)
    due: date | None = None
    assignee_id: UUID | None = None
    readers: list[UUID] = Field(default_factory=list, max_length=100)


class State(Strict):
    expected_revision: int = Field(ge=1)
    state: Literal["pending", "in_progress", "done"]


@router.get("/organizations")
async def organizations(user: CurrentUser, db: DBSession):
    rows = await db.execute(
        select(Lab.id, Lab.name)
        .join(LabUser, LabUser.lab_id == Lab.id)
        .where(LabUser.user_id == user.id)
        .order_by(Lab.name, Lab.id)
    )
    return rows.mappings().all()


@router.get("/organizations/{lab_id}/options")
async def room_options(
    lab_id: UUID, user: CurrentUser, db: DBSession, project_id: UUID | None = None
):
    if not await db.scalar(select(member(lab_id, user.id))):
        raise unavailable()
    from app.routers.my_work import readable_projects

    projects = await readable_projects(db, user, "visible", None)
    org_projects = list(
        await db.scalars(
            select(Project.id).where(Project.lab_id == lab_id, Project.id.in_(projects))
        )
    )
    result = [
        dict(id=u.id, name=name, username=u.username)
        for u, name in await db.execute(organization_accounts(lab_id))
    ]
    if project_id:
        if project_id not in org_projects:
            raise unavailable()
        rows = await db.execute(
            select(User, OrganizationGuestProfile.display_name)
            .outerjoin(
                OrganizationGuestProfile,
                (OrganizationGuestProfile.user_id == User.id)
                & (OrganizationGuestProfile.lab_id == lab_id),
            )
            .where(guest(project_id, User.id))
        )
        result.extend(
            dict(id=u.id, name=name or u.name or u.username, username=u.username)
            for u, name in rows
        )
    return dict(people=result, projects=[projects[pid] for pid in org_projects])


@router.put("/rooms/{identity}")
async def save_room(identity: UUID, data: Room, user: CurrentUser, db: DBSession):
    if data.id != identity or not await db.scalar(select(member(data.lab_id, user.id))):
        raise unavailable()
    # Serialize creation/retries and revisions without locking other meetings.
    await lock_meeting_key(db, identity)
    space = await db.get(MeetingSpace, identity, with_for_update=True)
    digest = canonical_digest(data.model_dump(mode="json"))
    if space:
        if (
            space.owner_id != user.id
            or space.lab_id != data.lab_id
            or space.project_meeting_id
        ):
            raise unavailable()
        if space.digest == digest:
            return await room_view(db, user, identity)
        if space.revision != data.expected_revision:
            raise HTTPException(409, "Meeting changed; review the latest version")
    else:
        if data.expected_revision or await db.get(ResearchLogEntry, identity):
            raise HTTPException(409, "Meeting identity or revision conflict")
        space = MeetingSpace(
            id=identity, lab_id=data.lab_id, owner_id=user.id, revision=0
        )
        db.add(space)
    space.title, space.body, space.body_format = data.title, data.body, data.body_format
    space.occurred_at, space.digest = data.occurred_at, digest
    space.revision += 1
    await db.flush()
    await set_links(db, space, user, data.project_ids, data.participants)
    add_minutes_edition(db, space)
    await db.commit()
    return await room_view(db, user, identity)


@router.get("/rooms/{identity}")
async def get_room(identity: UUID, user: CurrentUser, db: DBSession):
    return await room_view(db, user, identity)


@router.put("/rooms/{identity}/share")
async def share_minutes(identity: UUID, data: Share, user: CurrentUser, db: DBSession):
    space = await sources(db, user, identity, write=True)
    if space.project_meeting_id or space.revision != data.revision:
        raise HTTPException(
            409, "Check the current organization minutes before sharing"
        )
    users = set(data.users)
    valid = set(
        await db.scalars(
            select(LabUser.user_id).where(
                LabUser.lab_id == space.lab_id, LabUser.user_id.in_(users)
            )
        )
    )
    if users != valid:
        raise HTTPException(422, "Choose current organization members")
    await db.execute(
        delete(MeetingMinutesShare).where(MeetingMinutesShare.meeting_id == identity)
    )
    db.add_all(
        [
            MeetingMinutesShare(
                meeting_id=identity, user_id=uid, revision=data.revision
            )
            for uid in users
        ]
    )
    await db.commit()
    return {"shared": len(users)}


def task_view(task):
    return {
        key: getattr(task, key)
        for key in (
            "id",
            "title",
            "description",
            "due",
            "assignee_id",
            "state",
            "audience",
            "revision",
        )
    }


@router.post("/rooms/{identity}/actions")
async def add_action(identity: UUID, data: Action, user: CurrentUser, db: DBSession):
    space = await sources(db, user, identity, write=True)
    await lock_meeting_key(db, data.id, "meeting-action")
    digest = canonical_digest(data.model_dump(mode="json"))
    previous = await db.get(MeetingFollowUp, data.id)
    if previous:
        if (
            previous.meeting_id != identity
            or previous.owner_id != user.id
            or previous.digest != digest
        ):
            raise HTTPException(409, "Task identity is already in use")
        return {"id": previous.id}
    revision = (
        (await db.get(ResearchLogEntry, identity)).revision
        if space.project_meeting_id
        else space.revision
    )
    if revision != data.expected_revision:
        raise HTTPException(409, "Review the current minutes")
    if data.project_id:
        if data.project_id not in await links(db, space):
            raise HTTPException(422, "Choose a linked project")
        await project_context(db, user, data.project_id)
    assignee = data.assignee_id
    if data.audience == "personal":
        if (assignee and assignee != user.id) or data.readers:
            raise HTTPException(422, "A personal task is visible only to its creator")
        assignee = user.id
    readers = set(data.readers)
    if data.audience == "project":
        if not data.project_id or readers:
            raise HTTPException(422, "Choose the project audience")
        from app.routers.project_work import create_work_impl

        await project_context(db, user, data.project_id, write=True, lock=True)
        # Prevent adopting a pre-existing task with a coincidentally identical create digest.
        if await db.get(ResearchTask, data.id):
            raise HTTPException(409, "Task identity is already in use")
        await create_work_impl(
            WorkCreate(
                id=data.id,
                project_id=data.project_id,
                title=data.title,
                goal=data.description,
                assignee_user_id=assignee,
                planned_end=data.due,
            ),
            user,
            db,
        )
    else:
        for uid in readers | ({assignee} if assignee else set()):
            eligible = member(space.lab_id, uid)
            if data.project_id:
                eligible = eligible | guest(data.project_id, uid)
            if not await db.scalar(select(eligible)):
                raise HTTPException(
                    422,
                    "Recipient needs organization membership or an active project invitation",
                )
    project_wide = data.audience == "project"
    task = MeetingFollowUp(
        id=data.id,
        meeting_id=identity,
        source_revision=revision,
        owner_id=user.id,
        project_id=data.project_id,
        project_work_id=data.id if project_wide else None,
        assignee_id=assignee,
        title="" if project_wide else data.title,
        description="" if project_wide else data.description,
        due=None if project_wide else data.due,
        state="pending",
        audience=data.audience,
        revision=1,
        digest=digest,
    )
    db.add(task)
    await db.flush()
    db.add_all([MeetingFollowUpReader(task_id=data.id, user_id=uid) for uid in readers])
    await db.commit()
    return {"id": task.id}


@router.get("/rooms/{identity}/actions")
async def list_actions(identity: UUID, user: CurrentUser, db: DBSession):
    await sources(db, user, identity)
    rows = await db.scalars(
        restricted_tasks(user.id)
        .where(MeetingFollowUp.meeting_id == identity)
        .order_by(MeetingFollowUp.id)
    )
    result = [task_view(row) for row in rows]
    from app.models.project_work import ProjectWork
    from app.routers.my_work import readable_projects

    projects = await readable_projects(db, user, "visible", None)
    shared = await db.execute(
        select(ResearchTask, ProjectWork)
        .join(ProjectWork, ProjectWork.task_id == ResearchTask.id)
        .join(MeetingFollowUp, MeetingFollowUp.project_work_id == ResearchTask.id)
        .where(
            MeetingFollowUp.meeting_id == identity,
            ResearchTask.project_id.in_(projects),
            ResearchTask.archived_at.is_(None),
        )
    )
    for task, detail in shared:
        result.append(
            dict(
                id=task.id,
                title=task.title,
                state=PUBLIC_STATES.get(task.status, task.status),
                audience="project",
                assignee_id=detail.assignee_user_id,
                due=detail.planned_end,
                href=f"{projects[task.project_id]['path']}/work?item={task.id}",
            )
        )
    return result


@router.get("/tasks")
@guest_endpoint
async def assigned_tasks(user: CurrentUser, db: DBSession):
    rows = await db.scalars(
        restricted_tasks(user.id).order_by(
            MeetingFollowUp.due.asc().nulls_last(), MeetingFollowUp.id
        )
    )
    return [
        {**task_view(row), "can_update": user.id in {row.owner_id, row.assignee_id}}
        for row in rows
    ]


@router.get("/tasks/{identity}")
@guest_endpoint
async def one_task(identity: UUID, user: CurrentUser, db: DBSession):
    row = await db.scalar(
        restricted_tasks(user.id).where(MeetingFollowUp.id == identity)
    )
    if not row:
        raise unavailable()
    return {**task_view(row), "can_update": user.id in {row.owner_id, row.assignee_id}}


@router.patch("/tasks/{identity}")
@guest_endpoint
async def change_state(identity: UUID, data: State, user: CurrentUser, db: DBSession):
    row = await db.scalar(
        restricted_tasks(user.id)
        .where(MeetingFollowUp.id == identity)
        .with_for_update(of=MeetingFollowUp)
    )
    if not row or user.id not in {row.owner_id, row.assignee_id}:
        raise unavailable()
    if row.revision != data.expected_revision:
        raise HTTPException(409, "Task changed")
    row.state, row.revision = data.state, row.revision + 1
    await db.commit()
    return task_view(row)
