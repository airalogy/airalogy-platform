"""Template definitions and access checks; no measured state or executable code."""

from copy import deepcopy
from uuid import UUID

from fastapi import HTTPException
from jsonschema import Draft202012Validator, FormatChecker
from sqlalchemy import select

from app.models.document_template import DocumentTemplate
from app.models.lab import LabRole, LabUser
from app.models.research_log import ResearchLogScope
from app.routers.research_log import _scope_context
from app.services.research_documents import document_schema

BUILTINS = {
    "blank": (
        "document",
        "空白文档",
        "Blank document",
        "从空白开始，自由组织研究内容。",
        "Start with a blank page.",
        "",
        "",
    ),
    "experiment": (
        "experiment",
        "实验记录",
        "Experiment note",
        "记录方案、实际操作和偏差。",
        "Plan, observations and deviations.",
        "## 方案与计划参数\n\n<!-- 写明实验目标和计划；需要时添加字段。 -->\n\n## 实际操作与观察\n\n## 方案偏差及原因\n\n## 结果与下一步\n",
        "## Plan and parameters\n\n<!-- Describe the goal and plan; add fields as needed. -->\n\n## Procedure and observations\n\n## Deviations and reasons\n\n## Results and next steps\n",
    ),
    "meeting": (
        "meeting",
        "会议记录",
        "Meeting note",
        "记录议题、讨论、决策和下一步。",
        "Agenda, discussion, decisions and next steps.",
        "## 会议主题与参与者\n\n## 议题与讨论\n\n## 决策及依据\n\n## 下一步与负责人\n",
        "## Topic and participants\n\n## Agenda and discussion\n\n## Decisions and rationale\n\n## Next steps and owners\n",
    ),
    "progress": (
        "progress",
        "研究进展",
        "Research progress",
        "整理目标、进展、阻塞和下一步。",
        "Goals, progress, blockers and next steps.",
        "## 当前目标\n\n## 已完成事项与证据\n\n## 风险与阻塞\n\n## 下一步\n",
        "## Current goal\n\n## Progress and evidence\n\n## Risks and blockers\n\n## Next steps\n",
    ),
}


def builtin_templates(locale="en-US"):
    zh = locale.lower().startswith("zh")
    return [
        {
            "id": f"builtin:{key}",
            "title": row[1 if zh else 2],
            "description": row[3 if zh else 4],
            "kind": row[0],
            "body": row[5 if zh else 6],
            "revision": 1,
            "builtin": True,
            "can_edit": False,
            "archived": False,
            "scope_type": "builtin",
        }
        for key, row in BUILTINS.items()
    ]


def template_defaults(body):
    """Validate definitions and explicitly authored defaults, not required answers."""
    try:
        schema, _ = document_schema(body)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())

        def validate_defaults(node):
            if isinstance(node, dict):
                if "default" in node:
                    validator.evolve(schema=node).validate(node["default"])
                for child in node.values():
                    validate_defaults(child)
            elif isinstance(node, list):
                for child in node:
                    validate_defaults(child)

        validate_defaults(schema)
        return {
            "var": {
                key: deepcopy(value["default"])
                for key, value in schema.get("properties", {}).items()
                if "default" in value
            }
        }
    except Exception as exc:
        # Parser and schema diagnostics are bounded, never execute user definitions.
        raise HTTPException(
            422, {"code": "invalid_template", "message": str(exc)[:2000]}
        ) from exc


async def template_context(
    db, user, template_id, *, write=False, allow_archived=False, lock=True
):
    query = select(DocumentTemplate).where(DocumentTemplate.id == template_id)
    if write and lock:
        query = query.with_for_update()
    item = await db.scalar(query.execution_options(populate_existing=True))
    if not item or (item.archived_at and not allow_archived):
        raise HTTPException(404, "Document template not found")
    if item.scope_type == "personal" and item.owner_user_id != user.id:
        raise HTTPException(404, "Document template not found")
    scope = await _scope_context(
        db,
        user,
        scope_type=ResearchLogScope(item.scope_type),
        lab_id=item.lab_id,
        project_id=item.project_id,
        capability="log.write" if write else "log.read",
    )
    if write and item.created_by_user_id != user.id:
        membership = (
            await db.scalar(
                select(LabUser).where(
                    LabUser.lab_id == item.lab_id, LabUser.user_id == user.id
                )
            )
            if item.lab_id
            else None
        )
        from app.services.access_control import resolve_structured_access

        decision = (
            await resolve_structured_access(
                db, user.id, item.lab_id, scope.project, include_legacy=True
            )
            if scope.project
            else None
        )
        if not (membership and membership.role <= LabRole.MANAGER) and not (
            decision and decision.allows("access.manage")
        ):
            raise HTTPException(
                403, "Only the author or scope managers can manage this template"
            )
    return item, scope


async def resolve_template(db, user, template_id, revision, locale):
    if template_id.startswith("builtin:"):
        item = next(
            (x for x in builtin_templates(locale) if x["id"] == template_id), None
        )
        if item is None:
            raise HTTPException(404, "Document template not found")
    else:
        try:
            identity = UUID(template_id)
        except ValueError:
            raise HTTPException(422, "Invalid template ID")
        source, _ = await template_context(db, user, identity)
        item = {
            key: getattr(source, key)
            for key in ("id", "title", "body", "kind", "revision")
        }
    if revision != item["revision"]:
        raise HTTPException(
            409,
            "Template changed. Preview the current version before creating a document.",
        )
    return item, template_defaults(item["body"])
