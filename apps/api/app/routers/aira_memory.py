"""Personal memory is session-authenticated; external Agent tokens have no access."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select

from app.database import DBSession
from app.models.aira_memory import AiraMemory, AiraMemoryEvent
from app.models.chat import Chat
from app.routers.depends import CurrentUser
from app.services.aira_memory import (
    MemoryUpdate,
    conversation_feedback,
    decide_feedback,
    read_memory,
    update_memory,
)

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


class ConversationDecision(BaseModel):
    action: Literal["disable", "accept", "dismiss", "undo"]
    offer_id: UUID | None = None


async def owned_chat(db, user, chat_id, *, lock=False):
    query = select(Chat).where(Chat.id == chat_id, Chat.user_id == user.id)
    chat = await db.scalar(query.with_for_update() if lock else query)
    if not chat:
        raise HTTPException(404, "Conversation not found")
    return chat


@router.get("/conversations/{chat_id}")
async def conversation_controls(chat_id: UUID, db: DBSession, user: CurrentUser):
    chat = await owned_chat(db, user, chat_id)
    disabled = bool((chat.context or {}).get("memory_disabled"))
    feedback = (
        {}
        if disabled
        else conversation_feedback(await db.get(AiraMemory, user.id), chat_id)
    )
    return private_response({"disabled": disabled, "feedback": feedback})


@router.patch("/conversations/{chat_id}")
async def change_conversation_memory(
    chat_id: UUID, body: ConversationDecision, db: DBSession, user: CurrentUser
):
    chat = await owned_chat(db, user, chat_id, lock=True)
    disabled = bool((chat.context or {}).get("memory_disabled"))
    if body.action == "disable":
        chat.context = {**(chat.context or {}), "memory_disabled": True}
        disabled, feedback = True, {}
    elif disabled or not body.offer_id:
        raise HTTPException(
            409, "Personal memory is unavailable for this conversation."
        )
    else:
        feedback = await decide_feedback(
            db, user.id, chat_id, body.action, body.offer_id
        )
    await db.commit()
    return private_response({"disabled": disabled, "feedback": feedback})
