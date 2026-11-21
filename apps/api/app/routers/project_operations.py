"""Organization settings, explicit book grants, and gated commercial drill-downs."""

from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import exists, or_, select
from sqlalchemy.exc import IntegrityError

from app.database import DBSession
from app.models.knowledge import ResearchFile
from app.models.lab import LabUser
from app.models.project import Project, ProjectUser
from app.models.project_operations import (
    OperationsBook,
    OperationsEntry,
    OperationsEvent,
    OperationsGrant,
    OperationsOrganization,
)
from app.models.project_work import ProjectWork
from app.models.research import ResearchTask
from app.models.research_document import ResearchDocument
from app.models.research_log import ResearchLogEntry, ResearchLogRevision
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services import project_operations as ops
from app.services.browser_paths import project_browser_path
from app.services.knowledge import authorize_research_file
from app.services.operations_contracts import Change, Form, Role
from app.services.operations_totals import summarize
from app.services.project_people import organization_accounts, organization_display_name
from app.services.project_work import evidence_view
from app.services.research_runtime import has_research_capability

router = APIRouter(prefix="/project-operations", tags=["project-operations"])


class Switch(Form):
    enabled: bool
    expected_revision: int


class BookSettings(Switch):
    grants: dict[UUID, Role | Literal["inherit"]]


def granted_projects(org_id, user_id):
    explicit = select(OperationsGrant.user_id).where(
        OperationsGrant.project_id == Project.id, OperationsGrant.user_id == user_id
    )
    return (
        select(Project)
        .join(OperationsBook, OperationsBook.project_id == Project.id)
        .where(
            Project.lab_id == org_id,
            Project.deleted_at.is_(None),
            OperationsBook.enabled.is_(True),
            or_(
                exists(explicit),
                exists(
                    ops.project_owners(Project.id).where(ProjectUser.user_id == user_id)
                ),
            ),
        )
        .order_by(Project.name, Project.id)
    )


