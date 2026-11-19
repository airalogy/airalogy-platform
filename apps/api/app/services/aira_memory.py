"""Deterministic P0 memory. No extraction from documents, tools or past chats.

Only allowlisted presentation preferences can enter the model context. Keeping
scientific information out by construction is stronger than a prompt requesting
that a model distinguish historical values from measurements.
"""

import asyncio
import logging
import re
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import sessionmanager
from app.models.aira_memory import AiraMemory, AiraMemoryEvent

# The legacy wire text also keeps forgotten preferences out of model history.
MEMORY_REQUEST = {"role": "user", "content": "[Personal memory management request]"}
MEMORY_HANDLED = {
    "role": "assistant",
    "content": "[Memory management handled by Platform; no research data changed.]",
}


def is_memory_turn(messages: list[dict], index: int) -> bool:
    return (
        0 <= index < len(messages) - 1
        and messages[index] == MEMORY_REQUEST
        and messages[index + 1] == MEMORY_HANDLED
    )


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


async def lock_memory(db: AsyncSession, user_id: UUID) -> AiraMemory:
    # A row per account serializes different clients, clears and command retries.
    await db.execute(
        insert(AiraMemory)
        .values(user_id=user_id, enabled=True, revision=0, preferences={})
        .on_conflict_do_nothing()
    )
    return await db.scalar(
        select(AiraMemory)
        .where(AiraMemory.user_id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


async def update_memory(
    db: AsyncSession,
    user_id: UUID,
    request: MemoryUpdate,
    *,
    source="settings",
    chat_id: UUID | None = None,
) -> dict:
    memory = await lock_memory(db, user_id)
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
    # Any subsequent edit invalidates the undo offer and outstanding suggestions.
    interaction = {}
    if (
        source == "chat"
        and chat_id
        and request.changes
        and all(request.changes.values())
    ):
        interaction["undo"] = {
            "id": str(request.request_id),
            "chat_id": str(chat_id),
            "previous": {key: memory.preferences.get(key) for key in request.changes},
        }
    memory.interaction = interaction
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
            "简洁一点",
            "简短一点",
            "回答简短些",
            "简短回答",
            "回答简洁一点",
            "回答简短一点",
            "be concise",
        ],
        "detailed": ["详细回答", "详细解释", "回答详细一点", "be detailed"],
    },
    "format": {
        "paragraphs": ["用段落回答", "使用段落", "use paragraphs"],
        "steps": [
            "分步骤回答",
            "分步骤写",
            "按步骤回答",
            "分点回答",
            "使用编号步骤",
            "use numbered steps",
        ],
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


def normalized(text: str) -> str:
    return text.strip().rstrip("。.!！").strip().lower()


def requested_style(text: str, *, include_once=False) -> tuple[str, str] | None:
    """Only a direct, allowlisted style instruction, optionally after a question."""
    tail = re.split(r"[。！？!?\n]", normalized(text))[-1].strip()
    if include_once:
        tail = re.sub(r"^(?:这一次|这次|本次|for this answer[, ]+)\s*", "", tail)
    return ALIASES.get(tail.removeprefix("请").removeprefix("please ").strip())


def numbered_answer(text: str) -> bool:
    """Recognize visible numbered steps, never copy their content into memory."""
    if "```" in text or "~~~" in text:
        return False
    numbers = re.findall(r"^[ \t]*(\d{1,2})(?:[.)][ \t]+|、[ \t]*)\S", text, re.MULTILINE)
    return 2 <= len(numbers) <= 99 and [int(n) for n in numbers] == list(
        range(1, len(numbers) + 1)
    )


def parse_command(
    text: str, previous: str = "", previous_answer: str = ""
) -> dict | None:
    text = normalized(text)
    refer = r"(?:以后(?:请)?都(?:这样|这么)(?:写|回答|说)?|from now on like this)"
    match = re.fullmatch(r"(?:(.+?)[，,。；;]\s*)?" + refer, text)
    if match:
        pair = requested_style(match[1] or previous, include_once=True)
        if not pair and not match[1] and numbered_answer(previous_answer):
            pair = ("format", "steps")
        return {"changes": dict([pair])} if pair else {"clarify": True}
    if text in ("忘记所有个人偏好", "清除所有个人记忆", "forget all my preferences"):
        return {"clear": True}
    match = re.fullmatch(r"(?:请)?(?:忘记|forget)\s*[:：]?\s*(.+)", text)
    if match:
        key = FORGET_KEYS.get(match[1])
        return {"changes": {key: None}} if key else {"unsupported": True}
    match = re.fullmatch(
        r"(?:请)?(?:记住我的偏好|记住|以后(?:请)?(?:都)?|from now on[, ]+|always |remember(?: my preference)?)[：:,，\s]*(.+)",
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


def conversation_feedback(memory: AiraMemory | None, chat_id: UUID) -> dict:
    if not memory or not memory.enabled:
        return {}
    state = memory.interaction or {}
    for key, item in state.get("signals", {}).items():
        if item.get("chat_id") == str(chat_id) and item.get("stage") == "offered":
            return {
                "kind": "suggest",
                "id": item["id"],
                "key": key,
                "value": item["value"],
            }
    undo = state.get("undo", {})
    if undo.get("chat_id") == str(chat_id):
        return {"kind": "saved", "id": undo["id"]}
    return {}


async def observe_style(db, user_id, chat_id, request_id, pair, expected_revision):
    """Track at most one signal per allowlisted category, without message text."""
    memory = await lock_memory(db, user_id)
    key, value = pair
    if (
        not memory.enabled
        or memory.revision != expected_revision
        or memory.preferences.get(key, {}).get("value") == value
    ):
        return
    signals = dict((memory.interaction or {}).get("signals", {}))
    prior = signals.get(key, {})
    if prior.get("value") == value:
        if prior["stage"] != "seen" or prior["id"] == str(request_id):
            return
        stage = "offered"
    else:
        stage = "seen"
    signals[key] = {
        "value": value,
        "stage": stage,
        "id": str(request_id),
        "chat_id": str(chat_id),
    }
    memory.interaction = {**(memory.interaction or {}), "signals": signals}


async def decide_feedback(db, user_id, chat_id, action, offer_id):
    memory = await lock_memory(db, user_id)
    state = memory.interaction or {}
    feedback = conversation_feedback(memory, chat_id)
    if feedback.get("id") != str(offer_id):
        raise HTTPException(409, "This memory action is no longer current.")
    if action == "undo" and feedback["kind"] == "saved":
        previous = state["undo"]["previous"]
        await update_memory(
            db,
            user_id,
            MemoryUpdate(
                expected_revision=memory.revision,
                request_id=uuid4(),
                changes={k: v["value"] if v else None for k, v in previous.items()},
            ),
            source="chat",
            chat_id=chat_id,
        )
        values = dict(memory.preferences)
        for key, value in previous.items():
            if value is not None:
                values[key] = value
        memory.preferences = values
        memory.interaction = {}
    elif action in ("accept", "dismiss") and feedback["kind"] == "suggest":
        key = feedback["key"]
        if action == "accept":
            await update_memory(
                db,
                user_id,
                MemoryUpdate(
                    expected_revision=memory.revision,
                    request_id=uuid4(),
                    changes={key: feedback["value"]},
                ),
                source="chat",
                chat_id=chat_id,
            )
        else:
            signals = dict(state["signals"])
            signals[key] = {**signals[key], "stage": "dismissed"}
            memory.interaction = {**state, "signals": signals}
    else:
        raise HTTPException(409, "This memory action is no longer current.")
    return conversation_feedback(memory, chat_id)
