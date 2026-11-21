"""Delegated organization project registration and single-project cash books."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID, uuid5

from fastapi import HTTPException
from pydantic import Field, StringConstraints
from sqlalchemy import func, or_, select

from app.config import config
from app.models.external_access import ExternalProjectReceipt
from app.models.lab import Lab
from app.models.project import Project, ProjectType
from app.models.project_operations import OperationsEntry
from app.routers.utils import UidStr
from app.services import project_operations as ops
from app.services.browser_paths import project_browser_path
from app.services.external_access import (
    StrictModel,
    check_user_permission,
    digest,
    fail,
    scope,
)
from app.services.operations_contracts import Cash, Change
from app.services.operations_totals import summarize

Lookup = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)
]


class FindProject(StrictModel):
    query: Lookup
    by: Literal["name", "uid", "contract_number"]


class PrivateProject(StrictModel):
    request_id: UUID
    uid: UidStr
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=3, max_length=64)
    ]
    description: Annotated[
        str, StringConstraints(strip_whitespace=True, max_length=128)
    ] = ""
    contract_number: Lookup | None = None


class CashPage(StrictModel):
    offset: int = Field(default=0, ge=0, le=100000)


class RecordCash(StrictModel):
    request_id: UUID
    cash: Cash


TOOLS = {
    "find_organization_project": (
        "Find a readable project by exact name, UID or contract number in the authorized organization.",
        FindProject,
        True,
    ),
    "create_private_project": (
        "Register one private project. Reuse the same request_id on retry. No finance role or contract posting is created.",
        PrivateProject,
        False,
    ),
    "list_project_cash": (
        "Read actual cash receipts and payments in the authorized project and totals in CNY fen.",
        CashPage,
        True,
    ),
    "record_project_cash": (
        "Record an actual inflow or outflow in integer CNY fen on its actual date. For inflows specify receipt_purpose: customer_receipt or other_income. Reuse request_id on retry.",
        RecordCash,
        False,
    ),
}
REQUIRED = {
    "find_organization_project": "projects:find",
    "create_private_project": "projects:create",
    "list_project_cash": "cash:read",
    "record_project_cash": "cash:create",
}
ORG_SCOPES = {"projects:find", "projects:create"}
CASH_SCOPES = {"cash:read", "cash:create"}


async def cash_role(db, user, project):
    try:
        return (await ops.project_access(db, user, project.id, discovery=True))[2]
    except HTTPException as error:
        if error.status_code in (403, 404):
            return None
        raise


def project_info(org, project):
    base = config.SITE_URL.rstrip("/") + project_browser_path(org.uid, project.uid)
    return {
        "id": str(project.id),
        "name": project.name,
        "uid": project.uid,
        "url": base + "/overview",
    }


def contract_projects(org_id, number):
    # Intake references are visible to their registrar. Ledger references require
    # current book access in addition to project visibility (checked by the caller).
    return select(ExternalProjectReceipt.project_id).where(
        ExternalProjectReceipt.organization_id == org_id,
        ExternalProjectReceipt.contract_number == number,
    )


async def find_projects(db, user, org, args):
    q = select(Project).where(Project.lab_id == org.id, Project.deleted_at.is_(None))
    if args.by == "contract_number":
        number = args.query.upper()
        registered = contract_projects(org.id, number)
        own = registered.where(ExternalProjectReceipt.actor_id == user.id)
        ledger = select(OperationsEntry.project_id).where(
            OperationsEntry.kind == "contract",
            OperationsEntry.status != "void",
            func.upper(func.trim(OperationsEntry.data["number"].as_string())) == number,
        )
        q = q.add_columns(Project.id.in_(own)).where(
            or_(Project.id.in_(registered), Project.id.in_(ledger))
        )
    else:
        field = Project.uid if args.by == "uid" else Project.name
        q = q.add_columns(Project.id.is_not(None)).where(
            func.lower(field) == args.query.lower()
        )
    items = []
    for project, direct in await db.execute(q.order_by(Project.uid)):
        try:
            await check_user_permission(db, project, user, "read_project")
        except HTTPException as error:
            if error.status_code == 403:
                continue
            raise
        if direct or await cash_role(db, user, project):
            items.append(project_info(org, project))
    return {"items": items}


async def register(db, user, org, args):
    from app.routers.projects import ProjectCreateParams, create_project_transaction

    key = (org.id, args.request_id)
    number = args.contract_number.upper() if args.contract_number else None
    signature = digest({**args.model_dump(mode="json"), "contract_number": number})
    receipt = await db.get(ExternalProjectReceipt, key)
    if receipt:
        if receipt.actor_id != user.id or receipt.digest != signature:
            fail("request_id_conflict", 409)
        project = await db.get(Project, receipt.project_id)
        if not project or project.deleted_at:
            fail("project_unavailable", 404)
        await check_user_permission(db, project, user, "read_project")
        return project_info(org, project)
    duplicate = select(Project.id).where(
        Project.lab_id == org.id,
        Project.deleted_at.is_(None),
        or_(Project.uid == args.uid, func.lower(Project.name) == args.name.lower()),
    )
    if await db.scalar(duplicate):
        fail("project_registration_conflict", 409)
    if number:
        reserved = select(ExternalProjectReceipt.project_id).where(
            ExternalProjectReceipt.organization_id == org.id,
            ExternalProjectReceipt.contract_number == number,
        )
        existing = (
            select(OperationsEntry.id)
            .join(Project, Project.id == OperationsEntry.project_id)
            .where(
                Project.lab_id == org.id,
                Project.deleted_at.is_(None),
                OperationsEntry.kind == "contract",
                OperationsEntry.status != "void",
                func.upper(func.trim(OperationsEntry.data["number"].as_string()))
                == number,
            )
        )
        if await db.scalar(reserved) or await db.scalar(existing):
            fail("project_registration_conflict", 409)
    params = ProjectCreateParams(
        lab_id=org.id,
        uid=args.uid,
        name=args.name,
        description=args.description,
        type=ProjectType.PRIVATE,
    )
    project, _ = await create_project_transaction(params, user, db)
    db.add(
        ExternalProjectReceipt(
            organization_id=org.id,
            request_id=args.request_id,
            actor_id=user.id,
            project_id=project.id,
            contract_number=number,
            digest=signature,
        )
    )
    return project_info(org, project)


async def call(db, access, name, args):
    required = REQUIRED[name]
    scope(access, required)
    if required in ORG_SCOPES:
        if not access.grant.organization_id:
            fail("insufficient_scope")
        org, _, _ = await ops.organization(
            db,
            access.user,
            access.grant.organization_id,
            manage=True,
            write=name == "create_private_project",
        )
        if name == "find_organization_project":
            return await find_projects(db, access.user, org, args)
        return await register(db, access.user, org, args)
    if not access.project:
        fail("insufficient_scope")
    project, _, role, _, _ = await ops.project_access(
        db, access.user, access.project.id
    )
    org = await db.get(Lab, project.lab_id)
    url = (
        config.SITE_URL.rstrip("/")
        + project_browser_path(org.uid, project.uid)
        + "/operations"
    )
    if name == "record_project_cash":
        if role != "finance":
            fail("cash_finance_role_required")
        result = await ops.save(
            db,
            access.user,
            project.id,
            Change(
                request_id=args.request_id,
                entry_id=uuid5(project.id, str(args.request_id)),
                expected_revision=0,
                data=args.cash,
            ),
            commit=False,
        )
        return {**result, "url": url + "?entry=" + result["id"]}
    entries = await db.scalars(
        select(OperationsEntry)
        .where(OperationsEntry.project_id == project.id, OperationsEntry.kind == "cash")
        .order_by(OperationsEntry.data["day"].as_string().desc(), OperationsEntry.id)
    )
    rows = [ops.snapshot(entry) for entry in entries]
    totals = summarize(rows, date.today())
    page = rows[args.offset : args.offset + 50]
    return {
        "unit": "CNY_fen",
        "totals": {k: totals[k] for k in ("received", "paid", "net_cash")},
        "items": [{**row, "url": url + "?entry=" + row["id"]} for row in page],
        "next_offset": args.offset + len(page)
        if args.offset + len(page) < len(rows)
        else None,
        "url": url,
    }
