from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select

from app.database import DBSession
from app.models.lab import Lab, LabUser
from app.models.user import User
from app.models.user_alias import UserAlias
from app.routers.depends import CurrentUser, get_current_user
from app.routers.labs import require_configured_single_lab, require_lab_membership

router = APIRouter(prefix="/users", tags=["users"])


class UserAliasCreate(BaseModel):
    target_user_id: UUID
    alias: str


class BatchUserAliasParams(BaseModel):
    user_ids: List[UUID]
    lab_id: UUID | None = None


@router.post("/set_user_alias")
async def create_user_alias(
    alias_data: UserAliasCreate,
    db: DBSession,
    current_user: CurrentUser,
):
    """设置用户别名"""
    target_user = await User.find(db, id=alias_data.target_user_id)

    existing_alias = await UserAlias.find_by(
        db,
        [
            UserAlias.user_id == current_user.id,
            UserAlias.target_user_id == target_user.id,
        ],
    )

    if existing_alias:
        if existing_alias.alias == alias_data.alias:
            return {"success": True}
        elif alias_data.alias == "":
            await existing_alias.delete(db)
        else:
            existing_alias.alias = alias_data.alias
    elif alias_data.alias:
        await UserAlias.create(
            db,
            user_id=current_user.id,
            target_user_id=alias_data.target_user_id,
            alias=alias_data.alias,
        )
    await db.commit()
    return {"success": True}


@router.post("/get_user_aliases")
async def get_users_with_aliases(
    params: BatchUserAliasParams,
    db: DBSession,
    current_user: User = Depends(get_current_user),
):
    lab_users_map = {}
    if params.lab_id:
        lab = await Lab.find(db, id=params.lab_id)
        require_configured_single_lab(lab)
        await require_lab_membership(db, lab.id, current_user.id)
        lab_names = await db.execute(
            select(LabUser.user_id, LabUser.alias).where(
                LabUser.lab_id == lab.id,
                LabUser.user_id.in_(params.user_ids),
                LabUser.alias.isnot(None),
            )
        )
        lab_users_map = dict(lab_names.all())
    notes = await db.execute(
        select(UserAlias.target_user_id, UserAlias.alias).where(
            UserAlias.user_id == current_user.id,
            UserAlias.target_user_id.in_(params.user_ids),
        )
    )
    user_aliases_map = dict(notes.all())
    data = [
        {
            "id": user_id,
            "user_alias": user_aliases_map.get(user_id),
            "lab_alias": lab_users_map.get(user_id),
            "alias": user_aliases_map.get(user_id) or lab_users_map.get(user_id),
        }
        for user_id in params.user_ids
    ]

    return data
