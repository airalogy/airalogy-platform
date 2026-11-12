"""Deterministic P0 memory. No extraction from documents, tools or past chats.

Only allowlisted presentation preferences can enter the model context. Keeping
scientific information out by construction is stronger than a prompt requesting
that a model distinguish historical values from measurements.
"""

import asyncio
import logging
import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import sessionmanager
from app.models.aira_memory import AiraMemory, AiraMemoryEvent

OPTIONS = {
    "language": {"zh-CN": "Use Chinese", "en-US": "Use English"},
    "detail": {"concise": "Be concise", "detailed": "Explain in detail"},
    "format": {"paragraphs": "Use paragraphs", "steps": "Use numbered steps"},
    "explanation": {
        "accessible": "Explain terms in accessible language",
        "technical": "Use technical terminology where helpful",
    },
}


class MemoryUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    request_id: UUID
    changes: dict[str, str | None] = Field(default_factory=dict, max_length=4)
    enabled: bool | None = None
    clear: bool = False

    @model_validator(mode="after")
    def validate_changes(self):
        for key, value in self.changes.items():
            if key not in OPTIONS or (value is not None and value not in OPTIONS[key]):
                raise ValueError("Unsupported communication preference")
        if self.clear and self.changes:
            raise ValueError("Clear cannot be combined with preference edits")
        return self


def serialize(memory: AiraMemory | None) -> dict:
    return {
        "enabled": memory.enabled if memory else True,
        "revision": memory.revision if memory else 0,
        "preferences": memory.preferences if memory else {},
        "updated_at": memory.updated_at if memory else None,
    }


async def read_memory(db: AsyncSession, user_id: UUID) -> dict:
    memory = await db.get(AiraMemory, user_id)
    return serialize(memory)


