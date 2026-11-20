"""Organization entry points delegate to the established authorization handlers.

Other specialized legacy endpoints remain at /labs during the compatibility
period. No second identity, grants, or asset migration is introduced here.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from app.config import config
from app.database import DBSession
from app.models.lab import Lab
from app.models.organization import OrganizationType
from app.models.organization_ai import OrganizationAI
from app.services import organization_ai as ai
from app.services.chat_models import ChatCapabilities, enabled_chat_model_types

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


@router.get("/uid/{organization_uid}/ai-capabilities")
async def ai_capabilities(
    organization_uid: str, current_user: CurrentUser, db_session: DBSession
) -> ChatCapabilities:
    org = await Lab.find_by(db_session, [Lab.uid == organization_uid])
    if not org:
        raise HTTPException(404, "Organization unavailable")
    labs.require_configured_single_lab(org)
    await labs.require_lab_membership(db_session, org.id, current_user.id)
    await ai.bind_organization(db_session, org.id)
    return ChatCapabilities(
        ai_enabled=config.effective_ai_enabled,
        enabled_chat_models=list(enabled_chat_model_types()),
    )


async def ai_manager(db, org_id, user):
    org = await db.get(Lab, org_id)
    if org is None:
        raise HTTPException(404, "Organization unavailable")
    labs.require_configured_single_lab(org)
    await labs.require_lab_manager(db, org_id, user.id)


async def key_form(request, cls):
    # Validation errors from a secret-bearing form must never echo its input.
    try:
        return cls.model_validate(await request.json())
    except (ValidationError, ValueError, UnicodeError):
        raise HTTPException(422, "Invalid AI settings") from None


@router.get("/{organization_id}/ai-settings")
async def get_ai_settings(
    organization_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    await ai_manager(db_session, organization_id, current_user)
    return ai.status(await db_session.get(OrganizationAI, organization_id))


@router.put("/{organization_id}/ai-settings")
async def update_ai_settings(
    organization_id: UUID,
    request: Request,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await ai_manager(db_session, organization_id, current_user)
    return await ai.save_settings(
        db_session, organization_id, await key_form(request, ai.SettingsInput)
    )


@router.post("/{organization_id}/ai-settings/test")
async def test_ai_settings(
    organization_id: UUID,
    request: Request,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await ai_manager(db_session, organization_id, current_user)
    data = await key_form(request, ai.KeyInput)
    row = await db_session.get(OrganizationAI, organization_id)
    await db_session.commit()
    return await ai.test_key(row, data)
