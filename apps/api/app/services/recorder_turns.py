"""Plan one Recorder turn. Model proposals can only change a browser form."""

import math
import re
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.libs.masterbrain import json_request
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.routers.permission import check_user_permission


class RecorderTarget(BaseModel):
    form_id: str = Field(pattern=r"^[A-Za-z0-9_-]{12,64}$")
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{12,64}$")
    version: str = Field(min_length=1, max_length=80)
    record_id: UUID | None = None
    filled: list[str] = Field(default_factory=list, max_length=1024)
    last_applied: list[str] = Field(default_factory=list, max_length=128)
    locale: Literal["en-US", "zh-CN"] = "en-US"


async def recorder_scope(db, user, project, protocol, target):
    record = None
    if target.record_id:
        record = await db.scalar(
            select(Record)
            .where(
                Record.id == target.record_id,
                Record.protocol_id == protocol.id,
            )
            .order_by(Record.version.desc())
            .limit(1)
        )
        if record is None or record.user_id != user.id:
            raise HTTPException(403, "Record is not editable")
        if record.protocol_version != target.version:
            raise HTTPException(409, "Record Protocol version changed")
    await check_user_permission(
        db,
        project=project,
        protocol=protocol,
        record=record,
        user=user,
        action="create_record",
    )
    version = await ProtocolVersion.find_by(
        db,
        [
            ProtocolVersion.protocol_id == protocol.id,
            ProtocolVersion.version == target.version,
        ],
    )
    if version is None:
        raise HTTPException(409, "Recorder Protocol version is unavailable")
    return version


def scalar_fields(version):
    schema = (version.json_schema or {}).get("vars") or {}
    assigned = set((version.assigners or {}).keys())
    for item in (version.assigners or {}).values():
        if isinstance(item, dict):
            assigned.update(item.get("assigned_fields") or [])
    fields = {}
    skipped = []
    for key, original in (schema.get("properties") or {}).items():
        if not isinstance(original, dict):
            continue
        spec = dict(original)
        if "anyOf" in spec:
            choices = [x for x in spec.pop("anyOf") if x.get("type") != "null"]
            if len(choices) == 1:
                spec.update(choices[0])
            else:
                skipped.append(key)
                continue
        ref = spec.get("$ref", "")
        if isinstance(ref, str) and ref.startswith("#/$defs/"):
            definition = schema.get("$defs", {}).get(ref.removeprefix("#/$defs/"))
            if (
                isinstance(definition, dict)
                and "enum" in definition
                and set(spec) <= {"$ref", "title", "description", "default"}
            ):
                spec = {**definition, **{k: v for k, v in spec.items() if k != "$ref"}}
        kind = spec.get("type")
        # Never resolve arbitrary refs or guess at resource/file/signature semantics.
        if (
            not key.isidentifier()
            or key in ("__proto__", "prototype", "constructor")
            or key in assigned
            or spec.get("readOnly")
            or spec.get("airalogy_type")
            or any(k in spec for k in ("$ref", "allOf", "oneOf", "not", "if"))
            or kind not in ("integer", "number", "string", "boolean")
            or spec.get("format") not in (None, "date", "time", "date-time")
        ):
            skipped.append(key)
        else:
            fields[key] = spec
    return fields, skipped


def valid_value(spec, value):
    if isinstance(value, float) and not math.isfinite(value):
        return False
    if isinstance(value, int) and abs(value) > (2**53 - 1):
        return False
    return Draft202012Validator(spec, format_checker=FormatChecker()).is_valid(value)


_UNIT_ALIASES = {
    "°c": {"°c", "℃", "摄氏度"},
    "min": {"min", "mins", "minute", "minutes", "分钟"},
    "h": {"h", "hr", "hrs", "hour", "hours", "小时"},
    "s": {"s", "second", "seconds", "秒", "秒钟"},
}


