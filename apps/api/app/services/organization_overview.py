"""Read the organization's live research plan without creating a second schedule."""

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select

from app.models.lab import Lab
from app.models.project import Project, ProjectRole, ProjectUser
from app.models.project_work import ProjectWork
from app.models.research import ResearchTask
from app.routers.labs import require_configured_single_lab, require_lab_manager
from app.services.project_people import organization_names
from app.services.project_work_contracts import STORED_STATES


async def require_overview_access(db, user, lab_id):
    lab = await db.get(Lab, lab_id)
    if lab is None:
        raise HTTPException(404, "Organization not found")
    require_configured_single_lab(lab)
    await require_lab_manager(db, lab_id, user.id)


async def organization_project_overview(db, user, lab_id):
    await require_overview_access(db, user, lab_id)
    projects = await db.execute(
        select(Project.id, Project.uid, Project.name)
        .where(Project.lab_id == lab_id, Project.deleted_at.is_(None))
        .order_by(Project.name, Project.id)
    )
    rows = {
        p.id: {
            "id": p.id,
            "uid": p.uid,
            "name": p.name,
            "owners": [],
            "blockers": [],
            "next_steps": [],
            "milestone": None,
        }
        for p in projects
    }
    if not rows:
        return []
    memberships = (
        await db.execute(
            select(ProjectUser.project_id, ProjectUser.user_id)
            .where(
                ProjectUser.project_id.in_(rows), ProjectUser.role == ProjectRole.OWNER
            )
            .order_by(ProjectUser.created_at, ProjectUser.id)
        )
    ).all()
    names = await organization_names(db, lab_id, {m.user_id for m in memberships})
    for m in memberships:
        if m.user_id in names:
            rows[m.project_id]["owners"].append(names[m.user_id])

    blocked = ResearchTask.status == STORED_STATES["blocked"]
    planned = func.coalesce(ProjectWork.planned_end, ProjectWork.planned_start)
    tasks = await db.execute(
        select(
            ResearchTask.project_id,
            ResearchTask.id,
            ResearchTask.title,
            blocked.label("blocked"),
            ProjectWork.blocker,
            ProjectWork.next_step,
            ProjectWork.kind,
            planned.label("planned"),
        )
        .join(ProjectWork, ProjectWork.task_id == ResearchTask.id)
        .where(
            ResearchTask.project_id.in_(rows),
            ResearchTask.archived_at.is_(None),
            ResearchTask.status.not_in(
                [STORED_STATES["done"], STORED_STATES["cancelled"]]
            ),
            or_(blocked, ProjectWork.next_step != "", ProjectWork.kind == "milestone"),
        )
        .order_by(
            blocked.desc(),
            case(
                {"urgent": 0, "high": 1, "normal": 2},
                value=ProjectWork.priority,
                else_=3,
            ),
            planned.asc().nullslast(),
            ResearchTask.id,
        )
    )
    for task in tasks:
        project = rows[task.project_id]
        link = {"id": task.id, "title": task.title}
        if task.blocked:
            project["blockers"].append({**link, "text": task.blocker})
        if task.next_step:
            project["next_steps"].append({**link, "text": task.next_step})
        if task.kind == "milestone":
            current = project["milestone"]
            if current is None or (
                task.planned and (not current["date"] or task.planned < current["date"])
            ):
                project["milestone"] = {**link, "date": task.planned}
    return sorted(rows.values(), key=lambda p: not p["blockers"])
