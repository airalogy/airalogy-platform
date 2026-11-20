from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, literal, or_, select, union_all

from app.database import DBSession
from app.models.chat import (
    Chat,
    ChatType,
)
from app.models.lab import Lab
from app.models.meeting import MeetingConversation
from app.models.project import Project
from app.models.research_log import ResearchLogEntry
from app.routers.chats.utils import UsageLimit
from app.routers.depends import CurrentUser, get_current_user
from app.services.aira_memory import is_memory_turn
from app.services.chat_models import enabled_chat_model_types
from app.services.meetings import meeting_read_condition
from app.services.research_runtime import has_research_capability

router = APIRouter(
    dependencies=[Depends(get_current_user)],
)


@router.get("/usage")
async def get_usage(db_session: DBSession, current_user: CurrentUser):
    user_limit = UsageLimit.get(current_user.level, UsageLimit[1])

    query = (
        select(Chat.model_type, func.sum(Chat.user_message_count).label("total_count"))
        .where(
            Chat.user_id == current_user.id,
            Chat.created_at >= datetime.combine(datetime.now(), datetime.min.time()),
        )
        .group_by(Chat.model_type)
    )
    result = await db_session.execute(query)
    rows = result.all()

    # Create a dict of used counts keyed by model_type (int value)
    used_counts = {row.model_type: row.total_count for row in rows}

    usage = {}
    for model_type in enabled_chat_model_types():
        count = used_counts.get(model_type.value, 0)
        limit = user_limit.get(model_type, 0)
        usage[model_type.name.capitalize()] = {"used": count, "limit": limit}

    return usage


@router.post("/history/owned")
async def owned_cached_conversations(
    db_session: DBSession,
    current_user: CurrentUser,
    ids: Annotated[list[UUID], Body(max_length=100)],
):
    owned = await db_session.scalars(
        select(Chat.id).where(Chat.user_id == current_user.id, Chat.id.in_(ids))
    )
    return {"ids": owned.all()}


@router.get("/history/global")
async def list_account_conversations(
    db_session: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
):
    meeting = MeetingConversation
    # Resolve each distinct project with the same capability as the project panel.
    projects = (
        await db_session.scalars(
            select(Project).where(
                Project.deleted_at.is_(None),
                Project.id.in_(
                    select(meeting.project_id).where(meeting.user_id == current_user.id)
                ),
            )
        )
    ).all()
    allowed = [
        project.id
        for project in projects
        if await has_research_capability(
            db_session, user=current_user, project=project, capability="log.write"
        )
    ]
    general_rows = select(
        Chat.id, Chat.updated_at, literal("general").label("kind")
    ).where(
        Chat.user_id == current_user.id,
        Chat.protocol_id.is_(None),
        Chat.type == ChatType.QA,
    )
    meeting_rows = select(
        meeting.id, meeting.updated_at, literal("meeting").label("kind")
    ).where(
        meeting.user_id == current_user.id,
        meeting.project_id.in_(allowed),
        or_(
            meeting.meeting_id.is_(None),
            meeting.meeting_id.in_(
                select(ResearchLogEntry.id).where(
                    ResearchLogEntry.archived_at.is_(None),
                    meeting_read_condition(current_user.id),
                )
            ),
        ),
    )
    history = union_all(general_rows, meeting_rows).subquery()
    window = (
        select(history)
        .order_by(history.c.updated_at.desc(), history.c.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size + 1)
        .subquery()
    )
    rows = (
        await db_session.execute(
            select(
                window,
                Chat.messages,
                meeting.title,
                meeting.meeting_id,
                Project.name.label("project_name"),
                Project.uid.label("project_uid"),
                Lab.uid.label("lab_uid"),
            )
            .outerjoin(Chat, (window.c.kind == "general") & (Chat.id == window.c.id))
            .outerjoin(
                meeting, (window.c.kind == "meeting") & (meeting.id == window.c.id)
            )
            .outerjoin(Project, Project.id == meeting.project_id)
            .outerjoin(Lab, Lab.id == Project.lab_id)
            .order_by(window.c.updated_at.desc(), window.c.id.desc())
        )
    ).all()
    items = []
    for row in rows[:page_size]:
        if row.kind == "meeting":
            items.append(
                {
                    "id": row.id,
                    "title": row.title,
                    "kind": row.kind,
                    "updated_at": row.updated_at,
                    "project_name": row.project_name,
                    "project_uid": row.project_uid,
                    "lab_uid": row.lab_uid,
                    "meeting_id": row.meeting_id,
                }
            )
            continue
        messages = row.messages
        first_index = next(
            (i for i, m in enumerate(messages) if m.get("role") == "user"), -1
        )
        first = messages[first_index] if first_index >= 0 else {}
        title = first.get("content") or next(
            (
                f.get("file_name")
                for f in (first.get("files") or [])
                if f.get("file_name")
            ),
            "",
        )
        items.append(
            {
                "id": row.id,
                "title": str(title)[:120],
                "title_is_memory_request": is_memory_turn(messages, first_index),
                "updated_at": row.updated_at,
            }
        )
    return {"items": items, "has_more": len(rows) > page_size}


@router.get("/{chat_id}")
async def get_chat(chat_id: UUID, db_session: DBSession, current_user: CurrentUser):
    chat = await db_session.scalar(
        select(Chat).where(Chat.id == chat_id, Chat.user_id == current_user.id)
    )
    if chat is None:
        raise HTTPException(status_code=404, detail="Conversation unavailable")
    detail = chat.as_dict()
    if chat.type == ChatType.QA:
        summaries = {}
        for i in range(len(chat.messages) - 1):
            if is_memory_turn(chat.messages, i):
                summaries[i] = "request"
                summaries[i + 1] = "handled"
        if summaries:
            detail["memory_summaries"] = summaries
    return detail


@router.get("/")
async def get_chat_history(
    db_session: DBSession,
    current_user: CurrentUser,
    type: ChatType,
    protocol_id: UUID | None = None,
    page: int = 1,
    page_size: int = 10,
):
    chats = await Chat.all(
        db_session,
        [
            Chat.user_id == current_user.id,
            Chat.protocol_id == protocol_id,
            Chat.type == type,
        ],
        page=page,
        page_size=page_size,
        order_by=[Chat.id.desc()],
    )
    return {"chats": [c.as_dict() for c in chats]}
