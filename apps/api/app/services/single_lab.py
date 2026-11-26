import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import config
from app.models.account_token import AccountToken, AccountTokenType
from app.models.lab import Lab, LabRole, LabUser
from app.models.project import Project, ProjectRole, ProjectType, ProjectUser
from app.models.user import User


def utcnow() -> datetime:
    # Existing schema stores naive UTC-compatible timestamps.
    return datetime.now(UTC).replace(tzinfo=None)


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def account_for_email(db: AsyncSession, email: str) -> User | None:
    # Legacy profile edits could preserve mixed case. Never bind an ambiguous address.
    matches = (await db.scalars(
        select(User).where(func.lower(User.email) == normalize_email(email)).limit(2)
    )).all()
    if len(matches) > 1:
        raise HTTPException(409, "Resolve duplicate account emails before continuing")
    return matches[0] if matches else None


def hash_account_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def build_site_url(path: str) -> str:
    return f"{config.SITE_URL.rstrip('/')}/{path.lstrip('/')}"


async def get_single_lab(db_session: AsyncSession) -> Lab | None:
    if not config.is_single_lab:
        return None
    return await Lab.find_by(db_session, [Lab.uid == config.SINGLE_LAB_UID])


async def user_single_lab_role(
    db_session: AsyncSession,
    user_id: UUID,
    lab_id: UUID,
) -> LabRole | None:
    membership = await LabUser.find_by(
        db_session,
        [LabUser.lab_id == lab_id, LabUser.user_id == user_id],
    )
    return LabRole(membership.role) if membership is not None else None


async def user_can_manage_single_lab(
    db_session: AsyncSession,
    user_id: UUID,
    lab_id: UUID,
) -> bool:
    role = await user_single_lab_role(db_session, user_id, lab_id)
    return role in {LabRole.OWNER, LabRole.MANAGER}


async def ensure_default_project(
    db_session: AsyncSession,
    lab: Lab,
    owner: User,
    *,
    project_name: str | None = None,
) -> Project:
    project = await Project.find_by(
        db_session,
        [
            Project.lab_id == lab.id,
            Project.uid == config.SINGLE_LAB_DEFAULT_PROJECT_UID,
            Project.deleted_at.is_(None),
        ],
    )
    if project is None:
        project = Project(
            lab_id=lab.id,
            uid=config.SINGLE_LAB_DEFAULT_PROJECT_UID,
            name=project_name or config.SINGLE_LAB_DEFAULT_PROJECT_NAME,
            description="Private workspace for projects, documents, protocols and research."
            if config.DEPLOYMENT_MODE == "single_organization"
            else "Default private project for laboratory protocols and records.",
            type=ProjectType.PRIVATE,
            create_user_id=owner.id,
        )
        db_session.add(project)
        await db_session.flush()

    project_user = await ProjectUser.find_by(
        db_session,
        [ProjectUser.project_id == project.id, ProjectUser.user_id == owner.id],
    )
    if project_user is None:
        db_session.add(
            ProjectUser(
                project_id=project.id,
                user_id=owner.id,
                role=ProjectRole.OWNER,
                create_user_id=owner.id,
            )
        )

    lab.projects_count = await Project.count(
        db_session,
        [Project.lab_id == lab.id, Project.deleted_at.is_(None)],
    )
    return project


async def add_user_to_single_lab(
    db_session: AsyncSession,
    *,
    lab: Lab,
    user: User,
    created_by_user_id: UUID,
    display_name: str | None = None,
    lab_role: LabRole = LabRole.MEMBER,
    project_role: ProjectRole | None = ProjectRole.RECORDER,
) -> bool:
    # A concurrent conversion must win over an outstanding organization invitation.
    is_guest = await db_session.scalar(select(User.project_guest).where(User.id == user.id).with_for_update())
    if is_guest:
        raise HTTPException(409, "This account has external project access")
    # Serialize joins from distinct invitations before checking membership and updating the count.
    await db_session.execute(
        select(Lab.id).where(Lab.id == lab.id).with_for_update(key_share=True)
    )
    membership = await LabUser.find_by(
        db_session, [LabUser.lab_id == lab.id, LabUser.user_id == user.id]
    )
    if membership is not None:
        return False
    db_session.add(
        LabUser(
            lab_id=lab.id,
            user_id=user.id,
            role=lab_role,
            alias=display_name,
            create_user_id=created_by_user_id,
        )
    )
    await db_session.flush()

    default_project = await Project.find_by(
        db_session,
        [
            Project.lab_id == lab.id,
            Project.uid == config.SINGLE_LAB_DEFAULT_PROJECT_UID,
            Project.deleted_at.is_(None),
        ],
    )
    if default_project is not None and project_role is not None:
        project_membership = await ProjectUser.find_by(
            db_session,
            [
                ProjectUser.project_id == default_project.id,
                ProjectUser.user_id == user.id,
            ],
        )
        if project_membership is None:
            db_session.add(
                ProjectUser(
                    project_id=default_project.id,
                    user_id=user.id,
                    role=project_role,
                    create_user_id=created_by_user_id,
                )
            )

    lab.users_count = await LabUser.count(db_session, [LabUser.lab_id == lab.id])
    return True


