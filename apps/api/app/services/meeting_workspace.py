from fastapi import HTTPException
from sqlalchemy import delete, or_, select

from app.models.lab import LabUser
from app.services.meetings import attending_account
from app.models.meeting_workspace import (
    MeetingFollowUp,
    MeetingFollowUpReader,
    MeetingMinutesEdition,
    MeetingMinutesShare,
    MeetingSpace,
    MeetingSpacePerson,
    MeetingSpaceProject,
)
from app.models.project import Project
from app.models.project_guest import ProjectGuest
from app.routers import meetings
from app.services.project_work import project_context
from app.services.single_lab import utcnow


def unavailable():
    return HTTPException(404, "Meeting or task unavailable")


def member(lab_id, user_id):
    return (
        select(LabUser.id)
        .where(LabUser.lab_id == lab_id, LabUser.user_id == user_id)
        .exists()
    )


def guest(project_id, user_id):
    return (
        select(ProjectGuest.user_id)
        .join(Project, Project.id == ProjectGuest.project_id)
        .where(
            ProjectGuest.project_id == project_id,
            ProjectGuest.user_id == user_id,
            Project.deleted_at.is_(None),
            or_(
                ProjectGuest.access_until.is_(None),
                ProjectGuest.access_until > utcnow(),
            ),
        )
        .exists()
    )


def participant(identity, user_id):
    return (
        select(MeetingSpacePerson.user_id)
        .where(
            MeetingSpacePerson.meeting_id == identity,
            MeetingSpacePerson.user_id == user_id,
        )
        .exists()
    )


async def sources(db, user, identity, *, write=False, owner=False):
    """Resolve project or organization scope before returning any private source."""
    query = select(MeetingSpace).where(MeetingSpace.id == identity)
    space = await db.scalar(query.with_for_update() if write else query)
    if space and not space.project_meeting_id:
        if not await db.scalar(select(member(space.lab_id, user.id))):
            raise unavailable()
        if space.owner_id != user.id and (
            write
            or owner
            or not await db.scalar(select(participant(identity, user.id)))
        ):
            raise unavailable()
        return space
    entry, _, project = await meetings.context(
        db, user, identity, "manage" if write or owner else "read", lock=write
    )
    if entry.created_by_user_id != user.id and not await db.scalar(select(attending_account(identity, user.id))):
        raise unavailable()
    if not space and write:
        space = await db.get(MeetingSpace, identity, populate_existing=True)
        if space is None:
            space = MeetingSpace(
                id=identity,
                project_meeting_id=identity,
                lab_id=project.lab_id,
                owner_id=entry.created_by_user_id,
                digest="",
            )
            db.add(space)
            await db.flush()
    return space


async def set_links(db, space, user, projects, people):
    for pid in projects:
        project = await project_context(db, user, pid)
        if project.lab_id != space.lab_id:
            raise HTTPException(422, "Choose a project in this organization")
    if people:
        eligible = set(
            await db.scalars(
                select(LabUser.user_id).where(
                    LabUser.lab_id == space.lab_id, LabUser.user_id.in_(people)
                )
            )
        )
        if set(people) != eligible:
            raise HTTPException(422, "Choose current organization members")
    await db.execute(
        delete(MeetingSpaceProject).where(MeetingSpaceProject.meeting_id == space.id)
    )
    await db.execute(
        delete(MeetingSpacePerson).where(MeetingSpacePerson.meeting_id == space.id)
    )
    db.add_all(
        [
            MeetingSpaceProject(meeting_id=space.id, project_id=pid)
            for pid in set(projects)
        ]
    )
    db.add_all(
        [MeetingSpacePerson(meeting_id=space.id, user_id=uid) for uid in set(people)]
    )
    await db.flush()


def restricted_tasks(user_id):
    task = MeetingFollowUp
    audience = (
        select(MeetingFollowUpReader.user_id)
        .where(
            MeetingFollowUpReader.task_id == task.id,
            MeetingFollowUpReader.user_id == user_id,
        )
        .exists()
    )
    return (
        select(task)
        .join(MeetingSpace, MeetingSpace.id == task.meeting_id)
        .where(
            task.project_work_id.is_(None),
            or_(member(MeetingSpace.lab_id, user_id), guest(task.project_id, user_id)),
            or_(task.owner_id == user_id, task.assignee_id == user_id, audience),
        )
    )