@router.get("/organizations/{org_id}/access")
async def organization_access(
    org_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    _, admin, setting = await ops.organization(db_session, current_user, org_id)
    can_overview = False
    if setting and setting.enabled:
        for project in await db_session.scalars(
            granted_projects(org_id, current_user.id)
        ):
            if await has_research_capability(
                db_session,
                user=current_user,
                project=project,
                capability="research.read",
            ):
                can_overview = True
                break
    return {
        "admin": admin,
        "enabled": bool(setting and setting.enabled),
        "revision": setting.revision if setting else 0,
        "can_overview": can_overview,
    }


@router.put("/organizations/{org_id}")
async def configure_org(
    org_id: UUID, form: Switch, current_user: CurrentUser, db_session: DBSession
):
    _, _, row = await ops.organization(
        db_session, current_user, org_id, manage=True, write=True
    )
    if (row.revision if row else 0) != form.expected_revision:
        raise HTTPException(409, "Settings changed")
    if not row:
        row = OperationsOrganization(organization_id=org_id, revision=0)
    row.enabled = form.enabled
    row.revision += 1
    db_session.add(row)
    await db_session.commit()
    return {"enabled": row.enabled, "revision": row.revision}


@router.get("/organizations/{org_id}/projects")
async def setup_projects(
    org_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    _, _, setting = await ops.organization(
        db_session, current_user, org_id, manage=True
    )
    if not setting or not setting.enabled:
        raise HTTPException(403, "Organization operations disabled")
    rows = await db_session.execute(
        select(Project.id, Project.name)
        .where(Project.lab_id == org_id, Project.deleted_at.is_(None))
        .order_by(Project.name, Project.id)
    )
    return {"projects": rows.mappings().all()}


@router.get("/projects/{pid}/settings")
async def book_settings(pid: UUID, current_user: CurrentUser, db_session: DBSession):
    project, book, _, _, _ = await ops.project_access(
        db_session, current_user, pid, management=True
    )
    users = await db_session.execute(organization_accounts(project.lab_id))
    owners = set(await db_session.scalars(ops.project_owners(pid)))
    eligible = [
        {
            "id": str(u.id),
            "name": name,
            "username": u.username,
            "is_owner": u.id in owners,
        }
        for u, name in users
        if await has_research_capability(
            db_session, user=u, project=project, capability="research.read"
        )
    ]
    grants = await db_session.scalars(
        select(OperationsGrant).where(OperationsGrant.project_id == pid)
    )
    return {
        "enabled": bool(book and book.enabled),
        "revision": book.revision if book else 0,
        "people": eligible,
        "grants": {str(g.user_id): g.role for g in grants},
    }


@router.put("/projects/{pid}/settings")
async def configure_book(
    pid: UUID, form: BookSettings, current_user: CurrentUser, db_session: DBSession
):
    project, book, _, _, _ = await ops.project_access(
        db_session, current_user, pid, management=True, write=True
    )
    if (book.revision if book else 0) != form.expected_revision:
        raise HTTPException(409, "Settings changed")
    for uid in form.grants:
        account = await db_session.get(User, uid)
        if (
            not account
            or not await db_session.scalar(
                select(LabUser.id).where(
                    LabUser.lab_id == project.lab_id, LabUser.user_id == uid
                )
            )
            or not await has_research_capability(
                db_session, user=account, project=project, capability="research.read"
            )
        ):
            raise HTTPException(422, "Grants require current project access")
    if not book:
        book = OperationsBook(project_id=pid, revision=0)
    book.enabled = form.enabled
    book.revision += 1
    db_session.add(book)
    await db_session.flush()
    grants = {
        g.user_id: g
        for g in await db_session.scalars(
            select(OperationsGrant).where(OperationsGrant.project_id == pid)
        )
    }
    owners = set(await db_session.scalars(ops.project_owners(pid)))
    for uid, g in grants.items():
        if uid not in form.grants and uid in owners and g.role == "viewer":
            raise HTTPException(
                409,
                "Choose owner access explicitly before removing a read-only restriction",
            )
        if uid not in form.grants or form.grants[uid] == "inherit":
            await db_session.delete(g)
    for uid, role in form.grants.items():
        if role == "inherit" and uid not in owners:
            raise HTTPException(
                422, "Owner access setting requires current project ownership"
            )
        if role == "inherit":
            continue
        grant = grants.get(uid) or OperationsGrant(project_id=pid, user_id=uid)
        grant.role = role
        db_session.add(grant)
    await db_session.commit()
    return {"revision": book.revision}


@router.get("/projects/{pid}/access")
async def access(pid: UUID, current_user: CurrentUser, db_session: DBSession):
    _, _, role, _, _ = await ops.project_access(
        db_session, current_user, pid, discovery=True
    )
    return {"role": role}


@router.get("/organizations/{org_id}/overview")
async def overview(
    org_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    as_of: date | None = None,
):
    org, _, setting = await ops.organization(db_session, current_user, org_id)
    if not setting or not setting.enabled:
        raise HTTPException(403, "Organization operations disabled")
    query = granted_projects(org_id, current_user.id)
    rows = []
    for project in await db_session.scalars(query):
        if await has_research_capability(
            db_session, user=current_user, project=project, capability="research.read"
        ):
            entries = await ops.records(db_session, project.id)
            summary = summarize(entries, as_of or date.today())
            rows.append(
                {
                    "id": project.id,
                    "name": project.name,
                    "href": project_browser_path(org.uid, project.uid) + "/operations",
                    "owner": await ops.owner(db_session, project),
                    "summary": summary,
                    "contracts": [
                        {"id": r["id"], "title": r["data"]["title"]}
                        for r in entries
                        if r["kind"] == "contract" and r["status"] != "void"
                    ],
                }
            )
    return {"projects": rows}


@router.get("/projects/{pid}")
async def ledger(
    pid: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    as_of: date | None = None,
):
    project, _, role, _, _ = await ops.project_access(db_session, current_user, pid)
    rows = await ops.records(db_session, pid)
    latest = await db_session.execute(
        select(OperationsEvent.entry_id, OperationsEvent.actor_id, OperationsEvent.at)
        .distinct(OperationsEvent.entry_id)
        .where(OperationsEvent.project_id == pid)
        .order_by(
            OperationsEvent.entry_id,
            OperationsEvent.after["revision"].as_integer().desc(),
        )
    )
    updates = {str(entry_id): (str(actor), at) for entry_id, actor, at in latest}
    for row in rows:
        row["updated_by"], row["updated_at"] = updates[row["id"]]
    actors = {
        UUID(row[key])
        for row in rows
        for key in ("created_by", "verified_by", "updated_by")
        if row[key]
    }
    people = {
        str(uid): name
        for uid, name in await db_session.execute(
            select(User.id, organization_display_name())
            .outerjoin(
                LabUser,
                (LabUser.user_id == User.id) & (LabUser.lab_id == project.lab_id),
            )
            .where(User.id.in_(actors))
        )
    }
    return {
        "role": role,
        "owner": await ops.owner(db_session, project),
        "is_project_owner": bool(
            await db_session.scalar(
                ops.project_owners(pid)
                .where(ProjectUser.user_id == current_user.id)
                .limit(1)
            )
        ),
        "entries": rows,
        "people": people,
        "summary": summarize(rows, as_of or date.today()),
    }


@router.post("/projects/{pid}/entries")
async def post_change(
    pid: UUID, form: Change, current_user: CurrentUser, db_session: DBSession
):
    try:
        return await ops.save(db_session, current_user, pid, form)
    except IntegrityError as exc:
        await db_session.rollback()
        if getattr(exc.orig, "sqlstate", None) != "23505":
            raise
        raise HTTPException(409, "Record ID already used") from exc


@router.get("/projects/{pid}/entries/{eid}/history")
async def history(
    pid: UUID, eid: UUID, current_user: CurrentUser, db_session: DBSession
):
    project, *_ = await ops.project_access(db_session, current_user, pid)
    rows = await db_session.execute(
        select(OperationsEvent, organization_display_name())
        .join(User, User.id == OperationsEvent.actor_id)
        .outerjoin(
            LabUser, (LabUser.user_id == User.id) & (LabUser.lab_id == project.lab_id)
        )
        .where(OperationsEvent.project_id == pid, OperationsEvent.entry_id == eid)
        .order_by(OperationsEvent.after["revision"].as_integer())
    )
    return {
        "events": [
            {
                "actor": name,
                "actor_id": e.actor_id,
                "at": e.at,
                "reason": e.reason,
                "before": e.before,
                "after": e.after,
            }
            for e, name in rows
        ]
    }


@router.get("/projects/{pid}/sources")
async def sources(
    pid: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
    q: str = Query(default="", max_length=255),
):
    project, _, role, _, _ = await ops.project_access(db_session, current_user, pid)
    if role == "viewer":
        raise HTTPException(403, "Read only")
    result = {"work": [], "documents": [], "files": []}
    tasks = await db_session.execute(
        select(ResearchTask.id, ResearchTask.title)
        .join(ProjectWork, ProjectWork.task_id == ResearchTask.id)
        .where(
            ResearchTask.project_id == pid,
            ResearchTask.archived_at.is_(None),
            ResearchTask.title.icontains(q, autoescape=True),
        )
        .order_by(ResearchTask.title)
    )
    result["work"] = tasks.mappings().all()
    docs = await db_session.execute(
        select(ResearchLogEntry.id, ResearchLogRevision.revision)
        .join(ResearchDocument, ResearchDocument.id == ResearchLogEntry.id)
        .join(
            ResearchLogRevision, ResearchLogRevision.log_entry_id == ResearchLogEntry.id
        )
        .where(
            ResearchLogEntry.project_id == pid,
            ResearchLogEntry.archived_at.is_(None),
            ResearchLogEntry.title.icontains(q, autoescape=True),
        )
        .order_by(ResearchLogEntry.title, ResearchLogRevision.revision.desc())
    )
    for identity, version in docs:
        try:
            item = await evidence_view(
                db_session,
                current_user,
                project,
                {"kind": "document", "id": str(identity), "version": str(version)},
            )
        except HTTPException:
            continue
        result["documents"].append(
            {"id": identity, "version": version, "title": item["label"]}
        )
    files = await db_session.scalars(
        select(ResearchFile)
        .where(
            ResearchFile.project_id == pid,
            ResearchFile.visibility == "restricted",
            ResearchFile.archived_at.is_(None),
            ResearchFile.filename.icontains(q, autoescape=True),
        )
        .order_by(ResearchFile.filename)
    )
    for f in files:
        try:
            await authorize_research_file(db_session, current_user, f)
        except HTTPException:
            continue
        result["files"].append({"id": f.id, "title": f.filename})
    return result


@router.get("/projects/{pid}/entries/{eid}/evidence/{field}")
async def evidence(
    pid: UUID,
    eid: UUID,
    field: str,
    current_user: CurrentUser,
    db_session: DBSession,
    download: bool = False,
):
    project, _, _, _, _ = await ops.project_access(db_session, current_user, pid)
    entry = await db_session.get(OperationsEntry, eid)
    if (
        not entry
        or entry.project_id != pid
        or field not in {"signed_doc", "acceptance_doc", "work_id", "proof_file_id"}
        or not (ref := entry.data.get(field))
    ):
        raise HTTPException(404, "Evidence unavailable")
    if field == "work_id":
        return await evidence_view(
            db_session, current_user, project, {"kind": "research_task", "id": ref}
        )
    if field == "proof_file_id":
        from app.routers.knowledge import FileTokenParams, create_file_token

        return await create_file_token(
            UUID(ref),
            FileTokenParams(mode="download" if download else "preview"),
            db_session,
            current_user,
        )
    item = await evidence_view(
        db_session,
        current_user,
        project,
        {"kind": "document", "id": ref["id"], "version": str(ref["version"])},
    )
    revision = await db_session.scalar(
        select(ResearchLogRevision).where(
            ResearchLogRevision.log_entry_id == UUID(ref["id"]),
            ResearchLogRevision.revision == ref["version"],
        )
    )
    if download:
        return Response(
            revision.snapshot.get("body", ""),
            media_type="text/plain",
            headers={
                "Content-Disposition": f'attachment; filename="{ref["id"]}-v{ref["version"]}.aimd"'
            },
        )
    return {
        "title": item["label"],
        "version": ref["version"],
        "body": revision.snapshot.get("body", ""),
    }
