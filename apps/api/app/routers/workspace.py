"""Actor-owned project recency with authorization on both capture and replay."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.config import config
from app.database import DBSession
from app.models.knowledge import OwnerScope
from app.models.lab import Lab
from app.models.pinned_item import PinnedItem, PinnedResourceType
from app.models.project import Project
from app.models.project_visit import ProjectVisit
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.models.research_log import ResearchLogScope
from app.routers.depends import CurrentUser
from app.routers.permission import check_user_permission
from app.routers.research_documents import _context as document_context
from app.routers.research_log import _scope_context

router = APIRouter(prefix="/workspace", tags=["workspace"])


class ProjectVisitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "project", "protocol", "recording", "record", "document", "editor"
    ] = "project"
    section: Literal["overview", "protocols", "documents", "materials", "knowledge", "work"] = (
        "overview"
    )
    project_id: UUID | None = None
    lab_uid: str | None = Field(default=None, max_length=128)
    project_uid: str | None = Field(default=None, max_length=128)
    protocol_uid: str | None = Field(default=None, max_length=128)
    protocol_version: str | None = Field(default=None, max_length=64)
    resource_id: UUID | None = None
    record_version: int | None = Field(default=None, ge=1)


def missing():
    return HTTPException(404, "Workspace destination is unavailable")


async def resolve_target(db, user, request):
    entry = None
    if request.kind == "document":
        if request.resource_id is None:
            raise missing()
        entry, _ = await document_context(db, user, request.resource_id)
        if entry.scope_type != "project":
            return None  # Personal/Lab writing stays in its own space.
        if request.project_id and request.project_id != entry.project_id:
            raise missing()
        project = await db.get(Project, entry.project_id)
    elif request.project_id:
        project = await db.get(Project, request.project_id)
    elif request.lab_uid and request.project_uid:
        project = await db.scalar(
            select(Project)
            .join(Lab, Lab.id == Project.lab_id)
            .where(
                Lab.uid == request.lab_uid,
                Project.uid == request.project_uid,
            )
        )
    else:
        raise missing()
    if project is None or project.deleted_at is not None:
        raise missing()
    lab = await db.get(Lab, project.lab_id)
    if (
        lab is None
        or (request.lab_uid and request.lab_uid != lab.uid)
        or (request.project_uid and request.project_uid != project.uid)
    ):
        raise missing()
    if config.is_single_lab and lab.uid != config.SINGLE_LAB_UID:
        raise missing()
    await check_user_permission(db, project, user, action="read_project")
    params = {"labUid": lab.uid, "projectUid": project.uid}
    target = {
        "kind": request.kind,
        "title": None,
        "route": {"name": "project-overview", "params": params},
    }
    if entry:
        target.update(
            title=entry.title,
            route={
                "name": "research-document-detail",
                "params": {"documentId": str(entry.id)},
            },
        )
    elif request.kind == "project":
        if request.section in {"documents", "materials"}:
            await _scope_context(
                db,
                user,
                scope_type=ResearchLogScope.PROJECT,
                lab_id=lab.id,
                project_id=project.id,
                capability="log.read",
            )
        if request.section == "work":
            from app.services.project_work import project_context

            await project_context(db, user, project.id)
        if request.section == "knowledge":
            # Use the same scope gate as the Knowledge listing.
            from app.services.knowledge import resolve_scope

            await resolve_scope(
                db,
                user,
                scope_type=OwnerScope.PROJECT,
                lab_id=lab.id,
                project_id=project.id,
                capability="knowledge.read",
            )
        target["route"]["name"] = f"project-{request.section}"
        target["section"] = request.section
    else:
        protocol = await db.scalar(
            select(Protocol).where(
                Protocol.project_id == project.id,
                Protocol.uid == request.protocol_uid,
                Protocol.deleted_at.is_(None),
            )
        )
        if protocol is None:
            raise missing()
        await check_user_permission(
            db, project, user, action="read_protocol", protocol=protocol
        )
        target.update(
            title=protocol.name,
            protocol_id=str(protocol.id),
            protocol_version=protocol.latest_version,
        )
        params = {**params, "protocolUid": protocol.uid}
        target["route"] = {"name": "protocol-detail", "params": params}
        if request.kind == "recording":
            await check_user_permission(
                db, project, user, action="create_record", protocol=protocol
            )
            # The browser may attach its own matching draft; never resume someone else's device draft.
        elif request.kind == "editor":
            await check_user_permission(
                db, project, user, action="update_protocol", protocol=protocol
            )
            version = request.protocol_version or protocol.latest_version
            if not await db.scalar(
                select(ProtocolVersion.id).where(
                    ProtocolVersion.protocol_id == protocol.id,
                    ProtocolVersion.version == version,
                )
            ):
                raise missing()
            target["route"] = {
                "name": "protocol-editor",
                "params": {**params, "protocolVersion": version},
            }
        elif request.kind == "record":
            record = await db.scalar(
                select(Record).where(
                    Record.id == request.resource_id,
                    Record.version == request.record_version,
                    Record.protocol_id == protocol.id,
                    Record.deleted_at.is_(None),
                )
            )
            if record is None:
                raise missing()
            await check_user_permission(
                db,
                project,
                user,
                action="read_record",
                protocol=protocol,
                record=record,
            )
            target["record_number"] = record.number
            target["route"] = {
                "name": "protocol-record-report",
                "params": {
                    **params,
                    "protocolVersion": record.protocol_version,
                    "recordId": str(record.id),
                    "recordVersion": str(record.version),
                },
            }
    return project, lab, target


@router.post("/project-visits")
async def capture_project_visit(
    params: ProjectVisitRequest, current_user: CurrentUser, db_session: DBSession
):
    resolved = await resolve_target(db_session, current_user, params)
    if resolved is None:
        return {"recorded": False}
    project, _, _ = resolved
    # Store identifiers only, not names, form data, query strings or authorization decisions.
    stored = params.model_copy(
        update={"project_id": project.id, "lab_uid": None, "project_uid": None}
    ).model_dump(mode="json", exclude_none=True)
    await db_session.execute(
        insert(ProjectVisit)
        .values(
            user_id=current_user.id,
            project_id=project.id,
            target=stored,
            visited_at=func.clock_timestamp(),
        )
        .on_conflict_do_update(
            index_elements=[ProjectVisit.user_id, ProjectVisit.project_id],
            set_={"target": stored, "visited_at": func.clock_timestamp()},
        )
    )
    keep = (
        select(ProjectVisit.project_id)
        .where(ProjectVisit.user_id == current_user.id)
        .order_by(ProjectVisit.visited_at.desc(), ProjectVisit.project_id)
        .limit(50)
    )
    await db_session.execute(
        delete(ProjectVisit).where(
            ProjectVisit.user_id == current_user.id,
            ProjectVisit.project_id.not_in(keep),
        )
    )
    await db_session.commit()
    return {"recorded": True}


@router.get("/recent-projects")
async def recent_projects(current_user: CurrentUser, db_session: DBSession):
    visits = (
        await db_session.scalars(
            select(ProjectVisit)
            .where(ProjectVisit.user_id == current_user.id)
            .order_by(ProjectVisit.visited_at.desc(), ProjectVisit.project_id)
        )
    ).all()
    pins = (
        await db_session.scalars(
            select(PinnedItem)
            .where(
                PinnedItem.user_id == current_user.id,
                PinnedItem.resource_type == PinnedResourceType.PROJECT,
            )
            .order_by(PinnedItem.sort_order, PinnedItem.id)
        )
    ).all()
    visit_map = {row.project_id: row for row in visits}
    pin_map = {row.resource_id: row for row in pins}
    ids = list(
        dict.fromkeys(
            [row.resource_id for row in pins] + [row.project_id for row in visits]
        )
    )
    items = []
    for project_id in ids:
        try:
            project, lab, _ = await resolve_target(
                db_session, current_user, ProjectVisitRequest(project_id=project_id)
            )
        except HTTPException as exc:
            if exc.status_code not in {400, 403, 404}:
                raise
            continue
        visit = visit_map.get(project_id)
        target = None
        if visit:
            try:
                resolved = await resolve_target(
                    db_session,
                    current_user,
                    ProjectVisitRequest.model_validate(visit.target),
                )
                target = resolved[2] if resolved else None
            except HTTPException as exc:
                if exc.status_code not in {400, 403, 404}:
                    raise
                # Keep the authorized project, but never return revoked asset names or links.
        pin = pin_map.get(project_id)
        items.append(
            {
                "id": str(project.id),
                "uid": project.uid,
                "name": project.name,
                "lab_uid": lab.uid,
                "lab_name": lab.name,
                "visited_at": visit.visited_at if visit else None,
                "pinned_id": pin.id if pin else None,
                "target": target,
            }
        )
    return {"items": items}


class DraftDestinationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_ids: list[UUID] = Field(max_length=50)


@router.post("/draft-destinations")
async def draft_destinations(
    params: DraftDestinationsRequest, current_user: CurrentUser, db_session: DBSession
):
    items = []
    for protocol_id in dict.fromkeys(params.protocol_ids):
        protocol = await db_session.get(Protocol, protocol_id)
        if protocol is None or protocol.deleted_at is not None:
            continue
        try:
            project, lab, target = await resolve_target(
                db_session,
                current_user,
                ProjectVisitRequest(
                    project_id=protocol.project_id,
                    kind="recording",
                    protocol_uid=protocol.uid,
                ),
            )
        except HTTPException as exc:
            if exc.status_code not in {400, 403, 404}:
                raise
            continue
        items.append(
            {
                "id": str(project.id),
                "uid": project.uid,
                "name": project.name,
                "lab_uid": lab.uid,
                "lab_name": lab.name,
                "visited_at": None,
                "pinned_id": None,
                "target": target,
            }
        )
    return {"items": items}
