from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert

from app.models.account_token import AccountTokenType
from app.models.lab import LabRole, LabUser
from app.models.project import PermissionType, Project, ProjectRole, ProjectUser
from app.models.project_guest import ProjectGuest
from app.models.protocol import Protocol
from app.models.user import User
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
    manager = await db.scalar(
        select(ProjectUser.id).where(
            ProjectUser.user_id == actor_id,
            ProjectUser.project_id == project_id,
            ProjectUser.role.in_((ProjectRole.OWNER, ProjectRole.MANAGER)),
        )
    )
    if role is None or manager is None:
        raise HTTPException(403, "Project manager required")
    return project


async def accept_project_invitation(db, invitation, user):
    if not invitation.project_id or not invitation.created_by_user_id:
        raise HTTPException(404, "Invitation is no longer available")
    await project_manager(db, invitation.project_id, invitation.created_by_user_id)
    await db.scalar(select(User.id).where(User.id == user.id).with_for_update())
    if await LabUser.exists(db, [LabUser.user_id == user.id]):
        raise HTTPException(
            409, "Organization members must be added through the project team"
        )
    if invitation.access_until and invitation.access_until <= utcnow():
        raise HTTPException(410, "Project access has expired")
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


async def accessible_protocol(db, user_id, protocol_id):
    row = (
        await db.execute(
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
    ).first()
    if not row:
        raise HTTPException(404, "Protocol not found")
    return row