async def create_account_token(
    db_session: AsyncSession,
    *,
    token_type: AccountTokenType,
    created_by_user_id: UUID | None,
    expires_in: timedelta,
    email: str = "",
    invitation_display_name: str | None = None,
    invitation_note: str | None = None,
    lab_id: UUID | None = None,
    user_id: UUID | None = None,
    lab_role: LabRole | None = None,
    project_role: ProjectRole | None = None,
    project_id: UUID | None = None,
    access_until: datetime | None = None,
) -> tuple[AccountToken, str]:
    normalized_email = normalize_email(email) if email else ""
    invalidation = update(AccountToken).where(
        AccountToken.token_type == token_type.value,
        AccountToken.consumed_at.is_(None),
    )
    if token_type == AccountTokenType.PASSWORD_RESET:
        await db_session.execute(
            invalidation.where(AccountToken.user_id == user_id).values(
                consumed_at=utcnow()
            )
        )
    elif normalized_email:
        await db_session.execute(
            invalidation.where(
                AccountToken.lab_id == lab_id,
                AccountToken.email == normalized_email,
                AccountToken.project_id == project_id,
                AccountToken.expires_at > utcnow(),
            ).values(consumed_at=utcnow(), invitation_outcome="revoked")
        )

    raw_token = secrets.token_urlsafe(32)
    token = AccountToken(
        token_hash=hash_account_token(raw_token),
        token_type=token_type.value,
        email=normalized_email,
        project_id=project_id,
        access_until=access_until,
        invitation_display_name=invitation_display_name,
        invitation_note=invitation_note,
        lab_id=lab_id,
        user_id=user_id,
        lab_role=lab_role.value if lab_role is not None else None,
        project_role=project_role.value if project_role is not None else None,
        created_by_user_id=created_by_user_id,
        expires_at=utcnow() + expires_in,
    )
    db_session.add(token)
    await db_session.flush()
    return token, raw_token


async def revoke_lab_account_tokens(
    db_session: AsyncSession,
    *,
    lab_id: UUID,
    user_id: UUID,
    include_targeted_tokens: bool,
) -> None:
    actor_condition = AccountToken.created_by_user_id == user_id
    ownership_condition = (
        or_(actor_condition, AccountToken.user_id == user_id)
        if include_targeted_tokens
        else actor_condition
    )
    await db_session.execute(
        update(AccountToken)
        .where(
            AccountToken.lab_id == lab_id,
            AccountToken.consumed_at.is_(None),
            ownership_condition,
            AccountToken.expires_at > utcnow(),
        )
        .values(
            consumed_at=utcnow(),
            invitation_outcome=case(
                (
                    AccountToken.token_type == AccountTokenType.INVITATION.value,
                    "revoked",
                ),
                else_=AccountToken.invitation_outcome,
            ),
        )
    )


async def find_valid_account_token(
    db_session: AsyncSession,
    raw_token: str,
    token_type: AccountTokenType | tuple[AccountTokenType, ...],
    *,
    for_update: bool = False,
) -> AccountToken | None:
    statement = (
        select(AccountToken)
        .where(
            AccountToken.token_hash == hash_account_token(raw_token),
            AccountToken.token_type.in_(token_type if isinstance(token_type, tuple) else (token_type,)),
            AccountToken.consumed_at.is_(None),
            AccountToken.expires_at > utcnow(),
        )
        .limit(1)
    )
    if for_update:
        statement = statement.with_for_update()
    return (await db_session.execute(statement)).scalar()


def invitation_url(raw_token: str) -> str:
    return build_site_url(f"join?token={quote(raw_token, safe='')}")


def password_reset_url(raw_token: str) -> str:
    return build_site_url(f"reset-password?token={quote(raw_token, safe='')}")
