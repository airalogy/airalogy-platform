"""Personal cross-project meeting agenda and work queue, derived from the original rows."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Date, case, cast, func, literal, or_, select, union_all

from app.database import DBSession
from app.models.group import GroupProject
from app.models.lab import Lab, LabUser
from app.models.meeting import Meeting, MeetingParticipant, MeetingWorkLink
from app.models.meeting_workspace import (
    MeetingFollowUp,
    MeetingMinutesEdition,
    MeetingMinutesShare,
    MeetingSpace,
    MeetingSpaceProject,
)
from app.services.meeting_workspace import (
    action_sources,
    member,
    participant,
    restricted_tasks,
)
from app.models.project import Project, ProjectUser
from app.models.project_person import ProjectPerson
from app.models.project_work import ProjectWork
from app.models.research import (
    ResearchAction,
    ResearchApproval,
    ResearchHumanWorkItem,
    ResearchRun,
    ResearchTask,
)
from app.models.research_log import ResearchLogEntry
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.access_control import (
    LEGACY_ROLE_KEY,
    ROLE_CAPABILITIES,
    organizational_unit_ids_for_user,
    structured_project_ids_for_action,
)
from app.services.browser_paths import project_browser_path
from app.services.meetings import meeting_read_condition, work_meetings
from app.services.project_work_contracts import PUBLIC_STATES
from app.services.research_runtime import ACTIVE_WORK_ITEM_STATUSES

router = APIRouter(prefix="/my-work", tags=["personal workspace"])
Scope = Literal["mine", "managed", "visible"]
Period = Literal["upcoming", "past", "undated"]


async def readable_projects(db, user, scope, project_id):
    query = (
        select(Project, Lab.uid)
        .join(Lab, Lab.id == Project.lab_id)
        .join(LabUser, LabUser.lab_id == Lab.id)
        .where(LabUser.user_id == user.id, Project.deleted_at.is_(None))
        .order_by(Lab.name, Project.name, Project.id)
    )
    if project_id:
        query = query.where(Project.id == project_id)
    rows = (await db.execute(query)).all()
    managed_role = "project_manager" if scope == "managed" else None
    allowed = await structured_project_ids_for_action(
        db,
        user.id,
        [project for project, _ in rows],
        "research.read",
        role_key_filter=managed_role,
    )
    legacy_roles = [
        role
        for role, key in LEGACY_ROLE_KEY.items()
        if "research.read" in ROLE_CAPABILITIES[key]
        and (not managed_role or key == managed_role)
    ]
    by_lab = {}
    for project, _ in rows:
        by_lab.setdefault(project.lab_id, []).append(project.id)
    for lab_id, candidates in by_lab.items():
        units = await organizational_unit_ids_for_user(db, user.id, lab_id)
        direct = select(ProjectUser.project_id).where(
            ProjectUser.user_id == user.id,
            ProjectUser.project_id.in_(candidates),
            ProjectUser.role.in_(legacy_roles),
        )
        group = select(GroupProject.project_id).where(
            GroupProject.group_id.in_(units),
            GroupProject.project_id.in_(candidates),
            GroupProject.role.in_(legacy_roles),
        )
        allowed.update(await db.scalars(direct.union(group)))
    return {
        project.id: {
            "id": project.id,
            "name": project.name,
            "path": project_browser_path(lab_uid, project.uid),
        }
        for project, lab_uid in rows
        if project.id in allowed
    }


async def meeting_rows(
    db,
    user,
    projects,
    scope,
    period,
    zone,
    today,
    offset,
    limit,
    planned_only=False,
    project_filter=None,
):
    entry = ResearchLogEntry
    event_at = case(
        (Meeting.status == "held", entry.occurred_at), else_=Meeting.scheduled_at
    )
    date_zone = case((Meeting.time_precision == "date", Meeting.time_zone), else_=zone)
    day = cast(func.timezone(date_zone, event_at), Date)
    open_work = (
        select(func.count())
        .select_from(MeetingWorkLink)
        .join(ResearchTask, ResearchTask.id == MeetingWorkLink.task_id)
        .where(
            MeetingWorkLink.meeting_id == entry.id,
            ResearchTask.project_id == entry.project_id,
            ResearchTask.archived_at.is_(None),
            ResearchTask.status.not_in(("completed", "cancelled")),
        )
        .correlate(entry)
        .scalar_subquery()
    )
    restricted_ids = (
        restricted_tasks(user.id).with_only_columns(MeetingFollowUp.id).subquery()
    )

    def followup_count(identity):
        f = MeetingFollowUp
        return (
            select(func.count(f.id))
            .outerjoin(ResearchTask, ResearchTask.id == f.project_work_id)
            .where(
                f.meeting_id == identity,
                ((f.id.in_(select(restricted_ids.c.id))) & (f.state != "done"))
                | (
                    (ResearchTask.project_id.in_(projects))
                    & ResearchTask.archived_at.is_(None)
                    & ResearchTask.status.not_in(
                        ("completed", "cancelled", "failed", "archived")
                    )
                ),
            )
            .correlate(identity.class_)
            .scalar_subquery()
        )

    query = (
        select(
            entry.id,
            entry.title,
            entry.project_id,
            Meeting.status,
            Meeting.time_precision,
            day.label("day"),
            event_at.label("at"),
            (open_work + followup_count(entry.id)).label("open_count"),
        )
        .join(Meeting, Meeting.document_id == entry.id)
        .where(
            entry.project_id.in_(projects),
            entry.archived_at.is_(None),
            meeting_read_condition(user.id),
        )
    )
    if scope == "mine":
        participating = select(MeetingParticipant.meeting_id).where(
            MeetingParticipant.attendance != "absent",
            or_(
                MeetingParticipant.user_id == user.id,
                MeetingParticipant.person_id.in_(
                    select(ProjectPerson.id).where(ProjectPerson.user_id == user.id)
                ),
            ),
        )
        query = query.where(
            or_(entry.created_by_user_id == user.id, entry.id.in_(participating))
        )
    org = MeetingSpace
    is_attendee = participant(org.id, user.id) | (org.owner_id == user.id)
    shared = MeetingMinutesShare
    edition = MeetingMinutesEdition
    at = case((is_attendee, org.occurred_at), else_=edition.occurred_at)
    org_query = (
        select(
            org.id,
            case((is_attendee, org.title), else_=edition.title).label("title"),
            literal(None, type_=entry.project_id.type).label("project_id"),
            case((at > func.now(), "planned"), else_="held").label("status"),
            literal("datetime").label("time_precision"),
            cast(func.timezone(zone, at), Date).label("day"),
            at.label("at"),
            case((is_attendee, followup_count(org.id)), else_=0).label("open_count"),
            Lab.name.label("org_name"),
        )
        .join(Lab, Lab.id == org.lab_id)
        .outerjoin(shared, (shared.meeting_id == org.id) & (shared.user_id == user.id))
        .outerjoin(
            edition,
            (edition.meeting_id == org.id) & (edition.revision == shared.revision),
        )
        .where(
            org.project_meeting_id.is_(None),
            member(org.lab_id, user.id),
            is_attendee | (shared.user_id == user.id),
        )
    )
    if project_filter or scope == "managed":
        org_query = org_query.where(
            is_attendee,
            org.id.in_(
                select(MeetingSpaceProject.meeting_id).where(
                    MeetingSpaceProject.project_id.in_(projects)
                )
            ),
        )
    combined = union_all(
        query.add_columns(literal("").label("org_name")), org_query
    ).subquery()
    c = combined.c
    query = select(combined)
    day, event_at = c.day, c.at
    if planned_only:
        query = query.where(c.status == "planned")
    if period == "upcoming":
        query = query.where(day >= today).order_by(day, event_at, c.id)
    elif period == "recent":
        query = query.where(c.status == "held", day <= today).order_by(
            day.desc(), event_at.desc(), c.id
        )
    elif period == "past":
        query = query.where(day < today).order_by(day.desc(), event_at.desc(), c.id)
    else:
        query = query.where(event_at.is_(None)).order_by(c.title, c.id)
    return [
        {
            **r,
            "project": projects[r.project_id]["name"] if r.project_id else r.org_name,
            "href": f"{projects[r.project_id]['path']}/meetings?meeting={r.id}"
            if r.project_id
            else f"/my-work?room={r.id}",
        }
        for r in (await db.execute(query.offset(offset).limit(limit))).mappings()
    ]


async def todo_rows(
    db, user, projects, scope, zone, today, offset, limit, project_filter=None
):
    task, work = ResearchTask, ProjectWork
    active = (
        task.project_id.in_(projects),
        task.archived_at.is_(None),
        task.status.not_in(("completed", "cancelled", "failed", "archived")),
    )
    assignee = func.coalesce(
        ProjectPerson.name, func.nullif(User.name, ""), User.username
    )
    coordination = (
        select(
            task.id,
            task.id.label("task_id"),
            task.project_id,
            task.title,
            work.kind,
            task.status,
            work.planned_end.label("due"),
            assignee.label("assignee"),
        )
        .join(work, work.task_id == task.id)
        .outerjoin(ProjectPerson, ProjectPerson.id == work.assignee_person_id)
        .outerjoin(User, User.id == work.assignee_user_id)
        .where(*active)
    )

    def local_day(column):
        return cast(func.timezone(zone, column), Date)

    owner = func.coalesce(func.nullif(User.name, ""), User.username)
    research = (
        select(
            task.id,
            task.id,
            task.project_id,
            task.title,
            literal("research"),
            task.status,
            local_day(task.deadline_at),
            owner,
        )
        .join(User, User.id == task.owner_user_id)
        .where(*active, ~select(work.task_id).where(work.task_id == task.id).exists())
    )
    if scope == "mine":
        coordination = coordination.where(
            or_(work.assignee_user_id == user.id, ProjectPerson.user_id == user.id)
        )
        research = research.where(task.owner_user_id == user.id)

    def action_rows(model, kind, who, due, condition):
        return (
            select(
                model.id,
                task.id,
                task.project_id,
                ResearchAction.title,
                literal(kind),
                model.status,
                local_day(due),
                owner,
            )
            .select_from(model)
            .join(ResearchAction, ResearchAction.id == model.action_id)
            .join(ResearchRun, ResearchRun.id == ResearchAction.run_id)
            .join(task, task.id == ResearchRun.task_id)
            .join(User, User.id == who)
            .where(*active, condition)
        )

    manual = action_rows(
        ResearchHumanWorkItem,
        "manual",
        ResearchHumanWorkItem.assignee_user_id,
        ResearchHumanWorkItem.due_at,
        ResearchHumanWorkItem.status.in_(ACTIVE_WORK_ITEM_STATUSES),
    )
    approvals = action_rows(
        ResearchApproval,
        "approval",
        ResearchApproval.approver_user_id,
        ResearchAction.due_at,
        ResearchApproval.status == "pending",
    )
    if scope == "mine":
        manual = manual.where(ResearchHumanWorkItem.assignee_user_id == user.id)
        approvals = approvals.where(ResearchApproval.approver_user_id == user.id)
    f = MeetingFollowUp
    limited = (
        restricted_tasks(user.id)
        .with_only_columns(
            f.id,
            f.id,
            f.project_id,
            f.title,
            literal("followup"),
            f.state,
            f.due,
            User.name,
        )
        .outerjoin(User, User.id == f.assignee_id)
        .where(f.state != "done")
    )
    if project_filter or scope == "managed":
        limited = limited.where(f.project_id.in_(projects))
    if scope == "mine":
        limited = limited.where((f.owner_id == user.id) | (f.assignee_id == user.id))
    items = union_all(coordination, research, manual, approvals, limited).subquery()
    c = items.c
    priority = case(
        (c.due < today, 0), (c.due == today, 1), (c.status == "paused", 2), else_=3
    )
    rows = (
        (
            await db.execute(
                select(items)
                .order_by(priority, c.due.asc().nulls_last(), c.title, c.kind, c.id)
                .offset(offset)
                .limit(limit)
            )
        )
        .mappings()
        .all()
    )
    coordination_ids = [
        r.id for r in rows if r.kind not in ("research", "manual", "approval")
    ]
    meetings = await work_meetings(db, user.id, coordination_ids)
    sources = await action_sources(db, user.id, coordination_ids, projects)
    result = []
    for r in rows:
        source_links = [sources[r.id]] if r.id in sources else []
        if r.kind == "followup":
            result.append(
                {
                    **r,
                    "href": f"/my-work?task={r.id}",
                    "meetings": source_links,
                    "project_id": r.project_id if r.project_id in projects else None,
                    "project": projects.get(r.project_id, {}).get("name", ""),
                }
            )
            continue
        project = projects[r.project_id]
        href = f"/research/tasks/{r.task_id}"
        state = r.status
        if r.kind == "manual":
            href = f"/research/work-items/{r.id}"
        elif r.kind == "approval":
            href += "#research-approvals"
        elif r.kind != "research":
            href = f"{project['path']}/work?item={r.id}"
            state = PUBLIC_STATES.get(state, state)
        result.append(
            {
                **r,
                "status": state,
                "project": project["name"],
                "href": href,
                "meetings": [
                    {
                        **meeting,
                        "href": f"{project['path']}/meetings?meeting={meeting['id']}",
                    }
                    for meeting in meetings.get(r.id, [])
                ]
                + source_links,
            }
        )
    return result


@router.get("")
async def my_work(
    current_user: CurrentUser,
    db: DBSession,
    view: Literal["meetings", "todos", "summary", "projects"] = "meetings",
    scope: Scope = "mine",
    period: Period = "upcoming",
    project_id: UUID | None = None,
    time_zone: str = "UTC",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        today = datetime.now(UTC).astimezone(ZoneInfo(time_zone)).date()
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Unknown time zone") from None
    projects = await readable_projects(db, current_user, scope, project_id)
    if view == "projects":
        return {"projects": list(projects.values())}
    if view == "summary":
        meetings = await meeting_rows(
            db,
            current_user,
            projects,
            "mine",
            "upcoming",
            time_zone,
            today,
            0,
            1,
            planned_only=True,
        )
        if not meetings:
            meetings = await meeting_rows(
                db, current_user, projects, "mine", "recent", time_zone, today, 0, 1
            )
        todos = await todo_rows(
            db, current_user, projects, "mine", time_zone, today, 0, 1
        )
        return {"meeting": next(iter(meetings), None), "todo": next(iter(todos), None)}
    offset = (page - 1) * page_size
    if view == "meetings":
        items = await meeting_rows(
            db,
            current_user,
            projects,
            scope,
            period,
            time_zone,
            today,
            offset,
            page_size + 1,
            project_filter=project_id,
        )
    else:
        items = await todo_rows(
            db,
            current_user,
            projects,
            scope,
            time_zone,
            today,
            offset,
            page_size + 1,
            project_filter=project_id,
        )
    return {"items": items[:page_size], "has_more": len(items) > page_size}
