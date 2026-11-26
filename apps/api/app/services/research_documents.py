"""Bounded declarative document contracts; AIMD is parsed by the official SDK.

No generated Python, assigner, collector or user type is executed here. A document
can always be saved as a draft even when its future structured result is invalid.
"""

import ast
import json
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from airalogy.markdown import parse_aimd, validate_aimd
from airalogy.record.validator import validate_record_quiz_answers_with_aimd
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    create_model,
    model_validator,
)

from app.services.knowledge import canonical_digest

DOCUMENT_FORMAT = "airalogy.research-document.v1"
DocumentKind = Literal[
    "document",
    "experiment",
    "progress",
    "meeting",
    "reflection",
    "blocker",
    "milestone",
]


class DocumentData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    var: dict[str, JsonValue] = Field(default_factory=dict)
    step: dict[str, JsonValue] = Field(default_factory=dict)
    check: dict[str, JsonValue] = Field(default_factory=dict)
    quiz: dict[str, JsonValue] = Field(default_factory=dict)


class DocumentCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    checked: bool
    annotation: str = Field(default="", max_length=200_000)


class DocumentStep(DocumentCheck):
    elapsed_ms: float = Field(default=0, ge=0, allow_inf_nan=False)
    timer_started_at_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    started_at_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    ended_at_ms: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class DocumentContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=512)
    kind: DocumentKind = "document"
    body: str = Field(default="", max_length=200_000)
    body_format: Literal["md", "aimd"] | None = None
    record_data: DocumentData = Field(default_factory=DocumentData)
    file_ids: list[UUID] = Field(default_factory=list, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=50)
    collection: str = Field(default="", max_length=255)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def bounded(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("Document title is required")
        if len(set(self.file_ids)) != len(self.file_ids):
            raise ValueError("Duplicate attachment IDs")
        self.tags = list(dict.fromkeys(tag.strip() for tag in self.tags if tag.strip()))
        if any(len(tag) > 100 for tag in self.tags):
            raise ValueError("Tags must be at most 100 characters")
        if len(json.dumps(self.record_data.model_dump(), allow_nan=False)) > 1_000_000:
            raise ValueError("Document values exceed the size limit")
        if self.body_format == "md" and any(self.record_data.model_dump().values()):
            raise ValueError("Structured field values require AIMD format")
        if self.occurred_at is not None and self.occurred_at.tzinfo is None:
            raise ValueError("Occurrence time requires a timezone")
        return self


def _annotation(node: ast.AST, depth=0):
    if depth > 8:
        raise ValueError("Type expression is too deeply nested")
    if isinstance(node, ast.Name):
        types = {
            "str": str,
            "int": int,
            "float": float,
            "bool": bool,
            "date": date,
            "datetime": datetime,
        }
        if node.id in types:
            return types[node.id]
    if isinstance(node, ast.Constant) and node.value is None:
        return type(None)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _annotation(node.left, depth + 1) | _annotation(node.right, depth + 1)
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        name = node.value.id
        if name == "Literal":
            values = ast.literal_eval(node.slice)
            values = values if isinstance(values, tuple) else (values,)
            if (
                not values
                or len(values) > 100
                or any(
                    type(v) not in (str, int, bool, float, type(None)) for v in values
                )
            ):
                raise ValueError("Literal must contain scalar choices")
            return Literal[values]
        if name == "list":
            return list[_annotation(node.slice, depth + 1)]
        if name == "Optional":
            return _annotation(node.slice, depth + 1) | None
    raise ValueError(
        "This field type needs a Protocol runtime; use a declarative type for this document"
    )


def _model(nodes, name="DocumentValues", depth=0):
    if depth > 4 or len(nodes) > 200:
        raise ValueError("Too many or deeply nested fields")
    fields = {}
    for node in nodes:
        key = node["name"]
        if key in fields:
            raise ValueError(f"Duplicate field: {key}")
        subvars = node.get("subvars")
        if subvars is not None:
            typ = list[_model(subvars, f"{name}_{key}", depth + 1)]
        else:
            annotation = node.get("type_annotation") or "str"
            if len(annotation) > 1000:
                raise ValueError(f"Field {key}: type expression is too long")
            typ = _annotation(ast.parse(annotation, mode="eval").body)
        kwargs = dict(node.get("kwargs") or {})
        allowed = {
            "title",
            "description",
            "ge",
            "le",
            "gt",
            "lt",
            "min_length",
            "max_length",
            "multiple_of",
            "pattern",
            "unit",
            "default",
        }
        unknown = set(kwargs) - allowed
        if unknown:
            raise ValueError(
                f"Field {key}: unsupported constraints: {', '.join(sorted(unknown))}"
            )
        unit = kwargs.pop("unit", None)
        default = kwargs.pop("default", node.get("default_value", ...))
        if unit is not None:
            kwargs["json_schema_extra"] = {"unit": str(unit)}
        fields[key] = (typ, Field(default=default, **kwargs))
    return create_model(
        name, __config__=ConfigDict(extra="forbid", allow_inf_nan=False), **fields
    )


def document_schema(body: str) -> tuple[dict, dict]:
    diagnostics = validate_aimd(body)
    # SDK releases return a boolean tuple or raise for invalid syntax; parse_aimd
    # remains the source of the field definitions (not a second regex parser).
    if isinstance(diagnostics, tuple) and diagnostics and diagnostics[0] is False:
        raise ValueError(str(diagnostics[1]))
    templates = parse_aimd(body)["templates"]
    if any(
        templates.get(kind)
        for kind in ("assigner", "collectors", "connectors", "workflow")
    ):
        raise ValueError(
            "Executable/connected blocks require a Protocol; they are not executed by research documents"
        )
    return _model(templates.get("var", [])).model_json_schema(), templates


def definition_signature(body: str) -> str:
    try:
        schema, templates = document_schema(body)

        # Labels/prose may change without reinterpreting saved values.
        def semantic(value):
            if isinstance(value, dict):
                return {
                    k: (
                        {name: semantic(field) for name, field in v.items()}
                        if k in {"properties", "$defs"}
                        else semantic(v)
                    )
                    for k, v in value.items()
                    if k
                    not in {
                        "title",
                        "description",
                        "start_line",
                        "end_line",
                        "start_col",
                        "end_col",
                    }
                }
            return [semantic(v) for v in value] if isinstance(value, list) else value

        return canonical_digest(
            {
                "schema": semantic(schema),
                "step": semantic(templates.get("step")),
                "check": semantic(templates.get("check")),
                "quiz": semantic(templates.get("quiz")),
            }
        )
    except (ValueError, TypeError, SyntaxError, KeyError, RuntimeError):
        return canonical_digest({"unresolved_source": body})


def validate_document(body: str, data: dict) -> dict[str, Any]:
    errors = []
    try:
        schema, templates = document_schema(body)
    except (ValueError, TypeError, SyntaxError, KeyError, RuntimeError) as error:
        return {
            "valid": False,
            "schema": None,
            "errors": [{"field": "body", "message": str(error)[:2000]}],
        }
    variables = data.get("var", {})
    for error in Draft202012Validator(
        schema, format_checker=FormatChecker()
    ).iter_errors(variables):
        path = ".".join(map(str, error.absolute_path))
        errors.append(
            {"field": f"var.{path}" if path else "var", "message": error.message[:1000]}
        )
        if len(errors) >= 100:
            break
    for scope in ("step", "check"):
        names = {node["name"] for node in templates.get(scope, [])}
        for key, value in data.get(scope, {}).items():
            if key not in names:
                errors.append(
                    {
                        "field": f"{scope}.{key}",
                        "message": "Unknown field in this definition",
                    }
                )
            else:
                try:
                    (DocumentStep if scope == "step" else DocumentCheck).model_validate(
                        value
                    )
                except ValidationError:
                    errors.append(
                        {
                            "field": f"{scope}.{key}",
                            "message": "Expected a boolean checked state, text annotation and valid nonnegative timer values",
                        }
                    )
        if scope == "check":
            for key in names - set(data.get(scope, {})):
                errors.append(
                    {
                        "field": f"check.{key}",
                        "message": "Checkpoint response is required",
                    }
                )
    valid_quiz, quiz_errors = validate_record_quiz_answers_with_aimd(
        {"data": {**data, "quiz": data.get("quiz", {})}}, body
    )
    if not valid_quiz:
        errors.extend(
            {"field": "quiz", "message": str(error)[:1000]} for error in quiz_errors
        )
    return {
        "valid": not errors,
        "schema": schema,
        "errors": errors[:100],
        "definition_digest": definition_signature(body),
    }


def document_change_impact(previous: dict, proposed: DocumentContent) -> dict:
    next_data = proposed.record_data.model_dump(mode="json")
    old_data = previous.get("record_data") or {}
    old_format = previous.get("body_format", "aimd")
    old_body = "" if old_format == "md" else previous.get("body", "")
    new_body = "" if (proposed.body_format or old_format) == "md" else proposed.body
    changed_definition = definition_signature(old_body) != definition_signature(new_body)
    field_changes = []
    if changed_definition:
        try:
            old_fields = document_schema(old_body)[0].get(
                "properties", {}
            )
            new_fields = document_schema(new_body)[0].get("properties", {})
            for key in sorted(set(old_fields) | set(new_fields)):
                before, after = old_fields.get(key), new_fields.get(key)
                if before != after:
                    field_changes.append(
                        {"field": key, "before": before, "after": after}
                    )
        except (ValueError, TypeError, SyntaxError, KeyError, RuntimeError):
            field_changes = []  # Invalid source remains revisioned and cannot be submitted.
    existing_values = any(bool(values) for values in old_data.values())
    removed_values = [
        f"{scope}.{key}"
        for scope, values in old_data.items()
        if isinstance(values, dict)
        for key in values
        if key not in next_data.get(scope, {})
    ]
    return {
        "field_changes": field_changes,
        "definition_changed": changed_definition,
        "existing_values": existing_values,
        "removed_values": removed_values,
        "requires_confirmation": bool(
            removed_values or (changed_definition and existing_values)
        ),
    }
