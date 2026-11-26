import os

from fastapi import APIRouter, Depends, HTTPException

from app.database import DBSession
from app.routers.depends import CurrentUser
from app.routers.instance import ensure_single_lab_mode, require_single_lab_manager
from app.services.backup_console import (
    BackupRequest, Conflict, PolicyChange, queue, set_policy, state,
)


async def require_backup_operator(current_user: CurrentUser, db_session: DBSession):
    ensure_single_lab_mode()
    operators = {item.strip() for item in os.getenv("BACKUP_OPERATOR_IDS", "").split(",")}
    if str(current_user.id) not in operators:
        raise HTTPException(403, detail="Backup operator access required")
    await require_single_lab_manager(db_session, current_user)


router = APIRouter(prefix="/instance/backups", tags=["instance"], dependencies=[Depends(require_backup_operator)])


@router.get("")
def get_backups():
    with state() as data:
        return {k: v for k, v in data.items() if k != "last_slot"}


@router.put("/policy")
def update_policy(body: PolicyChange):
    try:
        with state() as data:
            set_policy(body, data)
            return {"revision": data["revision"]}
    except Conflict as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.post("/requests", status_code=202)
def request_backup(body: BackupRequest):
    try:
        with state() as data:
            queue(body, data)
        return {"queued": True}
    except Conflict as exc:
        raise HTTPException(409, detail=str(exc)) from exc
