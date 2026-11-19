"""Reusable people, with explicit account association and no ACL side effects."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select

from app.models.lab import LabUser
from app.models.project import ProjectUser
from app.models.project_person import ProjectPerson
from app.models.user import User
from app.services.knowledge import canonical_digest
from app.services.project_work import project_context
from app.services.research_runtime import has_research_capability


class PersonContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    organization: str = Field(default="", max_length=255)
    user_id: UUID | None = None

    @model_validator(mode="after")
    def meaningful_name(self):
        self.name = self.name.strip()
        self.organization = self.organization.strip()
        if not self.name:
            raise ValueError("A person's name is required")
        return self


class PersonCreate(PersonContent):
    id: UUID
    project_id: UUID


class PersonUpdate(PersonContent):
    expected_revision: int = Field(ge=1)


def organization_display_name():
    return func.coalesce(
        func.nullif(func.trim(LabUser.alias), ""),
        func.nullif(User.name, ""),
        User.username,
    ).label("display_name")


def organization_accounts(lab_id):
    display_name = organization_display_name()
    return (
        select(User, display_name)
        .join(LabUser, LabUser.user_id == User.id)
        .where(LabUser.lab_id == lab_id)
        .order_by(display_name, User.username, User.id)
    )


async def organization_names(db, lab_id, user_ids):
    if not user_ids:
        return {}
    rows = await db.execute(organization_accounts(lab_id).where(User.id.in_(user_ids)))
    return {user.id: display_name for user, display_name in rows}


def person_view(person):
    return {
        key: getattr(person, key)
        for key in ("id", "project_id", "name", "organization", "user_id", "revision")
    }


async def require_person(db, project_id, identity):
    person = await db.get(ProjectPerson, identity)
    if not person or person.project_id != project_id:
        raise HTTPException(422, "Person must belong to this project")
    return person


async def can_manage_accounts(db, user, project):
    from app.routers.permission import check_user_permission

    try:
        await check_user_permission(db, project, user, "update_project")
        return True
    except HTTPException:
        return False


async def require_account_manager(db, user, project):
    if not await can_manage_accounts(db, user, project):
        raise HTTPException(403, "Only project administrators may associate accounts")


async def validate_account(db, project, data, person_id):
    if not data.user_id:
        return
    user = await db.get(User, data.user_id)
    if not user or not await has_research_capability(
        db, user=user, project=project, capability="log.read"
    ):
        raise HTTPException(422, "Account needs current project access")
    existing = await db.scalar(
        select(ProjectPerson).where(
            ProjectPerson.project_id == project.id,
            ProjectPerson.user_id == user.id,
            ProjectPerson.id != person_id,
        )
    )
    if existing:
        raise HTTPException(409, "Account already associated with a project person")


async def list_people(db, user, project_id):
    project = await project_context(db, user, project_id)
    from app.models.project_work import ProjectWork
    from app.models.research import ResearchTask

    counts = dict(
        (
            await db.execute(
                select(ProjectWork.assignee_person_id, func.count())
                .join(ResearchTask, ResearchTask.id == ProjectWork.task_id)
                .where(
                    ResearchTask.project_id == project_id,
                    ResearchTask.archived_at.is_(None),
                )
                .group_by(ProjectWork.assignee_person_id)
            )
        ).all()
    )
    people = (
        await db.scalars(
            select(ProjectPerson)
            .where(ProjectPerson.project_id == project_id)
            .order_by(ProjectPerson.name, ProjectPerson.id)
        )
    ).all()
    linked_ids = [p.user_id for p in people if p.user_id]
    names = await organization_names(db, project.lab_id, linked_ids)
    return {
        "can_manage_accounts": await can_manage_accounts(db, user, project),
        "can_write": await has_research_capability(
            db, user=user, project=project, capability="log.write"
        ),
        "people": [
            {
                **person_view(p),
                "display_name": names.get(p.user_id, p.name),
                "assigned_count": counts.get(p.id, 0),
            }
            for p in people
        ],
    }


async def team_roster(db, user, project_id):
    project = await project_context(db, user, project_id)
    # Direct project roles have their own paginated, editable list.
    direct_member = (
        select(ProjectUser.id)
        .where(ProjectUser.project_id == project_id, ProjectUser.user_id == User.id)
        .exists()
    )
    candidates = await db.execute(
        organization_accounts(project.lab_id).where(~direct_member)
    )
    additional_members = []
    for account, display_name in candidates.unique():
        if await has_research_capability(
            db, user=account, project=project, capability="research.read"
        ):
            additional_members.append(
                {
                    "id": account.id,
                    "name": account.name,
                    "username": account.username,
                    "display_name": display_name,
                }
            )
    participants = await db.execute(
        select(ProjectPerson.id, ProjectPerson.name, ProjectPerson.organization)
        .where(ProjectPerson.project_id == project_id, ProjectPerson.user_id.is_(None))
        .order_by(ProjectPerson.name, ProjectPerson.id)
    )
    return {
        "additional_members": additional_members,
        "participants": participants.mappings().all(),
    }


async def create_person(db, user, data):
    project = await project_context(db, user, data.project_id, write=True, lock=True)
    digest = canonical_digest(data.model_dump(mode="json"))
    person = await db.get(ProjectPerson, data.id)
    if person:
        if (
            person.project_id != project.id
            or person.created_by_user_id != user.id
            or person.create_digest != digest
        ):
            raise HTTPException(409, "Person request ID belongs to different content")
        return person_view(person)
    if data.user_id:
        await require_account_manager(db, user, project)
    await validate_account(db, project, data, data.id)
    person = ProjectPerson(
        **data.model_dump(),
        created_by_user_id=user.id,
        create_digest=digest,
        revision=1,
    )
    if data.user_id:
        person.account_history = [
            {
                "actor_id": str(user.id),
                "at": datetime.now(UTC).isoformat(),
                "previous_user_id": None,
                "user_id": str(data.user_id),
                "revision": 1,
            }
        ]
    db.add(person)
    await db.flush()
    return person_view(person)


async def update_person(db, user, identity, data):
    person = await db.get(ProjectPerson, identity)
    if not person:
        raise HTTPException(404, "Person unavailable")
    project = await project_context(db, user, person.project_id, write=True, lock=True)
    await db.refresh(person)
    if person.revision != data.expected_revision:
        # An identical retry does not create another revision.
        if all(
            getattr(person, k) == v
            for k, v in data.model_dump(exclude={"expected_revision"}).items()
        ):
            return person_view(person)
        raise HTTPException(409, "Person changed; refresh before saving")
    if person.user_id != data.user_id:
        await require_account_manager(db, user, project)
        person.account_history = [
            *(person.account_history or []),
            {
                "actor_id": str(user.id),
                "at": datetime.now(UTC).isoformat(),
                "previous_user_id": str(person.user_id) if person.user_id else None,
                "user_id": str(data.user_id) if data.user_id else None,
                "revision": person.revision + 1,
            },
        ]
    await validate_account(db, project, data, identity)
    for key, value in data.model_dump(exclude={"expected_revision"}).items():
        setattr(person, key, value)
    person.revision += 1
    await db.flush()
    return person_view(person)
