"""Single-organization project invitations and the external collaborator workspace."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import AwareDatetime, BaseModel, EmailStr, Field, StringConstraints
from sqlalchemy import delete, func, or_, select, update

from app.config import config
from app.database import DBSession
from app.libs.smtp import send_smtp_message
from app.models.account_token import AccountToken, AccountTokenType
from app.models.external_access import ExternalGrant
from app.models.group import GroupProject, GroupUser
from app.models.lab import LabRole, LabUser
from app.models.oauth import OAuthAccessToken, OAuthAuthorizationCode
from app.models.project import PermissionType, Project, ProjectRole, ProjectUser
from app.models.project_guest import OrganizationGuestProfile, ProjectGuest
from app.models.project_operations import OperationsGrant
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.user import User
from app.routers.depends import CurrentUser, guest_endpoint
from app.routers.instance import require_single_lab_manager
from app.routers.labs import lab_member_page, remove_membership_access
from app.services.account_security import bump_auth_version
from app.services.project_guests import (
    accessible_protocol,
    active_projects,
    ensure_guest_profile,
    exclusive_guest_profile,
    project_manager,
)
from app.services.single_lab import (
    account_for_email,
    add_user_to_single_lab,
    create_account_token,
    invitation_url,
    normalize_email,
    revoke_lab_account_tokens,
    utcnow,
)

router = APIRouter(prefix="/project-guests", tags=["project collaboration"])


DisplayName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
]


class Recipient(BaseModel):
    email: EmailStr


class Invite(Recipient):
    display_name: DisplayName | None = None
    role: Literal["reader", "recorder"] = "reader"
    access_until: AwareDatetime | None = None
    locale: Literal["zh-CN", "en-US"] = "zh-CN"


def role_name(role):
    return "recorder" if role == ProjectRole.RECORDER else "reader"


async def guest_name(db, project, user):
    if not user or not user.project_guest:
        return None
    profile = await db.get(OrganizationGuestProfile, (project.lab_id, user.id))
    return profile.display_name if profile else None


@router.post("/projects/{project_id}/invitation-name")
async def invitation_name(
    project_id: UUID, params: Recipient, current_user: CurrentUser, db: DBSession
):
    project = await project_manager(db, project_id, current_user.id)
    user = await account_for_email(db, str(params.email))
    # Project managers only need to know whether another name is required.
    return {"reuse": bool(await guest_name(db, project, user))}


@router.post("/projects/{project_id}/invitations")
async def invite(
    project_id: UUID, params: Invite, current_user: CurrentUser, db: DBSession
):
    project = await project_manager(db, project_id, current_user.id, lock=True)
    email = normalize_email(str(params.email))
    user = await account_for_email(db, email)
    if user and await LabUser.exists(db, [LabUser.user_id == user.id]):
        raise HTTPException(409, "Use the organization member picker for this account")
    name = await guest_name(db, project, user) or params.display_name
    if not name:
        raise HTTPException(422, "Organization display name is required")
    until = (
        params.access_until.astimezone(UTC).replace(tzinfo=None)
        if params.access_until
        else None
    )
    if until and until <= utcnow():
        raise HTTPException(422, "Access expiry must be in the future")
    token, raw = await create_account_token(
        db,
        token_type=AccountTokenType.PROJECT_INVITATION,
        email=email,
        invitation_display_name=name,
        project_role=ProjectRole.RECORDER
        if params.role == "recorder"
        else ProjectRole.VIEWER,
        lab_id=project.lab_id,
        project_id=project.id,
        access_until=until,
        created_by_user_id=current_user.id,
        user_id=user.id if user else None,
        expires_in=min(timedelta(days=7), until - utcnow())
        if until
        else timedelta(days=7),
    )
    url = invitation_url(raw)
    await db.commit()
    delivery = "link"
    if not config.research_email_missing_fields and (
        config.SMTP_SECURITY != "none" or config.APP_ENV != "production"
    ):
        subject = (
            "Airalogy 项目协作邀请"
            if params.locale == "zh-CN"
            else "Airalogy project invitation"
        )
        try:
            await asyncio.to_thread(
                send_smtp_message,
                delivery_id=token.id,
                recipient=email,
                subject=subject,
                body=f"{subject} · {project.name}\n\n{url}",
            )
            delivery = "sent"
        except OSError:
            delivery = "failed"
    return {"id": token.id, "url": url, "delivery": delivery}


@router.get("/projects/{project_id}/team")
async def team(project_id: UUID, current_user: CurrentUser, db: DBSession):
    project = await project_manager(db, project_id, current_user.id)
    people = (
        await db.execute(
            select(User, ProjectGuest, OrganizationGuestProfile.display_name)
            .join(ProjectGuest, ProjectGuest.user_id == User.id)
            .outerjoin(
                OrganizationGuestProfile,
                (OrganizationGuestProfile.user_id == User.id)
                & (OrganizationGuestProfile.lab_id == project.lab_id),
            )
            .where(ProjectGuest.project_id == project_id)
            .order_by(User.name)
        )
    ).all()
    pending = await db.scalars(
        select(AccountToken)
        .where(
            AccountToken.project_id == project_id,
            AccountToken.token_type == AccountTokenType.PROJECT_INVITATION,
            AccountToken.consumed_at.is_(None),
            AccountToken.expires_at > utcnow(),
        )
        .order_by(AccountToken.created_at.desc())
    )
    return {
        "people": [
            {
                "id": u.id,
                "name": name or u.name or u.username,
                "email": u.email,
                "role": role_name(g.role),
                "expired": bool(g.access_until and g.access_until <= utcnow()),
            }
            for u, g, name in people
        ],
        "pending": [
            {
                "id": i.id,
                "email": i.email,
                "name": i.invitation_display_name,
                "role": role_name(i.project_role),
            }
            for i in pending
        ],
    }


@router.delete("/projects/{project_id}/invitations/{invite_id}")
async def cancel(
    project_id: UUID, invite_id: UUID, current_user: CurrentUser, db: DBSession
):
    await project_manager(db, project_id, current_user.id, lock=True)
    await db.execute(
        update(AccountToken)
        .where(
            AccountToken.project_id == project_id,
            AccountToken.id == invite_id,
            AccountToken.consumed_at.is_(None),
        )
        .values(consumed_at=utcnow(), invitation_outcome="revoked")
    )
    await db.commit()
    return {"success": True}


@router.delete("/projects/{project_id}/people/{user_id}")
async def revoke(
    project_id: UUID, user_id: UUID, current_user: CurrentUser, db: DBSession
):
    await project_manager(db, project_id, current_user.id, lock=True)
    user = await db.get(User, user_id)
    if user:
        await db.execute(
            update(AccountToken)
            .where(
                AccountToken.project_id == project_id,
                AccountToken.email == normalize_email(user.email),
                AccountToken.consumed_at.is_(None),
            )
            .values(consumed_at=utcnow(), invitation_outcome="revoked")
        )
    await db.execute(
        delete(ProjectGuest).where(
            ProjectGuest.project_id == project_id, ProjectGuest.user_id == user_id
        )
    )
    await db.commit()
    return {"success": True}


def guest_rows(lab_id):
    return (
        select(User, OrganizationGuestProfile.display_name)
        .join(OrganizationGuestProfile, OrganizationGuestProfile.user_id == User.id)
        .where(OrganizationGuestProfile.lab_id == lab_id, User.project_guest.is_(True))
        # Keep a collaborator on the same directory page when their name is edited.
        .order_by(User.username, User.id)
    )


async def guest_people(db, lab_id, query):
    people = {}
    for user, name in await db.execute(query):
        await user.load_avatar_attachment()
        people[user.id] = {
            "id": user.id,
            "name": name or user.name or user.username,
            "display_name": name,
            "username": user.username,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "projects": [],
        }
    if people:
        projects = await db.execute(
            select(ProjectGuest.user_id, Project.name)
            .join(Project, Project.id == ProjectGuest.project_id)
            .where(
                Project.lab_id == lab_id,
                Project.deleted_at.is_(None),
                ProjectGuest.user_id.in_(people.keys()),
                or_(
                    ProjectGuest.access_until.is_(None),
                    ProjectGuest.access_until > utcnow(),
                ),
            )
            .order_by(Project.name, Project.id)
        )
        for user_id, project_name in projects:
            people[user_id]["projects"].append(project_name)
    return list(people.values())


@router.get("/directory")
async def directory(current_user: CurrentUser, db: DBSession):
    lab, _ = await require_single_lab_manager(db, current_user)
    return await guest_people(db, lab.id, guest_rows(lab.id))


@router.get("/people")
async def people(
    current_user: CurrentUser,
    db: DBSession,
    kind: Literal["all", "staff", "guest"] = "all",
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
):
    lab, _ = await require_single_lab_manager(db, current_user)
    offset = (page - 1) * page_size
    total = 0
    rows = []
    if kind != "guest":
        total = await LabUser.count(db, [LabUser.lab_id == lab.id])
        if offset < total:
            staff = await lab_member_page(
                db, lab.id, current_user.id, offset, page_size
            )
            rows.extend(dict(person, kind="staff") for person in staff)
    if kind != "staff":
        guests = guest_rows(lab.id)
        guest_offset = max(0, offset - total)
        total += await db.scalar(
            select(func.count()).select_from(guests.order_by(None).subquery())
        )
        if len(rows) < page_size and offset < total:
            batch = await guest_people(
                db, lab.id, guests.offset(guest_offset).limit(page_size - len(rows))
            )
            rows.extend(dict(person, kind="guest") for person in batch)
    return {"list": rows, "total": total}


class RenameGuest(BaseModel):
    display_name: DisplayName


@router.patch("/directory/{user_id}")
async def rename_guest(
    user_id: UUID, params: RenameGuest, current_user: CurrentUser, db: DBSession
):
    lab, _ = await require_single_lab_manager(db, current_user)
    result = await db.execute(
        update(OrganizationGuestProfile)
        .where(
            OrganizationGuestProfile.lab_id == lab.id,
            OrganizationGuestProfile.user_id == user_id,
            OrganizationGuestProfile.user_id.in_(
                select(User.id).where(User.project_guest.is_(True))
            ),
        )
        .values(display_name=params.display_name)
        .returning(OrganizationGuestProfile.user_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(404, "Collaborator not found")
    await db.commit()
    return {"display_name": params.display_name}


async def conversion_context(db, actor, user_id, *, lock=False):
    lab, role = await require_single_lab_manager(db, actor)
    query = select(LabUser).where(LabUser.user_id == user_id, LabUser.lab_id == lab.id)
    member = await db.scalar(query.with_for_update() if lock else query)
    if not member:
        raise HTTPException(404, "Member not found")
    if (
        user_id == actor.id
        or user_id == lab.create_user_id
        or member.role == LabRole.OWNER
        or (role == LabRole.MANAGER and member.role != LabRole.MEMBER)
    ):
        raise HTTPException(
            403, "The organization owner or a peer administrator cannot be converted"
        )
    if await LabUser.exists(db, [LabUser.user_id == user_id, LabUser.lab_id != lab.id]):
        raise HTTPException(409, "This account belongs to another organization")
    direct = select(ProjectUser.project_id).where(ProjectUser.user_id == user_id)
    via_group = (
        select(GroupProject.project_id)
        .join(GroupUser, GroupUser.group_id == GroupProject.group_id)
        .where(GroupUser.user_id == user_id)
    )
    projects = (
        await db.scalars(
            select(Project)
            .where(
                Project.lab_id == lab.id,
                Project.deleted_at.is_(None),
                Project.id.in_(direct.union(via_group)),
            )
            .order_by(Project.name)
        )
    ).all()
    owners = (
        await db.scalars(
            select(Project.name)
            .join(ProjectUser, ProjectUser.project_id == Project.id)
            .where(
                Project.deleted_at.is_(None),
                ProjectUser.user_id == user_id,
                ProjectUser.role == ProjectRole.OWNER,
            )
        )
    ).all()
    return lab, member, projects, owners


@router.get("/conversion/{user_id}")
async def preview_conversion(user_id: UUID, current_user: CurrentUser, db: DBSession):
    _, _, projects, owners = await conversion_context(db, current_user, user_id)
    return {
        "projects": [{"id": p.id, "name": p.name} for p in projects],
        "transfer_first": owners,
    }


class Convert(BaseModel):
    projects: list[UUID] = Field(max_length=500)
    keep_none: bool = False
    confirm: Literal[True]


@router.post("/conversion/{user_id}")
async def convert(
    user_id: UUID, params: Convert, current_user: CurrentUser, db: DBSession
):
    lab, member, projects, owners = await conversion_context(
        db, current_user, user_id, lock=True
    )
    if owners:
        raise HTTPException(409, "Transfer project ownership first")
    keep = set(params.projects)
    if params.keep_none == bool(keep) or not keep.issubset(p.id for p in projects):
        raise HTTPException(
            422, "Select current projects or explicitly remove all project access"
        )
    user = await db.scalar(
        select(User).where(User.id == user_id).with_for_update(of=User)
    )
    await ensure_guest_profile(db, lab.id, user.id, member.alias or None)
    await remove_membership_access(db, lab, member, current_user)
    await db.execute(
        delete(OperationsGrant).where(
            OperationsGrant.user_id == user.id,
            OperationsGrant.project_id.in_(
                select(Project.id).where(Project.lab_id == lab.id)
            ),
        )
    )
    now = utcnow()
    await db.execute(
        update(ExternalGrant)
        .where(ExternalGrant.user_id == user.id, ExternalGrant.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    await db.execute(
        update(OAuthAccessToken)
        .where(OAuthAccessToken.user_id == user.id)
        .values(revoked_at=now)
    )
    await db.execute(
        update(OAuthAuthorizationCode)
        .where(OAuthAuthorizationCode.user_id == user.id)
        .values(used_at=now)
    )
    user.api_key_iv = os.urandom(16).hex()
    user.project_guest = True
    await bump_auth_version(db, user.id)
    db.add_all(
        [
            ProjectGuest(user_id=user.id, project_id=pid, role=ProjectRole.VIEWER)
            for pid in keep
        ]
    )
    await db.commit()
    return {"success": True}


async def promotion_context(db, actor, user_id, *, lock=False):
    lab, _ = await require_single_lab_manager(db, actor)
    user = await db.get(User, user_id, with_for_update=lock)
    profile = await exclusive_guest_profile(db, lab.id, user)
    if not profile:
        raise HTTPException(404, "Collaborator unavailable")
    query = (
        active_projects(user.id).where(Project.lab_id == lab.id).order_by(Project.id)
    )
    if lock:
        query = query.with_for_update(of=(ProjectGuest, Project))
    return lab, user, profile, (await db.execute(query)).all()


@router.get("/promotion/{user_id}")
async def preview_promotion(user_id: UUID, current_user: CurrentUser, db: DBSession):
    _, _, _, rows = await promotion_context(db, current_user, user_id)
    return {
        "projects": [
            {
                "id": project.id,
                "name": project.name,
                "role": role_name(guest.role),
                "access_until": guest.access_until.replace(tzinfo=UTC)
                if guest.access_until
                else None,
            }
            for project, guest in rows
        ]
    }


@router.post("/promotion/{user_id}")
async def promote(
    user_id: UUID, params: Convert, current_user: CurrentUser, db: DBSession
):
    lab, user, profile, rows = await promotion_context(
        db, current_user, user_id, lock=True
    )
    keep = set(params.projects)
    eligible = {project.id: guest for project, guest in rows}
    if params.keep_none == bool(keep) or not keep.issubset(eligible):
        raise HTTPException(422, "Confirm which active collaborations to retain")
    user.project_guest = False
    user.api_key_iv = os.urandom(16).hex()
    await db.flush()
    await add_user_to_single_lab(
        db,
        lab=lab,
        user=user,
        created_by_user_id=current_user.id,
        display_name=profile.display_name or user.name or user.username,
        project_role=None,
    )
    for project_id in keep:
        role = (
            ProjectRole.RECORDER
            if eligible[project_id].role == ProjectRole.RECORDER
            else ProjectRole.VIEWER
        )
        db.add(
            ProjectUser(
                project_id=project_id,
                user_id=user.id,
                role=role,
                create_user_id=current_user.id,
            )
        )
    await db.execute(delete(ProjectGuest).where(ProjectGuest.user_id == user.id))
    await db.delete(profile)
    await db.execute(
        update(AccountToken)
        .where(
            AccountToken.lab_id == lab.id,
            AccountToken.token_type == AccountTokenType.PROJECT_INVITATION,
            AccountToken.email == normalize_email(user.email),
            AccountToken.consumed_at.is_(None),
        )
        .values(consumed_at=utcnow(), invitation_outcome="revoked")
    )
    await revoke_lab_account_tokens(
        db, lab_id=lab.id, user_id=user.id, include_targeted_tokens=True
    )
    await bump_auth_version(db, user.id)
    await db.commit()
    return {"success": True}


@router.get("/mine")
@guest_endpoint
async def my_projects(current_user: CurrentUser, db: DBSession):
    rows = await db.execute(active_projects(current_user.id).order_by(Project.name))
    return [
        {
            "id": p.id,
            "uid": p.uid,
            "name": p.name,
            "description": p.description,
            "role": role_name(g.role),
        }
        for p, g in rows
    ]


@router.get("/mine/{project_id}")
@guest_endpoint
async def my_project(project_id: UUID, current_user: CurrentUser, db: DBSession):
    row = (
        await db.execute(
            active_projects(current_user.id).where(Project.id == project_id)
        )
    ).first()
    if not row:
        raise HTTPException(404, "Project not found")
    protocols = []
    if row.Project.permission_type == PermissionType.INHERIT:
        protocols = (
            (
                await db.execute(
                    select(Protocol.id, Protocol.uid, Protocol.name)
                    .where(
                        Protocol.project_id == project_id,
                        Protocol.deleted_at.is_(None),
                        Protocol.inherit_permissions.is_(True),
                    )
                    .order_by(Protocol.name)
                )
            )
            .mappings()
            .all()
        )
    return {"protocols": protocols}


@router.get("/protocols/{protocol_id}")
@guest_endpoint
async def my_protocol(protocol_id: UUID, current_user: CurrentUser, db: DBSession):
    _, grant, protocol = await accessible_protocol(db, current_user.id, protocol_id)
    version = await db.scalar(
        select(ProtocolVersion).where(
            ProtocolVersion.protocol_id == protocol_id,
            ProtocolVersion.version == protocol.latest_version,
        )
    )
    if not version:
        raise HTTPException(404, "Protocol version not found")
    return {
        "name": protocol.name,
        "version": version.version,
        "aimd": version.aimd,
        "role": role_name(grant.role),
    }
