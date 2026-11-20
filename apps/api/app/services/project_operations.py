"""Project-scoped, serialized commercial postings and access control."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.knowledge import ResearchFile
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project, ProjectRole, ProjectUser
from app.models.project_operations import (
    OperationsBook,
    OperationsEntry,
    OperationsEvent,
    OperationsGrant,
    OperationsOrganization,
    OperationsProof,
)
from app.models.project_work import ProjectWork
from app.models.user import User
from app.routers.labs import require_configured_single_lab, require_lab_membership
from app.services.knowledge import authorize_research_file, canonical_digest
from app.services.operations_contracts import Change
from app.services.project_people import organization_display_name
from app.services.project_work import evidence_view
from app.services.research_runtime import has_research_capability


async def organization(db, user, org_id, *, manage=False, write=False):
    org = await db.scalar(
        select(Lab).where(Lab.id == org_id).with_for_update(read=not write)
    )
    if not org:
        raise HTTPException(404, "Organization unavailable")
    require_configured_single_lab(org)
    member = await require_lab_membership(db, org_id, user.id)
    admin = member.role in (LabRole.OWNER, LabRole.MANAGER)
    if manage and not admin:
        raise HTTPException(403, "Organization manager required")
    settings = await db.get(OperationsOrganization, org_id)
    return org, admin, settings


async def project_access(
    db, user, pid, *, write=False, management=False, discovery=False
):
    org_id = await db.scalar(
        select(Project.lab_id).where(Project.id == pid, Project.deleted_at.is_(None))
    )
    if not org_id:
        raise HTTPException(404, "Project unavailable")
    _, admin, settings = await organization(db, user, org_id, manage=management)
    q = select(Project).where(
        Project.id == pid, Project.lab_id == org_id, Project.deleted_at.is_(None)
    )
    project = await db.scalar(q.with_for_update() if write else q)
    if not project or not await has_research_capability(
        db, user=user, project=project, capability="research.read"
    ):
        raise HTTPException(404, "Project unavailable")
    book = await db.get(OperationsBook, pid, populate_existing=True)
    grant = await db.get(OperationsGrant, (pid, user.id), populate_existing=True)
    enabled = bool(settings and settings.enabled)
    role = grant.role if enabled and book and book.enabled and grant else None
    if not discovery and (not enabled or not (management or role)):
        raise HTTPException(403, "Project operations unavailable")
    return project, book, role, enabled, admin


def snapshot(entry):
    return {
        "id": str(entry.id),
        "kind": entry.kind,
        "data": entry.data,
        "status": entry.status,
        "revision": entry.revision,
        "created_by": str(entry.created_by),
        "verified_by": str(entry.verified_by) if entry.verified_by else None,
        "verified_at": entry.verified_at.isoformat() if entry.verified_at else None,
    }


async def records(db, pid):
    return [
        snapshot(r)
        for r in (
            await db.scalars(
                select(OperationsEntry)
                .where(OperationsEntry.project_id == pid)
                .order_by(OperationsEntry.kind, OperationsEntry.id)
            )
        ).all()
    ]


async def owner(db, project):
    owner_id = (
        await db.scalar(
            select(ProjectUser.user_id)
            .where(
                ProjectUser.project_id == project.id,
                ProjectUser.role == ProjectRole.OWNER,
            )
            .order_by(ProjectUser.created_at, ProjectUser.id)
            .limit(1)
        )
        or project.create_user_id
    )
    name = await db.scalar(
        select(organization_display_name())
        .select_from(User)
        .outerjoin(
            LabUser, (LabUser.user_id == User.id) & (LabUser.lab_id == project.lab_id)
        )
        .where(User.id == owner_id)
    )
    return {"id": str(owner_id), "name": name} if name is not None else None


def check_links(rows):
    live = {r["id"]: r for r in rows if r["status"] != "void"}

    def linked(identity, kind):
        if identity and (identity not in live or live[identity]["kind"] != kind):
            raise HTTPException(422, "Linked record must be active in this project")
        return live[identity]["data"] if identity else None

    allocated = {}
    scheduled = {}
    paid = {}
    received = {}
    for r in live.values():
        d = r["data"]
        linked(d.get("contract_id"), "contract")
        if r["kind"] == "installment":
            k = d["contract_id"]
            scheduled[k] = scheduled.get(k, 0) + d["amount"]
        if r["kind"] != "cash":
            continue
        term = linked(d["installment_id"], "installment")
        cost = linked(d["cost_id"], "cost")
        if term:
            if d["contract_id"] and d["contract_id"] != term["contract_id"]:
                raise HTTPException(422, "Installment belongs to another contract")
            k = d["installment_id"]
            allocated[k] = allocated.get(k, 0) + d["amount"]
        if cost:
            k = d["cost_id"]
            paid[k] = paid.get(k, 0) + d["amount"]
        k = term["contract_id"] if term else None
        if k:
            if live[k]["data"]["state"] != "signed":
                raise HTTPException(422, "Receipt requires a signed contract")
            received[k] = received.get(k, 0) + d["amount"]
    for amounts, key in (
        (allocated, "amount"),
        (scheduled, "gross"),
        (paid, "payable"),
        (received, "gross"),
    ):
        if any(value > live[k]["data"][key] for k, value in amounts.items()):
            raise HTTPException(422, "Allocation exceeds the linked amount")


async def validate_sources(db, user, project, data):
    for field in ("signed_doc", "acceptance_doc"):
        ref = data.get(field)
        if ref:
            await evidence_view(
                db,
                user,
                project,
                {"kind": "document", "id": ref["id"], "version": str(ref["version"])},
            )
    if work := data.get("work_id"):
        if not await db.get(ProjectWork, UUID(work)):
            raise HTTPException(422, "Choose an existing work item")
        await evidence_view(db, user, project, {"kind": "research_task", "id": work})
    if fid := data.get("proof_file_id"):
        file = await db.get(ResearchFile, UUID(fid))
        if (
            not file
            or file.archived_at
            or file.project_id != project.id
            or file.visibility != "restricted"
        ):
            raise HTTPException(404, "Restricted project file unavailable")
        await authorize_research_file(db, user, file)
        if not await db.get(OperationsProof, file.id):
            db.add(OperationsProof(file_id=file.id, project_id=project.id))


async def save(db, user, pid, change: Change, *, commit=True):
    project, _, role, _, _ = await project_access(db, user, pid, write=True)
    if role == "viewer":
        raise HTTPException(403, "Read-only operations access")
    digest = canonical_digest(change.model_dump(mode="json"))
    previous = await db.scalar(
        select(OperationsEvent).where(
            OperationsEvent.project_id == pid,
            OperationsEvent.request_id == change.request_id,
        )
    )
    if previous:
        if previous.actor_id != user.id or previous.digest != digest:
            raise HTTPException(409, "Request ID already used")
        return {"id": str(previous.entry_id), "revision": previous.after["revision"]}
    entry = await db.get(OperationsEntry, change.entry_id)
    if entry and entry.project_id != pid:
        raise HTTPException(409, "Record ID unavailable")
    if (entry.revision if entry else 0) != change.expected_revision:
        raise HTTPException(409, "Record changed; compare the current revision")
    if not entry and change.data is None:
        raise HTTPException(404, "Record unavailable")
    before = snapshot(entry) if entry else None
    kind = entry.kind if entry else change.data.kind
    data = change.data.model_dump(mode="json") if change.data else entry.data
    if data["kind"] != kind or (entry and entry.status == "void"):
        raise HTTPException(409, "Record cannot be changed")
    if role == "finance" and kind not in {"cost", "cash", "closing"}:
        raise HTTPException(403, "Project lead authorization required")
    if role != "finance" and (
        kind in {"cash", "closing"} or change.action in {"verify", "return"}
    ):
        raise HTTPException(403, "Finance authorization required")
    status = entry.status if entry else ("pending" if kind == "cost" else "active")
    if change.action in {"verify", "return"}:
        if kind != "cost" or status not in {"pending", "returned"}:
            raise HTTPException(409, "Only submitted costs can be reviewed")
        status = "verified" if change.action == "verify" else "returned"
    elif change.action == "void":
        if status == "verified" and role != "finance":
            raise HTTPException(403, "Finance authorization required")
        status = "void"
    elif kind == "cost" and status == "verified" and role != "finance":
        if {k: v for k, v in data.items() if k != "contract_id"} != {
            k: v for k, v in entry.data.items() if k != "contract_id"
        }:
            raise HTTPException(
                403, "A verified cost can only be reassigned by the project lead"
            )
    elif kind == "cost" and status == "returned":
        status = "pending"
    elif kind in {"cash", "closing"}:
        status = "verified"
    rows = await records(db, pid)
    if kind in {"forecast", "closing"} and any(
        r["kind"] == kind and r["status"] != "void" and r["id"] != str(change.entry_id)
        for r in rows
    ):
        raise HTTPException(
            409, "Update the current project estimate or reconciliation"
        )
    if change.action == "save":
        await validate_sources(db, user, project, data)
    if not entry:
        entry = OperationsEntry(
            id=change.entry_id,
            project_id=pid,
            created_by=user.id,
            kind=kind,
            revision=0,
        )
    entry.data = data
    entry.status = status
    entry.revision += 1
    if status == "verified" and role == "finance":
        entry.verified_by = user.id
        entry.verified_at = datetime.now(UTC)
    after = snapshot(entry)
    check_links([r for r in rows if r["id"] != after["id"]] + [after])
    db.add(entry)
    await db.flush()
    db.add(
        OperationsEvent(
            id=uuid4(),
            project_id=pid,
            entry_id=entry.id,
            request_id=change.request_id,
            digest=digest,
            actor_id=user.id,
            reason=change.reason,
            before=before,
            after=after,
        )
    )
    if commit:
        await db.commit()
    return {"id": after["id"], "revision": after["revision"]}
