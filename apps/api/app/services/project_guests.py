from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.config import config
from app.models.account_token import AccountTokenType
from app.models.lab import LabRole, LabUser
from app.models.project import PermissionType, Project, ProjectRole
from app.models.project_guest import OrganizationGuestProfile, ProjectGuest
from app.models.protocol import Protocol
from app.models.user import User
from app.services.access_control import resolve_structured_access
from app.services.single_lab import get_single_lab, user_single_lab_role, utcnow

INVITATIONS = (AccountTokenType.INVITATION, AccountTokenType.PROJECT_INVITATION)


async def project_manager(db, project_id, actor_id, *, lock=False):
    lab = await get_single_lab(db)
    query = select(Project).where(
        Project.id == project_id, Project.deleted_at.is_(None)
    )
    if lock:
        query = query.with_for_update()
    project = await db.scalar(query)
    if lab is None or project is None or project.lab_id != lab.id:
        raise HTTPException(404, "Project not found")
    role = await user_single_lab_role(db, actor_id, lab.id)
    if role in (LabRole.OWNER, LabRole.MANAGER):
        return project
    if role is not None:
        from app.routers.permission import get_user_project_role

        direct_or_group = await get_user_project_role(db, actor_id, project_id)
        if direct_or_group in (ProjectRole.OWNER, ProjectRole.MANAGER):
            return project
        if config.effective_lab_structure_mode == "structured":
            access = await resolve_structured_access(
                db, actor_id, project.lab_id, project, include_legacy=False
            )
            if "project_manager" in access.role_keys:
                return project
    raise HTTPException(403, "Project manager required")


async def exclusive_guest_profile(db, lab_id, user):
    if not user or not user.project_guest:
        return None
    profile = await db.get(OrganizationGuestProfile, (lab_id, user.id))
    if profile is None:
        return None
    foreign_profile = select(OrganizationGuestProfile.user_id).where(
        OrganizationGuestProfile.user_id == user.id, OrganizationGuestProfile.lab_id != lab_id
    ).exists()
    foreign_project = select(ProjectGuest.user_id).join(Project).where(
        ProjectGuest.user_id == user.id, Project.lab_id != lab_id
    ).exists()
    staff = select(LabUser.user_id).where(LabUser.user_id == user.id).exists()
    if await db.scalar(select(foreign_profile | foreign_project | staff)):
        return None
    return profile


async def ensure_guest_profile(db, lab_id, user_id, name):
    # A later project invitation must respect the name already managed by the organization.
    statement = insert(OrganizationGuestProfile).values(
        lab_id=lab_id, user_id=user_id, display_name=name
    )
    await db.execute(
        statement.on_conflict_do_update(
            index_elements=[
                OrganizationGuestProfile.lab_id,
                OrganizationGuestProfile.user_id,
            ],
            set_={"display_name": statement.excluded.display_name},
            where=OrganizationGuestProfile.display_name.is_(None),
        )
    )


async def accept_project_invitation(db, invitation, user):
    if not invitation.project_id or not invitation.created_by_user_id:
        raise HTTPException(404, "Invitation is no longer available")
    project = await project_manager(
        db, invitation.project_id, invitation.created_by_user_id
    )
    await db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    if await LabUser.exists(db, [LabUser.user_id == user.id]):
        raise HTTPException(
            409, "Organization members must be added through the project team"
        )
    if invitation.access_until and invitation.access_until <= utcnow():
        raise HTTPException(410, "Project access has expired")
    await ensure_guest_profile(
        db, project.lab_id, user.id, invitation.invitation_display_name
    )
    user.project_guest = True
    values = {
        "project_id": invitation.project_id,
        "user_id": user.id,
        "role": invitation.project_role,
        "access_until": invitation.access_until,
    }
    await db.execute(
        insert(ProjectGuest)
        .values(**values)
        .on_conflict_do_update(
            index_elements=[ProjectGuest.project_id, ProjectGuest.user_id],
            where=ProjectGuest.access_until <= utcnow(),
            set_={
                "role": invitation.project_role,
                "access_until": invitation.access_until,
            },
        )
    )
    invitation.claim_invitation(user.id, utcnow())


def active_projects(user_id):
    return (
        select(Project, ProjectGuest)
        .join(ProjectGuest, ProjectGuest.project_id == Project.id)
        .where(
            ProjectGuest.user_id == user_id,
            Project.deleted_at.is_(None),
            or_(
                ProjectGuest.access_until.is_(None),
                ProjectGuest.access_until > utcnow(),
            ),
        )
    )


async def accessible_protocol(db, user_id, protocol_id, *, lock=False):
    query = (
        active_projects(user_id)
        .add_columns(Protocol)
        .join(Protocol, Protocol.project_id == Project.id)
        .where(
            Protocol.id == protocol_id,
            Protocol.deleted_at.is_(None),
            Protocol.inherit_permissions.is_(True),
            Project.permission_type == PermissionType.INHERIT,
        )
    )
    if lock:
        query = query.with_for_update(of=(Protocol, ProjectGuest))
    row = (await db.execute(query)).first()
    if not row:
        raise HTTPException(404, "Protocol not found")
    return row