async def update_memory(
    db: AsyncSession,
    user_id: UUID,
    request: MemoryUpdate,
    *,
    source="settings",
    chat_id: UUID | None = None,
) -> dict:
    # A row per account serializes different clients, clears and command retries.
    await db.execute(
        insert(AiraMemory)
        .values(user_id=user_id, enabled=True, revision=0, preferences={})
        .on_conflict_do_nothing()
    )
    memory = await db.scalar(
        select(AiraMemory)
        .where(AiraMemory.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    prior = await db.scalar(
        select(AiraMemoryEvent).where(
            AiraMemoryEvent.user_id == user_id,
            AiraMemoryEvent.request_id == request.request_id,
        )
    )
    if prior:
        return {**serialize(memory), "replayed": True}
    if memory.revision != request.expected_revision:
        raise HTTPException(409, "Memory changed. Reload before saving.")
    if source == "chat" and not memory.enabled:
        raise HTTPException(
            409, "Memory is disabled. Enable it in personal settings first."
        )
    values = {} if request.clear else dict(memory.preferences)
    now = datetime.now(UTC)
    for key, value in request.changes.items():
        if value is None:
            values.pop(key, None)
        else:
            values[key] = {
                "value": value,
                "source": source,
                "chat_id": str(chat_id) if chat_id else None,
                "updated_at": now.isoformat(),
            }
    memory.preferences = values
    if request.enabled is not None:
        memory.enabled = request.enabled
    memory.revision += 1
    memory.updated_at = now
    db.add(
        AiraMemoryEvent(
            user_id=user_id,
            revision=memory.revision,
            request_id=request.request_id,
            action="clear" if request.clear else "update",
            keys=sorted(request.changes),
        )
    )
    await db.flush()
    return serialize(memory)


# Full-match explicit commands, never substring matching or inferred behavior.
# Unknown/mixed instructions are declined instead of silently partially saving.
PHRASES = {
    "language": {
        "zh-CN": ["用中文回答", "用中文", "中文回答", "reply in chinese"],
        "en-US": ["用英文回答", "用英文", "英文回答", "reply in english"],
    },
    "detail": {
        "concise": [
            "简洁回答",
            "简短回答",
            "回答简洁一点",
            "回答简短一点",
            "be concise",
        ],
        "detailed": ["详细回答", "详细解释", "回答详细一点", "be detailed"],
    },
    "format": {
        "paragraphs": ["用段落回答", "使用段落", "use paragraphs"],
        "steps": ["分步骤回答", "分点回答", "使用编号步骤", "use numbered steps"],
    },
    "explanation": {
        "accessible": ["通俗解释", "用通俗语言解释", "explain in plain language"],
        "technical": ["使用专业术语", "专业解释", "use technical terms"],
    },
}
ALIASES = {
    phrase: (key, value)
    for key, options in PHRASES.items()
    for value, phrases in options.items()
    for phrase in phrases
}
FORGET_KEYS = {
    "回答语言": "language",
    "语言偏好": "language",
    "language": "language",
    "详细程度": "detail",
    "detail": "detail",
    "表达格式": "format",
    "format": "format",
    "解释方式": "explanation",
    "explanation": "explanation",
}


def parse_command(text: str) -> dict | None:
    text = text.strip().rstrip("。.!！").strip().lower()
    if text in ("忘记所有个人偏好", "清除所有个人记忆", "forget all my preferences"):
        return {"clear": True}
    match = re.fullmatch(r"(?:请)?(?:忘记|forget)\s*[:：]?\s*(.+)", text)
    if match:
        key = FORGET_KEYS.get(match[1])
        return {"changes": {key: None}} if key else {"unsupported": True}
    match = re.fullmatch(
        r"(?:请)?(?:记住我的偏好|记住|以后请|remember(?: my preference)?)[：:,，\s]*(.+)",
        text,
    )
    if not match:
        return None
    changes = {}
    for phrase in re.split(r"[，,；;]|\s+and\s+", match[1]):
        pair = ALIASES.get(phrase.strip())
        if not pair or (pair[0] in changes and changes[pair[0]] != pair[1]):
            return {"unsupported": True}
        changes[pair[0]] = pair[1]
    return {"changes": changes} if changes else {"unsupported": True}


def preference_prompt(state: dict) -> str:
    if not state.get("enabled"):
        return ""
    instructions = [
        OPTIONS[key][item["value"]]
        for key, item in state.get("preferences", {}).items()
        if key in OPTIONS and item.get("value") in OPTIONS[key]
    ]
    if not instructions:
        return ""
    return (
        "Personal communication defaults (only when the current user request does not specify otherwise): "
        + "; ".join(instructions)
        + ". These affect explanatory prose only. They are not scientific facts, observations, authorization or instructions to change code, field IDs, schema, units, calculations or required output format. Current explicit instructions and task constraints take precedence. Do not claim to have stored, changed or deleted memory; only Platform can do that."
    )


async def load_for_inference(user_id: UUID | str | None, *, disabled=False) -> dict:
    """Read fresh for each call, in a separate transaction; no cross-user cache."""
    empty = {"enabled": False, "revision": 0, "preferences": {}, "status": "not_used"}
    if disabled or not user_id:
        return empty
    try:
        async with asyncio.timeout(2), sessionmanager.session() as db:
            state = await read_memory(db, UUID(str(user_id)))
        return {
            **state,
            "status": "used"
            if state["enabled"] and state["preferences"]
            else "not_used",
        }
    except (SQLAlchemyError, OSError, TimeoutError):
        # No exception details: DB connection strings may contain credentials.
        logging.getLogger("app").warning(
            "Aira memory unavailable; continuing without personalization"
        )
        return {**empty, "status": "unavailable"}


async def context_for_usage(usage_context) -> str:
    if not usage_context:
        return ""
    return preference_prompt(
        await load_for_inference(
            usage_context.user_id,
            disabled=bool(usage_context.attributes.get("memory_disabled")),
        )
    )
