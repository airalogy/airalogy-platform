"""Organization entry points delegate to the established authorization handlers.

Other specialized legacy endpoints remain at /labs during the compatibility
period. No second identity, grants, or asset migration is introduced here.
"""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.database import DBSession
from app.models.organization import OrganizationType
from . import labs
from .depends import CurrentUser, get_current_user

router = APIRouter(
    prefix="/organizations",
    tags=["organizations"],
    dependencies=[Depends(get_current_user)],
)


class OrganizationCreate(labs.LabCreateParams):
    organization_type: OrganizationType = OrganizationType.OTHER


@router.get("")
async def list_organizations(
    db_session: DBSession,
    current_user: CurrentUser,
    params=Depends(labs.LabQueryParams),
    page: int = 1,
    page_size: int = 10,
):
    return await labs.get_labs(db_session, current_user, params, page, page_size)


@router.get("/uid/{organization_uid}")
async def get_by_uid(
    organization_uid: str, db_session: DBSession, current_user: CurrentUser
):
    return await labs.get_lab_by_uid(organization_uid, db_session, current_user)


@router.get("/{organization_id}")
async def get_by_id(
    organization_id: UUID, db_session: DBSession, current_user: CurrentUser
):
    return await labs.get_lab_by_id(organization_id, db_session, current_user)


@router.post("")
async def create_organization(
    params: OrganizationCreate, current_user: CurrentUser, db_session: DBSession
):
    return await labs.create_lab(params, current_user, db_session)


@router.put("/{organization_id}")
async def update_organization(
    organization_id: UUID,
    params: labs.LabUpdateParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    return await labs.update_lab(organization_id, params, current_user, db_session)


@router.get("/{organization_id}/members")
async def get_members(
    organization_id: UUID,
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 10,
):
    result = await labs.get_lab_users(
        organization_id, db_session, current_user, page, page_size
    )
    return {
        "members": [
            {**user, "organization_role": user["lab_role"]} for user in result["users"]
        ],
        "total_count": result["total_count"],
    }


@router.post("/{organization_id}/members")
async def add_member(
    organization_id: UUID,
    params: labs.LabAddUserParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    return await labs.add_user_to_lab(organization_id, params, current_user, db_session)


@router.put("/{organization_id}/members/{user_id}")
async def update_member(
    organization_id: UUID,
    user_id: UUID,
    params: labs.LabAddUserParams,
    current_user: CurrentUser,
    db_session: DBSession,
):
    return await labs.change_user_role_or_alias_in_lab(
        organization_id, user_id, params, current_user, db_session
    )


@router.delete("/{organization_id}/members/{user_id}")
async def remove_member(
    organization_id: UUID,
    user_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    return await labs.delete_user_from_lab(
        organization_id, user_id, current_user, db_session
    )
