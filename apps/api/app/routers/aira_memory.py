"""Personal memory is session-authenticated; external Agent tokens have no access."""

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.database import DBSession
from app.models.aira_memory import AiraMemoryEvent
from app.routers.depends import CurrentUser
from app.services.aira_memory import MemoryUpdate, read_memory, update_memory

router = APIRouter(prefix="/aira-memory", tags=["personal-memory"])


def private_response(data, *, export=False):
    headers = {"Cache-Control": "no-store"}
    if export:
        headers["Content-Disposition"] = 'attachment; filename="aira-preferences.json"'
    return JSONResponse(jsonable_encoder(data), headers=headers)


@router.get("")
async def get_memory(db: DBSession, user: CurrentUser):
    return private_response(await read_memory(db, user.id))


@router.patch("")
async def patch_memory(body: MemoryUpdate, db: DBSession, user: CurrentUser):
    result = await update_memory(db, user.id, body)
    await db.commit()
    return private_response(result)


@router.get("/export")
async def export_memory(db: DBSession, user: CurrentUser):
    return private_response(
        {"schema_version": 1, "scope": "personal", **await read_memory(db, user.id)},
        export=True,
    )


@router.get("/activity")
async def activity(db: DBSession, user: CurrentUser):
    events = (
        await db.scalars(
            select(AiraMemoryEvent)
            .where(AiraMemoryEvent.user_id == user.id)
            .order_by(AiraMemoryEvent.revision.desc())
            .limit(50)
        )
    ).all()
    return private_response(
        [event.as_dict(excludes=["user_id", "request_id"]) for event in events]
    )
