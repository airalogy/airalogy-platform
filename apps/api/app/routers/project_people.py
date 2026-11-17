"""Project contact management does not change membership or access."""

from uuid import UUID

from fastapi import APIRouter

from app.database import DBSession
from app.routers.depends import CurrentUser
from app.services import project_people as service

router = APIRouter(prefix="/project-people", tags=["project-people"])


@router.get("")
async def list_people(
    project_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    return await service.list_people(db_session, current_user, project_id)


@router.post("")
async def create_person(
    data: service.PersonCreate, current_user: CurrentUser, db_session: DBSession
):
    result = await service.create_person(db_session, current_user, data)
    await db_session.commit()
    return result


@router.put("/{person_id}")
async def update_person(
    person_id: UUID,
    data: service.PersonUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    result = await service.update_person(db_session, current_user, person_id, data)
    await db_session.commit()
    return result