def matching_unit(message, source, spec):
    if spec.get("type") not in ("number", "integer"):
        return True
    # Bound the quoted number so "1" cannot come from "31" or "-1".
    matches = list(
        re.finditer(
            r"(?<![0-9A-Za-z_.+-])" + re.escape(source) + r"(?![0-9.eE])", message
        )
    )
    if not matches:
        return False
    unit = spec.get("unit")
    if not isinstance(unit, str):
        return True
    aliases = next(
        (group for group in _UNIT_ALIASES.values() if unit.casefold() in group), None
    )
    # Unknown units require exact spelling (notably mM versus mm). A number may
    # also be supplied without a unit when the field's unit is understood.
    for match in matches:
        suffix = message[match.end() :].lstrip()
        token = re.match(
            r"(?:[a-zA-Z°µμ%℃]+(?:/[a-zA-Zµμ]+)?|分钟|小时|秒钟|秒|摄氏度)", suffix
        )
        if token:
            observed = token[0]
            if observed.casefold() in {"and", "or", "for", "in", "to", "then"}:
                continue
            matches = observed.casefold() in aliases if aliases else observed == unit
            if not matches:
                return False
    return True


def grounded_value(spec, raw, source):
    """The extractor may normalize a value; it cannot invent a measurement."""
    kind = spec["type"]
    if kind in ("integer", "number"):
        try:
            number = Decimal(str(raw))
            if not number.is_finite() or number != Decimal(source):
                return None
            if kind == "integer" and number != number.to_integral_value():
                return None
            value = int(number) if kind == "integer" else float(number)
        except (ValueError, InvalidOperation, OverflowError):
            return None
    elif kind == "boolean":
        aliases = {
            "true": True,
            "false": False,
            "yes": True,
            "no": False,
            "是": True,
            "否": False,
            "真": True,
            "假": False,
        }
        value = aliases.get(source.casefold())
        if value is None or aliases.get(str(raw).casefold()) != value:
            return None
    else:
        value = source
        if str(raw) != source:
            return None
    return value if valid_value(spec, value) else None


async def plan_recorder_turn(chat, version, target, message, usage, *, attachment_texts=()):
    fields, _ = scalar_fields(version)
    scope = [str(version.id), str(target.record_id or ""), str(target.form_id)]
    prior = (chat.context or {}).get("recorder_focus", {})
    history = [
        {"role": m["role"], "content": m["content"][:2000]}
        for m in chat.messages[-12:]
        if m.get("role") in ("user", "assistant") and isinstance(m.get("content"), str)
    ]
    data = dict(
        protocol=version.aimd[:18000],
        fields=fields,
        filled=target.filled,
        locale=target.locale,
        conversation=history,
        references=prior.get("fields", []) if prior.get("scope") == scope else [],
        last_applied=target.last_applied,
        current_message=message,
    )
    if attachment_texts:
        data["attachment_texts"] = attachment_texts
    try:
        result = await json_request(
            "endpoints/chat/field_input/turn",
            {
                **data,
                "model": {"name": chat.model["name"]},
            },
            usage_context=usage,
        )
    except HTTPException as exc:
        if exc.status_code == 404 and exc.detail == "Not Found":
            raise HTTPException(
                503,
                "Conversational Record filling requires Masterbrain 0.14.0 or later",
            ) from exc
        raise
    # The 0.14 public module loads provider settings on import. In package
    # mode the transport installs the host configuration before this import.
    from masterbrain.recorder import RecorderTurnResponse

    plan = RecorderTurnResponse.model_validate(result)
    if attachment_texts and plan.attachment_count != len(attachment_texts):
        raise HTTPException(503, "This Masterbrain service does not support Recorder attachments")
    evidence = [message, *attachment_texts]
    focus = [key for key in plan.references if key in fields]
    operations = {}
    skipped = []
    reply = plan.answer
    if plan.intent == "simulate":
        reply = (
            "要试用示例数据，请打开 Protocol 编辑器，在预览中选择「用示例数据测试」。当前记录保持原样。"
            if target.locale == "zh-CN"
            else "To try example data, open the Protocol editor and choose Test with example data in Preview. Your Record is unchanged."
        )
    elif plan.intent == "fill":
        for op in plan.operations:
            key = op.rf_name
            if (
                key not in fields
                or not any(op.source in text for text in evidence)
                or key in operations
                or key in skipped
            ):
                skipped.append(key)
                operations.pop(key, None)
                continue
            value = grounded_value(fields[key], op.rf_value, op.source)
            if value is None or not any(
                op.source in text and matching_unit(text, op.source, fields[key])
                for text in evidence
            ):
                skipped.append(key)
            else:
                operations[key] = value
    return (
        reply,
        {"scope": scope, "fields": focus},
        {
            "request_id": str(target.request_id),
            "form_id": str(target.form_id),
            "intent": plan.intent,
            "values": operations,
            "skipped": skipped,
        },
    )
