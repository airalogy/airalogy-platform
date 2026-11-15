"""Built-in and member-shared document starters; permissions enforced on every use."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, or_, select

from app.database import DBSession
from app.models.document_template import DocumentTemplate, DocumentTemplateRevision
from app.models.lab import Lab, LabUser
from app.models.project import Project
from app.models.research_log import ResearchLogScope
from app.models.user import User
from app.routers.depends import CurrentUser
from app.routers.research_log import _scope_conditions, _scope_context
from app.services.document_templates import (
    builtin_templates,
    template_context,
    template_defaults,
)
from app.services.knowledge import canonical_digest
from app.services.research_documents import DocumentKind

router = APIRouter(prefix="/document-templates", tags=["document-templates"])


class TemplateContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=2000)
    kind: DocumentKind = "document"
    body: str = Field(default="", max_length=200_000)

    @model_validator(mode="after")
    def normalize(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("Template title is required")
        return self


class TemplateCreate(TemplateContent):
    id: UUID = Field(default_factory=uuid4)
    scope_type: ResearchLogScope
    lab_id: UUID | None = None
    project_id: UUID | None = None
    source_template_id: UUID | None = None
    source_template_revision: int | None = Field(default=None, ge=1)
    source_document_id: UUID | None = None
    source_revision: int | None = Field(default=None, ge=1)
    preview_digest: str | None = None


class TemplateUpdate(TemplateContent):
    expected_revision: int = Field(ge=1)
    preview_digest: str | None = None


class ArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    archived: bool


def content(item):
    return {key: getattr(item, key) for key in TemplateContent.model_fields}


def revision(db, item, user):
    db.add(
        DocumentTemplateRevision(
            template_id=item.id,
            revision=item.revision,
            snapshot={**content(item), "archived": item.archived_at is not None},
            created_by_user_id=user.id,
        )
    )


async def payload(db, user, item):
    can_edit = False
    try:
        await template_context(
            db, user, item.id, write=True, allow_archived=True, lock=False
        )
        can_edit = True
    except HTTPException:
        pass
    return {
        **content(item),
        "id": str(item.id),
        "revision": item.revision,
        "scope_type": item.scope_type,
        "lab_id": item.lab_id,
        "project_id": item.project_id,
        "can_edit": can_edit,
        "builtin": False,
        "archived": item.archived_at is not None,
        "updated_at": item.updated_at,
    }


def scope_payload(scope):
    return {
        "scope_type": scope.scope_type.value,
        "lab_id": str(scope.lab_id) if scope.lab_id else None,
        "project_id": str(scope.project_id) if scope.project_id else None,
        "name": " / ".join(x.name for x in (scope.lab, scope.project) if x),
    }


@router.get("/scopes")
async def available_scopes(current_user: CurrentUser, db_session: DBSession):
    # Query only Labs this user belongs to; re-evaluate explicit Project access.
    labs = list(
        (
            await db_session.scalars(
                select(Lab)
                .join(LabUser, LabUser.lab_id == Lab.id)
                .where(LabUser.user_id == current_user.id)
                .order_by(Lab.name)
            )
        ).all()
    )
    candidates = [(ResearchLogScope.PERSONAL, None, None)]
    candidates += [(ResearchLogScope.LAB, lab.id, None) for lab in labs]
    projects = (
        (
            await db_session.scalars(
                select(Project)
                .where(
                    Project.lab_id.in_([lab.id for lab in labs]),
                    Project.deleted_at.is_(None),
                )
                .order_by(Project.name)
            )
        ).all()
        if labs
        else []
    )
    candidates += [(ResearchLogScope.PROJECT, p.lab_id, p.id) for p in projects]
    items = []
    for kind, lab_id, project_id in candidates:
        try:
            scope = await _scope_context(
                db_session,
                current_user,
                scope_type=kind,
                lab_id=lab_id,
                project_id=project_id,
                capability="log.read",
            )
        except HTTPException:
            continue
        can_write = True
        try:
            await _scope_context(
                db_session,
                current_user,
                scope_type=kind,
                lab_id=lab_id,
                project_id=project_id,
                capability="log.write",
            )
        except HTTPException:
            can_write = False
        items.append({**scope_payload(scope), "can_write": can_write})
    return {"items": items}


@router.get("/builtins")
async def builtins(
    current_user: CurrentUser, locale: str = Query(default="en-US", max_length=16)
):
    return {"items": builtin_templates(locale)}


@router.get("")
async def list_templates(
    current_user: CurrentUser,
    db_session: DBSession,
    scope_type: ResearchLogScope,
    lab_id: UUID | None = None,
    project_id: UUID | None = None,
    q: str = Query(default="", max_length=200),
    archived: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    scope = await _scope_context(
        db_session,
        current_user,
        scope_type=scope_type,
        lab_id=lab_id,
        project_id=project_id,
        capability="log.read",
    )
    filters = [
        *_scope_conditions(DocumentTemplate, scope),
        DocumentTemplate.archived_at.is_not(None)
        if archived
        else DocumentTemplate.archived_at.is_(None),
    ]
    if q:
        filters.append(
            or_(
                DocumentTemplate.title.ilike(f"%{q}%"),
                DocumentTemplate.description.ilike(f"%{q}%"),
            )
        )
    total = await db_session.scalar(
        select(func.count()).select_from(DocumentTemplate).where(*filters)
    )
    items = (
        await db_session.scalars(
            select(DocumentTemplate)
            .where(*filters)
            .order_by(DocumentTemplate.updated_at.desc(), DocumentTemplate.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    can_write = True
    try:
        await _scope_context(
            db_session,
            current_user,
            scope_type=scope_type,
            lab_id=lab_id,
            project_id=project_id,
            capability="log.write",
        )
    except HTTPException:
        can_write = False
    return {
        "items": [await payload(db_session, current_user, item) for item in items],
        "total_count": total or 0,
        "can_write": can_write,
    }


@router.post("")
async def create_template(
    params: TemplateCreate, current_user: CurrentUser, db_session: DBSession
):
    scope = await _scope_context(
        db_session,
        current_user,
        scope_type=params.scope_type,
        lab_id=params.lab_id,
        project_id=params.project_id,
        capability="log.write",
    )
    await db_session.scalar(
        select(User.id).where(User.id == current_user.id).with_for_update()
    )
    request_digest = canonical_digest(
        params.model_dump(mode="json", exclude={"preview_digest"})
    )
    existing = await db_session.get(DocumentTemplate, params.id)
    if existing:
        if (
            existing.created_by_user_id != current_user.id
            or existing.create_digest != request_digest
        ):
            raise HTTPException(409, "Template creation key already used")
        return await payload(db_session, current_user, existing)
    source = {}
    if params.source_document_id and params.source_template_id:
        raise HTTPException(422, "Choose one template source")
    if params.source_template_id:
        original, _ = await template_context(
            db_session, current_user, params.source_template_id
        )
        if original.revision != params.source_template_revision:
            raise HTTPException(
                409, "Source template changed. Review the current content."
            )
        source = {"template_id": str(original.id), "revision": original.revision}
    elif params.source_template_revision is not None:
        raise HTTPException(422, "Source revision requires a template")
    if params.source_document_id:
        from app.routers.research_documents import _context

        entry, _ = await _context(db_session, current_user, params.source_document_id)
        from app.services.meetings import require_shareable_meeting_source

        await require_shareable_meeting_source(db_session, entry)
        if params.source_revision != entry.revision:
            raise HTTPException(
                409, "Source document changed. Review the current content."
            )
        source = {"document_id": str(entry.id), "revision": entry.revision}
    elif params.source_revision is not None:
        raise HTTPException(422, "Source revision requires a document")
    defaults = template_defaults(params.body)
    snapshot = {
        "content": params.model_dump(include=set(TemplateContent.model_fields)),
        "destination": scope_payload(scope),
        "defaults": defaults,
    }
    digest = canonical_digest(
        {
            "operation": "create_template",
            "actor": str(current_user.id),
            "request": request_digest,
            "source": source,
            "snapshot": snapshot,
        }
    )
    if not params.preview_digest:
        return {
            "requires_confirmation": True,
            "preview_digest": digest,
            "snapshot": snapshot,
        }
    if params.preview_digest != digest:
        raise HTTPException(
            409, "Template preview changed. Preview again before saving."
        )
    item = DocumentTemplate(
        id=params.id,
        **scope.model_values(),
        **content(params),
        revision=1,
        source=source,
        create_digest=request_digest,
        created_by_user_id=current_user.id,
    )
    db_session.add(item)
    await db_session.flush()
    revision(db_session, item, current_user)
    await db_session.commit()
    return await payload(db_session, current_user, item)


@router.get("/{template_id}")
async def get_template(
    template_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    item, _ = await template_context(
        db_session, current_user, template_id, allow_archived=True
    )
    return await payload(db_session, current_user, item)


@router.put("/{template_id}")
async def update_template(
    template_id: UUID,
    params: TemplateUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    item, scope = await template_context(
        db_session, current_user, template_id, write=True
    )
    if params.expected_revision != item.revision:
        raise HTTPException(409, "Template changed. Reload before editing.")
    defaults = template_defaults(params.body)
    snapshot = {
        "content": content(params),
        "destination": scope_payload(scope),
        "defaults": defaults,
    }
    digest = canonical_digest(
        {
            "operation": "update_template",
            "actor": str(current_user.id),
            "id": str(item.id),
            "revision": item.revision,
            "snapshot": snapshot,
        }
    )
    if not params.preview_digest:
        return {
            "requires_confirmation": True,
            "preview_digest": digest,
            "snapshot": snapshot,
        }
    if digest != params.preview_digest:
        raise HTTPException(
            409, "Template preview changed. Preview again before saving."
        )
    for key, value in content(params).items():
        setattr(item, key, value)
    item.revision += 1
    item.updated_at = datetime.now(UTC)
    revision(db_session, item, current_user)
    await db_session.commit()
    return await payload(db_session, current_user, item)


@router.post("/{template_id}/archive")
async def archive_template(
    template_id: UUID,
    params: ArchiveRequest,
    current_user: CurrentUser,
    db_session: DBSession,
):
    item, _ = await template_context(
        db_session, current_user, template_id, write=True, allow_archived=True
    )
    if item.revision != params.expected_revision:
        raise HTTPException(409, "Template changed. Reload before editing.")
    item.archived_at = datetime.now(UTC) if params.archived else None
    item.updated_at = datetime.now(UTC)
    item.revision += 1
    revision(db_session, item, current_user)
    await db_session.commit()
    return await payload(db_session, current_user, item)


@router.get("/{template_id}/revisions")
async def template_history(
    template_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    await template_context(db_session, current_user, template_id, allow_archived=True)
    rows = (
        await db_session.scalars(
            select(DocumentTemplateRevision)
            .where(DocumentTemplateRevision.template_id == template_id)
            .order_by(DocumentTemplateRevision.revision.desc())
        )
    ).all()
    return {
        "items": [
            {"revision": r.revision, "snapshot": r.snapshot, "created_at": r.created_at}
            for r in rows
        ]
    }