async def links(db, space):
    if space.project_meeting_id:
        from app.models.research_log import ResearchLogEntry

        entry = await db.get(ResearchLogEntry, space.id)
        return [entry.project_id]
    return list(
        await db.scalars(
            select(MeetingSpaceProject.project_id).where(
                MeetingSpaceProject.meeting_id == space.id
            )
        )
    )


async def room_view(db, user, identity):
    space = await db.get(MeetingSpace, identity)
    if (
        not space
        or space.project_meeting_id
        or not await db.scalar(select(member(space.lab_id, user.id)))
    ):
        raise unavailable()
    own = space.owner_id == user.id
    inside = own or await db.scalar(select(participant(identity, user.id)))
    if not inside:
        share = await db.get(MeetingMinutesShare, (identity, user.id))
        edition = (
            await db.get(MeetingMinutesEdition, (identity, share.revision))
            if share
            else None
        )
        if not edition:
            raise unavailable()
        return dict(
            id=identity,
            title=edition.title,
            body=edition.body,
            body_format=edition.body_format,
            revision=edition.revision,
            occurred_at=edition.occurred_at,
            can_manage=False,
            can_read_sources=False,
            project_ids=[],
            participants=[],
            shared_with=[],
        )
    from app.routers.my_work import readable_projects

    allowed_projects = await readable_projects(db, user, "visible", None)
    project_ids = [pid for pid in await links(db, space) if pid in allowed_projects]
    from app.models.user import User
    from app.services.project_people import organization_accounts

    ids = list(
        await db.scalars(
            select(MeetingSpacePerson.user_id).where(
                MeetingSpacePerson.meeting_id == identity
            )
        )
    )
    people = await db.execute(
        organization_accounts(space.lab_id).where(User.id.in_(ids))
    )
    return dict(
        projects=[allowed_projects[pid] for pid in project_ids],
        attendees=[dict(id=u.id, name=name, username=u.username) for u, name in people],
        id=identity,
        title=space.title,
        body=space.body,
        body_format=space.body_format,
        occurred_at=space.occurred_at,
        lab_id=space.lab_id,
        revision=space.revision,
        can_manage=own,
        can_read_sources=True,
        project_ids=project_ids,
        participants=ids,
        shared_with=list(
            await db.scalars(
                select(MeetingMinutesShare.user_id).where(
                    MeetingMinutesShare.meeting_id == identity
                )
            )
        )
        if own
        else [],
    )


async def action_sources(db, user_id, task_ids, projects):
    """Link only to meetings readable independently of the task assignment."""
    if not task_ids:
        return {}
    from app.models.research_log import ResearchLogEntry
    from app.services.meetings import meeting_read_condition

    org = MeetingSpace
    follow = MeetingFollowUp
    entry = ResearchLogEntry
    organization = (
        select(follow.id, org.id, org.title)
        .join(org, org.id == follow.meeting_id)
        .where(
            follow.id.in_(task_ids),
            org.project_meeting_id.is_(None),
            member(org.lab_id, user_id),
            (org.owner_id == user_id) | participant(org.id, user_id),
        )
    )
    result = {
        tid: dict(id=mid, title=title, relation="created", href=f"/my-work?room={mid}")
        for tid, mid, title in await db.execute(organization)
    }
    project = (
        select(follow.id, entry.id, entry.title, entry.project_id)
        .join(org, org.id == follow.meeting_id)
        .join(entry, entry.id == org.project_meeting_id)
        .where(
            follow.id.in_(task_ids),
            entry.project_id.in_(projects),
            entry.archived_at.is_(None),
            meeting_read_condition(user_id),
        )
    )
    for tid, mid, title, pid in await db.execute(project):
        result[tid] = dict(
            id=mid,
            title=title,
            relation="created",
            href=f"{projects[pid]['path']}/meetings?meeting={mid}",
        )
    return result
