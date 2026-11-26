"""Project notebooks without a mandatory Protocol or Research Task."""

import asyncio
import hashlib
import io
import json
import zipfile
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Date, cast, func, or_, select

from app.config import config
from app.database import DBSession
from app.libs.file_storage import get_file_content
from app.models.knowledge import (
    KnowledgeItem,
    KnowledgeRevision,
    OwnerScope,
    ResearchFile,
    ResearchFileAccessAudit,
    ResearchFileBlob,
)
from app.models.lab import Lab
from app.models.meeting import Meeting
from app.models.project import Project
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolVersion
from app.models.research_document import (
    ResearchDocument,
    ResearchDocumentDerivation,
    ResearchDocumentSubmission,
)
from app.models.research_log import (
    ResearchLogEntry,
    ResearchLogRevision,
    ResearchLogScope,
)
from app.models.user import User
from app.routers.depends import CurrentUser
from app.routers.permission import check_user_permission
from app.routers.research_log import _scope_conditions, _scope_context, _snapshot
from app.routers.research_materials import (
    cleanup_material_uploads,
    material_content_type,
    persist_material,
)
from app.services.browser_paths import project_browser_path
from app.services.document_browse import date_bounds
from app.services.knowledge import (
    assert_research_file_upload_quota,
    authorize_research_file,
    canonical_digest,
    resolve_scope,
    snapshot_knowledge,
)
from app.services.meetings import (
    authorize_meeting,
    meeting_read_condition,
    require_shareable_meeting_source,
)
from app.services.research_document_archive import (
    ARCHIVE_MAX_BYTES,
    read_document_archive,
)
from app.services.research_documents import (
    DOCUMENT_FORMAT,
    DocumentContent,
    document_change_impact,
    validate_document,
)

router = APIRouter(prefix="/research-documents", tags=["research-documents"])


class DocumentCreate(DocumentContent):
    id: UUID = Field(default_factory=uuid4)
    scope_type: ResearchLogScope
    lab_id: UUID | None = None
    project_id: UUID | None = None
    source_document_id: UUID | None = None
    source_protocol_version_id: UUID | None = None
    source_template_id: str | None = Field(default=None, max_length=64)
    source_template_revision: int | None = Field(default=None, ge=1)
    template_locale: str = Field(default="en-US", max_length=16)


class DocumentUpdate(DocumentContent):
    expected_revision: int = Field(ge=1)
    preview_digest: str | None = Field(default=None, min_length=64, max_length=64)
    change_summary: str = Field(default="Edited", min_length=1, max_length=4000)


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    preview_digest: str | None = Field(default=None, min_length=64, max_length=64)


class DeriveRequest(RevisionRequest):
    kind: Literal["knowledge", "protocol"]
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1, max_length=200_000)


async def _context(db, user, document_id, *, write=False):
    query = select(ResearchLogEntry).where(ResearchLogEntry.id == document_id)
    if write:
        query = query.with_for_update()
    entry = await db.scalar(query.execution_options(populate_existing=True))
    doc = await db.get(ResearchDocument, document_id, populate_existing=True)
    if entry is None or doc is None or entry.archived_at is not None:
        raise HTTPException(404, "Research document not found")
    if entry.scope_type == "personal" and entry.owner_user_id != user.id:
        raise HTTPException(404, "Research document not found")
    await _scope_context(
        db,
        user,
        scope_type=ResearchLogScope(entry.scope_type),
        lab_id=entry.lab_id,
        project_id=entry.project_id,
        capability="log.write" if write else "log.read",
    )
    meeting = await authorize_meeting(db, user, entry, "edit" if write else "read")
    if write and meeting is not None:
        raise HTTPException(
            409,
            "Use the meeting page to preserve attendance, audience and meeting history",
        )
    if write and entry.created_by_user_id != user.id:
        raise HTTPException(403, "Only the author can revise this document")
    return entry, doc


def _document_snapshot(entry, doc):
    return {
        **_snapshot(entry),
        "document": {
            "format": DOCUMENT_FORMAT,
            "format_version": doc.format_version,
            "state": doc.state,
            "record_data": deepcopy(doc.record_data),
            "file_ids": list(doc.file_ids),
            "tags": list(doc.tags),
            "collection": doc.collection,
            "origin": deepcopy(doc.origin),
        },
    }


def _content(entry, doc):
    return {
        "title": entry.title,
        "kind": entry.kind,
        "body": entry.body,
        "body_format": "md" if doc.format_version == "md.v1" else "aimd",
        "record_data": doc.record_data,
        "file_ids": doc.file_ids,
        "tags": doc.tags,
        "collection": doc.collection,
        "occurred_at": entry.occurred_at.isoformat(),
    }


async def _files(db, user, entry, ids):
    manifests = []
    for raw_id in ids:
        file = await db.get(ResearchFile, UUID(str(raw_id)))
        if file is None or file.archived_at is not None:
            raise HTTPException(404, "Document attachment is unavailable")
        await authorize_research_file(db, user, file)
        # A reference must not disclose a private/restricted file to the wider
        # document audience. Cross-scope sharing is a separate explicit action.
        if (
            file.scope_type != entry.scope_type
            or file.owner_user_id != entry.owner_user_id
            or file.lab_id != entry.lab_id
            or file.project_id != entry.project_id
            or file.visibility == "restricted"
        ):
            raise HTTPException(
                403, "Attachments must belong to this document's scope and audience"
            )
        blob = await db.get(ResearchFileBlob, file.blob_id)
        if blob is None:
            raise HTTPException(404, "Document attachment content is unavailable")
        manifests.append(
            {
                "id": str(file.id),
                "filename": file.filename,
                "sha256": blob.checksum_sha256,
                "size_bytes": blob.size_bytes,
                "content_type": blob.content_type,
            }
        )
    return manifests


async def _payload(db, user, entry, doc):
    can_edit = False
    meeting = await db.get(Meeting, entry.id)
    if entry.created_by_user_id == user.id or meeting:
        try:
            await _scope_context(
                db,
                user,
                scope_type=ResearchLogScope(entry.scope_type),
                lab_id=entry.lab_id,
                project_id=entry.project_id,
                capability="log.write",
            )
            await authorize_meeting(db, user, entry, "edit")
            can_edit = True
        except HTTPException:
            pass
    files = []
    for file_id in doc.file_ids:
        try:
            files.extend(await _files(db, user, entry, [file_id]))
        except HTTPException:
            files.append({"id": str(file_id), "unavailable": True})
    lab = await db.get(Lab, entry.lab_id) if entry.lab_id else None
    project = await db.get(Project, entry.project_id) if entry.project_id else None
    scope_name = (
        " / ".join(item.name for item in (lab, project) if item)
        or user.name
        or user.username
    )
    return {
        "scope_name": scope_name,
        "meeting_id": str(entry.id) if meeting else None,
        "meeting_url": f"{project_browser_path(lab.uid, project.uid)}/meetings?meeting={entry.id}"
        if meeting and lab and project
        else None,
        **_content(entry, doc),
        "id": str(entry.id),
        "revision": entry.revision,
        "state": doc.state,
        "format": DOCUMENT_FORMAT,
        "origin": doc.origin,
        "can_edit": can_edit and not meeting,
        "scope_type": entry.scope_type,
        "lab_id": entry.lab_id,
        "project_id": entry.project_id,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "files": files,
    }


def _assert_revision(entry, expected):
    if entry.revision != expected:
        raise HTTPException(
            409, "Document changed. Reload and compare your changes before saving."
        )


def _save_revision(db, entry, doc, user, summary):
    db.add(
        ResearchLogRevision(
            log_entry_id=entry.id,
            revision=entry.revision,
            snapshot=_document_snapshot(entry, doc),
            change_summary=summary,
            created_by_user_id=user.id,
        )
    )


def browse_query(scope, q, kind, date_from, date_to, time_zone, user_id=None):
    start, end = date_bounds(date_from, date_to, time_zone)
    filters = [
        *_scope_conditions(ResearchLogEntry, scope),
        ResearchLogEntry.archived_at.is_(None),
    ]
    if user_id is not None:
        filters.append(meeting_read_condition(user_id))
    q = q.strip()
    if scope.project and not q and kind != "meeting":
        filters.append(
            ~select(Meeting.document_id)
            .where(Meeting.document_id == ResearchLogEntry.id)
            .exists()
        )
    if q:
        filters.append(
            or_(
                ResearchLogEntry.title.ilike(f"%{q}%"),
                ResearchLogEntry.body.ilike(f"%{q}%"),
            )
        )
    if kind:
        filters.append(ResearchLogEntry.kind == kind)
    if start:
        filters.append(ResearchLogEntry.occurred_at >= start)
    if end:
        filters.append(ResearchLogEntry.occurred_at < end)
    return (
        select(ResearchLogEntry, ResearchDocument)
        .join(ResearchDocument, ResearchDocument.id == ResearchLogEntry.id)
        .where(*filters)
    )


@router.get("/calendar")
async def document_calendar(
    current_user: CurrentUser,
    db_session: DBSession,
    scope_type: ResearchLogScope,
    month: date,
    lab_id: UUID | None = None,
    project_id: UUID | None = None,
    q: str = Query(default="", max_length=200),
    kind: str = Query(default="", max_length=32),
    time_zone: str = Query(default="UTC", max_length=64),
):
    scope = await _scope_context(
        db_session,
        current_user,
        scope_type=scope_type,
        lab_id=lab_id,
        project_id=project_id,
        capability="log.read",
    )
    first = month.replace(day=1)
    if first.year == 9999 and first.month == 12:
        raise HTTPException(422, "Month is outside the supported range")
    next_month = date(first.year + first.month // 12, first.month % 12 + 1, 1)
    source = browse_query(
        scope,
        q,
        kind,
        first,
        next_month - timedelta(days=1),
        time_zone,
        current_user.id,
    ).subquery()
    day = cast(func.timezone(time_zone, source.c.occurred_at), Date)
    rows = (
        await db_session.execute(
            select(day.label("day"), func.count().label("count"))
            .group_by(day)
            .order_by(day)
        )
    ).all()
    return {"days": [{"date": row.day.isoformat(), "count": row.count} for row in rows]}


@router.get("")
async def list_documents(
    current_user: CurrentUser,
    db_session: DBSession,
    scope_type: ResearchLogScope,
    lab_id: UUID | None = None,
    project_id: UUID | None = None,
    q: str = Query(default="", max_length=200),
    kind: str = Query(default="", max_length=32),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    order: Literal["updated", "recorded"] = "updated",
    date_from: date | None = None,
    date_to: date | None = None,
    time_zone: str = Query(default="UTC", max_length=64),
):
    scope = await _scope_context(
        db_session,
        current_user,
        scope_type=scope_type,
        lab_id=lab_id,
        project_id=project_id,
        capability="log.read",
    )
    query = browse_query(scope, q, kind, date_from, date_to, time_zone, current_user.id)
    total = await db_session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db_session.execute(
            query.order_by(
                (
                    ResearchLogEntry.occurred_at
                    if order == "recorded"
                    else ResearchLogEntry.updated_at
                ).desc(),
                ResearchLogEntry.id.desc(),
            )
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
    items = []
    meeting_statuses = dict(
        (
            await db_session.execute(
                select(Meeting.document_id, Meeting.status).where(
                    Meeting.document_id.in_([entry.id for entry, _ in rows])
                )
            )
        ).all()
    )
    meeting_path = (
        project_browser_path(scope.lab.uid, scope.project.uid) + "/meetings"
        if scope.project and meeting_statuses
        else None
    )
    for entry, doc in rows:
        items.append(
            {
                "id": str(entry.id),
                "title": entry.title,
                "kind": entry.kind,
                "state": doc.state,
                "meeting_status": meeting_statuses.get(entry.id),
                "meeting_url": f"{meeting_path}?meeting={entry.id}"
                if entry.id in meeting_statuses
                else None,
                "revision": entry.revision,
                "tags": doc.tags,
                "collection": doc.collection,
                "updated_at": entry.updated_at,
                "occurred_at": entry.occurred_at,
                "excerpt": entry.body[:240],
            }
        )
    # A project containing only meetings still needs a usable document search.
    has_searchable_items = bool(total)
    if not total and scope.project and not (q.strip() or kind or date_from or date_to):
        visible_meetings = browse_query(
            scope, "", "meeting", None, None, time_zone, current_user.id
        )
        has_searchable_items = bool(
            await db_session.scalar(select(visible_meetings.exists()))
        )
    return {
        "items": items,
        "total_count": total,
        "has_searchable_items": has_searchable_items,
        "can_write": can_write,
    }


@router.get("/recent")
async def recent_documents(
    current_user: CurrentUser,
    db_session: DBSession,
    scope_type: ResearchLogScope | None = None,
):
    rows = (
        await db_session.execute(
            select(ResearchLogEntry, ResearchDocument)
            .join(ResearchDocument, ResearchDocument.id == ResearchLogEntry.id)
            .where(
                ResearchLogEntry.created_by_user_id == current_user.id,
                ResearchLogEntry.archived_at.is_(None),
                *([ResearchLogEntry.scope_type == scope_type] if scope_type else []),
            )
            .order_by(ResearchLogEntry.updated_at.desc())
            .limit(100)
        )
    ).all()
    items = []
    for entry, doc in rows:
        try:
            await _context(db_session, current_user, entry.id)
        except HTTPException:
            continue
        items.append(
            {
                "id": str(entry.id),
                "title": entry.title,
                "state": doc.state,
                "updated_at": entry.updated_at,
            }
        )
        if len(items) == 5:
            break
    return {"items": items}


@router.get("/protocol-sources")
async def protocol_sources(
    current_user: CurrentUser,
    db_session: DBSession,
    project_id: UUID,
    q: str = Query(default="", max_length=200),
):
    scope = await _scope_context(
        db_session,
        current_user,
        scope_type=ResearchLogScope.PROJECT,
        project_id=project_id,
        lab_id=None,
        capability="log.write",
    )
    query = select(Protocol, ProtocolVersion).join(
        ProtocolVersion,
        (ProtocolVersion.protocol_id == Protocol.id)
        & (ProtocolVersion.version == Protocol.latest_version),
    )
    query = query.where(
        Protocol.project_id == project_id, Protocol.deleted_at.is_(None)
    )
    if q:
        query = query.where(Protocol.name.ilike(f"%{q}%"))
    rows = (await db_session.execute(query.order_by(Protocol.name).limit(100))).all()
    items = []
    for protocol, version in rows:
        try:
            await check_user_permission(
                db_session,
                project=scope.project,
                user=current_user,
                action="read_protocol",
                protocol=protocol,
            )
        except HTTPException:
            continue
        items.append(
            {"id": str(version.id), "name": protocol.name, "version": version.version}
        )
    return {"items": items}


@router.post("")
async def create_document(
    params: DocumentCreate, current_user: CurrentUser, db_session: DBSession
):
    scope = await _scope_context(
        db_session,
        current_user,
        scope_type=params.scope_type,
        lab_id=params.lab_id,
        project_id=params.project_id,
        capability="log.write",
    )
    # Serializes retries by this author; the client keeps its creation UUID.
    await db_session.scalar(
        select(User.id).where(User.id == current_user.id).with_for_update()
    )
    existing = await db_session.get(ResearchDocument, params.id)
    if existing:
        entry, doc = await _context(db_session, current_user, params.id, write=True)
        if any(
            getattr(entry, key) != value for key, value in scope.model_values().items()
        ):
            raise HTTPException(409, "Creation key belongs to another scope")
        return await _payload(db_session, current_user, entry, doc)
    if await db_session.get(ResearchLogEntry, params.id):
        raise HTTPException(409, "Creation key already exists")
    origin = {}
    body = params.body
    if (
        sum(
            bool(x)
            for x in (
                params.source_document_id,
                params.source_protocol_version_id,
                params.source_template_id,
            )
        )
        > 1
    ):
        raise HTTPException(422, "Choose one source")
    defaults = {}
    kind = params.kind
    if params.source_template_revision is not None and not params.source_template_id:
        raise HTTPException(422, "Template revision requires a template")
    if params.source_template_id:
        from app.services.document_templates import resolve_template

        source, defaults = await resolve_template(
            db_session,
            current_user,
            params.source_template_id,
            params.source_template_revision,
            params.template_locale,
        )
        body, kind = source["body"], source["kind"]
        origin = {
            "kind": "template",
            "id": str(source["id"]),
            "revision": source["revision"],
            "digest": canonical_digest({"body": body, "defaults": defaults}),
        }
    if params.source_document_id:
        source, source_doc = await _context(
            db_session, current_user, params.source_document_id
        )
        if any(
            getattr(source, key) != value for key, value in scope.model_values().items()
        ):
            raise HTTPException(
                403,
                "Copy within the same scope; cross-scope publication requires a separate review",
            )
        await require_shareable_meeting_source(db_session, source)
        body = source.body
        origin = {
            "kind": "document",
            "id": str(source.id),
            "revision": source.revision,
            "digest": canonical_digest(_document_snapshot(source, source_doc)),
        }
    elif params.source_protocol_version_id:
        version = await db_session.get(
            ProtocolVersion, params.source_protocol_version_id
        )
        protocol = (
            await db_session.get(Protocol, version.protocol_id) if version else None
        )
        project = (
            await db_session.get(Project, protocol.project_id) if protocol else None
        )
        if (
            not protocol
            or protocol.deleted_at is not None
            or not project
            or project.deleted_at is not None
        ):
            raise HTTPException(404, "Source Protocol is unavailable")
        await check_user_permission(
            db_session,
            project=project,
            user=current_user,
            action="read_protocol",
            protocol=protocol,
        )
        if scope.project_id != project.id:
            raise HTTPException(
                403, "Start the experiment in the source Protocol's Project"
            )
        body = version.aimd
        origin = {
            "kind": "protocol",
            "id": str(protocol.id),
            "version_id": str(version.id),
            "version": version.version,
            "digest": canonical_digest({"aimd": body, "version_id": str(version.id)}),
        }
    entry = ResearchLogEntry(
        id=params.id,
        **scope.model_values(),
        kind=kind,
        title=params.title,
        body=body,
        goal="",
        completed_items=[],
        evidence=[],
        risks=[],
        next_steps=[],
        asset_links=[],
        occurred_at=params.occurred_at or datetime.now(UTC),
        created_by_user_id=current_user.id,
        revision=1,
    )
    # Copies never carry historical measured values or attachments implicitly.
    doc = ResearchDocument(
        id=entry.id,
        format_version=source_doc.format_version if params.source_document_id else ("md.v1" if params.body_format == "md" and not origin else "aimd.v1"),
        state="draft",
        record_data=defaults if origin else params.record_data.model_dump(mode="json"),
        file_ids=[] if origin else [str(x) for x in params.file_ids],
        tags=params.tags,
        collection=params.collection,
        origin=origin,
    )
    await _files(db_session, current_user, entry, doc.file_ids)
    db_session.add(entry)
    await db_session.flush()
    db_session.add(doc)
    _save_revision(db_session, entry, doc, current_user, "Created")
    await db_session.commit()
    return await _payload(db_session, current_user, entry, doc)


@router.post("/import")
async def import_document(
    current_user: CurrentUser,
    db_session: DBSession,
    file: Annotated[UploadFile, File()],
    scope_type: Annotated[ResearchLogScope, Form()],
    request_key: Annotated[UUID, Form()],
    lab_id: Annotated[UUID | None, Form()] = None,
    project_id: Annotated[UUID | None, Form()] = None,
    preview_digest: Annotated[str | None, Form()] = None,
):
    scope = await _scope_context(
        db_session,
        current_user,
        scope_type=scope_type,
        lab_id=lab_id,
        project_id=project_id,
        capability="log.write",
    )
    raw = await file.read(ARCHIVE_MAX_BYTES + 1)
    try:
        content, attachments, manifest = await asyncio.to_thread(
            read_document_archive, raw
        )
        for meta, data in attachments:
            if len(data) > config.KNOWLEDGE_PDF_MAX_BYTES:
                raise ValueError("Attachment exceeds the configured file limit")
            await asyncio.to_thread(material_content_type, data, meta["filename"])
    except Exception as error:
        raise HTTPException(
            422, "Invalid document archive: " + str(error)[:300]
        ) from error
    digest = canonical_digest(
        {
            "archive": hashlib.sha256(raw).hexdigest(),
            "scope": {key: str(value) for key, value in scope.model_values().items()},
            "request_key": str(request_key),
        }
    )
    if preview_digest != digest:
        return {
            "preview_digest": digest,
            "requires_confirmation": True,
            "snapshot": {
                "title": content.title,
                "body": content.body,
                "record_data": content.record_data.model_dump(),
                "files": [meta for meta, _ in attachments],
                "scope_type": scope.scope_type,
            },
        }
    await db_session.scalar(
        select(User.id).where(User.id == current_user.id).with_for_update()
    )
    existing = await db_session.get(ResearchDocument, request_key)
    if existing:
        entry, doc = await _context(db_session, current_user, request_key, write=True)
        if doc.origin.get("archive_digest") != digest:
            raise HTTPException(409, "Import request key already used")
        return await _payload(db_session, current_user, entry, doc)
    if await db_session.get(ResearchLogEntry, request_key):
        raise HTTPException(409, "Import request key already used")
    if attachments:
        material_scope = await resolve_scope(
            db_session,
            current_user,
            scope_type=OwnerScope(scope_type),
            lab_id=lab_id,
            project_id=project_id,
            capability="knowledge.import",
        )
        await assert_research_file_upload_quota(
            db_session,
            current_user.id,
            sum(len(data) for _, data in attachments),
            incoming_count=len(attachments),
        )
    uploaded_keys = []
    try:
        ids = []
        for meta, data in attachments:
            saved, _, _ = await persist_material(
                db_session,
                current_user,
                material_scope,
                filename=meta["filename"],
                data=data,
                source_note="Imported from a research document archive",
                occurred_at=None,
                request_key=uuid4(),
                uploaded_keys=uploaded_keys,
            )
            ids.append(str(saved.id))
        entry = ResearchLogEntry(
            id=request_key,
            **scope.model_values(),
            kind=content.kind,
            title=content.title,
            body=content.body,
            occurred_at=content.occurred_at or datetime.now(UTC),
            created_by_user_id=current_user.id,
            revision=1,
        )
        db_session.add(entry)
        await db_session.flush()
        doc = ResearchDocument(
            id=entry.id,
            state="draft",
            format_version="md.v1" if content.body_format == "md" else "aimd.v1",
            record_data=content.record_data.model_dump(mode="json"),
            file_ids=ids,
            tags=content.tags,
            collection=content.collection,
            origin={
                "kind": "archive",
                "archive_digest": digest,
                "source_revision": manifest.get("revision"),
            },
        )
        db_session.add(doc)
        _save_revision(
            db_session,
            entry,
            doc,
            current_user,
            "Imported document archive; requires fresh validation",
        )
        await db_session.commit()
        return await _payload(db_session, current_user, entry, doc)
    except Exception:
        await cleanup_material_uploads(db_session, uploaded_keys)
        raise


@router.get("/{document_id}")
async def get_document(
    document_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    entry, doc = await _context(db_session, current_user, document_id)
    return await _payload(db_session, current_user, entry, doc)


def _update_preview(entry, doc, params):
    values = params.model_dump(include=set(DocumentContent.model_fields))
    values["body_format"] = values.get("body_format") or ("md" if doc.format_version == "md.v1" else "aimd")
    if values["body_format"] == "md" and any(values["record_data"].values()):
        raise HTTPException(422, "Structured field values require AIMD format")
    proposed = DocumentContent.model_validate(values)
    impact = document_change_impact(_content(entry, doc), proposed)
    digest = canonical_digest(
        {
            "document_id": str(entry.id),
            "revision": entry.revision,
            "proposed": proposed.model_dump(mode="json"),
            "impact": impact,
        }
    )
    return {"impact": impact, "preview_digest": digest}


@router.post("/{document_id}/preview")
async def preview_document(
    document_id: UUID,
    params: DocumentUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    entry, doc = await _context(db_session, current_user, document_id)
    _assert_revision(entry, params.expected_revision)
    return await asyncio.to_thread(_update_preview, entry, doc, params)


@router.put("/{document_id}")
async def update_document(
    document_id: UUID,
    params: DocumentUpdate,
    current_user: CurrentUser,
    db_session: DBSession,
):
    entry, doc = await _context(db_session, current_user, document_id, write=True)
    if await db_session.get(Meeting, document_id) and (
        params.kind != "meeting"
        or (params.occurred_at and params.occurred_at != entry.occurred_at)
    ):
        raise HTTPException(422, "Change meeting type/time in the meeting page")
    _assert_revision(entry, params.expected_revision)
    preview = await asyncio.to_thread(_update_preview, entry, doc, params)
    if (
        preview["impact"]["requires_confirmation"]
        and params.preview_digest != preview["preview_digest"]
    ):
        raise HTTPException(409, {"code": "definition_review_required", **preview})
    await _files(db_session, current_user, entry, params.file_ids)
    entry.title, entry.body, entry.kind = params.title, params.body, params.kind
    if params.occurred_at:
        entry.occurred_at = params.occurred_at
    entry.revision += 1
    entry.updated_at = datetime.now(UTC)
    doc.state = "draft"
    if params.body_format:
        doc.format_version = params.body_format + ".v1"
    if doc.format_version == "md.v1" and any(params.record_data.model_dump().values()):
        raise HTTPException(422, "Structured field values require AIMD format")
    doc.record_data = params.record_data.model_dump(mode="json")
    doc.file_ids = [str(item) for item in params.file_ids]
    doc.tags, doc.collection = params.tags, params.collection
    _save_revision(db_session, entry, doc, current_user, params.change_summary)
    await db_session.commit()
    return await _payload(db_session, current_user, entry, doc)


@router.get("/{document_id}/revisions")
async def document_revisions(
    document_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    await _context(db_session, current_user, document_id)
    rows = (
        await db_session.scalars(
            select(ResearchLogRevision)
            .where(ResearchLogRevision.log_entry_id == document_id)
            .order_by(ResearchLogRevision.revision.desc())
            .limit(100)
        )
    ).all()
    return {"items": [row.as_dict() for row in rows]}


@router.post("/{document_id}/restore/{revision}")
async def restore_document(
    document_id: UUID,
    revision: int,
    params: RevisionRequest,
    current_user: CurrentUser,
    db_session: DBSession,
):
    entry, doc = await _context(db_session, current_user, document_id, write=True)
    if await db_session.get(Meeting, document_id):
        raise HTTPException(
            422,
            "Review historical minutes and save the desired text from the meeting page; audience and attendance are not restored implicitly",
        )
    _assert_revision(entry, params.expected_revision)
    old = await db_session.scalar(
        select(ResearchLogRevision).where(
            ResearchLogRevision.log_entry_id == document_id,
            ResearchLogRevision.revision == revision,
        )
    )
    if old is None or "document" not in old.snapshot:
        raise HTTPException(404, "Document revision not found")
    digest = canonical_digest(
        {
            "document_id": str(document_id),
            "current": entry.revision,
            "restore": old.snapshot,
        }
    )
    if params.preview_digest != digest:
        return {
            "preview_digest": digest,
            "snapshot": old.snapshot,
            "requires_confirmation": True,
        }
    data = old.snapshot["document"]
    await _files(db_session, current_user, entry, data["file_ids"])
    entry.title, entry.body, entry.kind = (
        old.snapshot["title"],
        old.snapshot["body"],
        old.snapshot["kind"],
    )
    entry.occurred_at = datetime.fromisoformat(old.snapshot["occurred_at"])
    doc.format_version = data.get("format_version", "aimd.v1")
    for key in ("record_data", "file_ids", "tags", "collection"):
        setattr(doc, key, deepcopy(data[key]))
    doc.state = "draft"
    entry.revision += 1
    entry.updated_at = datetime.now(UTC)
    _save_revision(
        db_session, entry, doc, current_user, f"Restored revision {revision}"
    )
    await db_session.commit()
    return await _payload(db_session, current_user, entry, doc)


@router.post("/{document_id}/validate")
async def check_document(
    document_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    entry, doc = await _context(db_session, current_user, document_id)
    return await asyncio.to_thread(validate_document, "" if doc.format_version == "md.v1" else entry.body, doc.record_data)


@router.post("/{document_id}/submit")
async def submit_document(
    document_id: UUID,
    params: RevisionRequest,
    current_user: CurrentUser,
    db_session: DBSession,
):
    entry, doc = await _context(db_session, current_user, document_id, write=True)
    _assert_revision(entry, params.expected_revision)
    validation = await asyncio.to_thread(validate_document, "" if doc.format_version == "md.v1" else entry.body, doc.record_data)
    if not validation["valid"]:
        raise HTTPException(422, validation)
    files = await _files(db_session, current_user, entry, doc.file_ids)
    snapshot = {
        "format": DOCUMENT_FORMAT,
        "content": _content(entry, doc),
        "definition": validation["schema"],
        "files": files,
        "origin": doc.origin,
        "scope_type": entry.scope_type,
        "lab_id": str(entry.lab_id) if entry.lab_id else None,
        "project_id": str(entry.project_id) if entry.project_id else None,
    }
    digest = canonical_digest(
        {
            "document_id": str(entry.id),
            "source_revision": entry.revision,
            "snapshot": snapshot,
        }
    )
    if params.preview_digest != digest:
        return {
            "preview_digest": digest,
            "snapshot": snapshot,
            "requires_confirmation": True,
        }
    result = await db_session.scalar(
        select(ResearchDocumentSubmission).where(
            ResearchDocumentSubmission.document_id == document_id,
            ResearchDocumentSubmission.source_revision == entry.revision,
        )
    )
    if result is None:
        result = ResearchDocumentSubmission(
            document_id=document_id,
            source_revision=entry.revision,
            snapshot=snapshot,
            digest=digest,
            created_by_user_id=current_user.id,
        )
        db_session.add(result)
    doc.state = "submitted"
    await db_session.commit()
    return {
        "submission_id": str(result.id),
        "source_revision": result.source_revision,
        "digest": result.digest,
        "state": "submitted",
    }


@router.get("/{document_id}/submissions")
async def list_submissions(
    document_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    await _context(db_session, current_user, document_id)
    rows = (
        await db_session.scalars(
            select(ResearchDocumentSubmission)
            .where(ResearchDocumentSubmission.document_id == document_id)
            .order_by(ResearchDocumentSubmission.source_revision.desc())
        )
    ).all()
    return {"items": [row.as_dict() for row in rows]}


@router.post("/{document_id}/derive")
async def derive_document(
    document_id: UUID,
    params: DeriveRequest,
    current_user: CurrentUser,
    db_session: DBSession,
):
    entry, doc = await _context(db_session, current_user, document_id, write=True)
    await require_shareable_meeting_source(db_session, entry)
    _assert_revision(entry, params.expected_revision)
    scope = None
    if params.kind == "knowledge":
        scope = await resolve_scope(
            db_session,
            current_user,
            scope_type=OwnerScope(entry.scope_type),
            lab_id=entry.lab_id,
            project_id=entry.project_id,
            capability="knowledge.write",
        )
    snapshot = {
        "document_id": str(entry.id),
        "source_revision": entry.revision,
        "source_digest": canonical_digest(_document_snapshot(entry, doc)),
        "kind": params.kind,
        "title": params.title,
        "body": params.body,
        "file_ids": [],
        "record_data": {},
    }
    digest = canonical_digest(snapshot)
    if params.preview_digest != digest:
        return {
            "preview_digest": digest,
            "snapshot": snapshot,
            "requires_confirmation": True,
        }
    existing = await db_session.scalar(
        select(ResearchDocumentDerivation).where(
            ResearchDocumentDerivation.document_id == document_id,
            ResearchDocumentDerivation.source_revision == entry.revision,
            ResearchDocumentDerivation.kind == params.kind,
        )
    )
    if existing:
        if existing.digest != digest:
            raise HTTPException(
                409,
                "This revision already has a different derivation; save a new document revision first",
            )
        return {
            "id": str(existing.id),
            "knowledge_id": str(existing.knowledge_id)
            if existing.knowledge_id
            else None,
            "kind": existing.kind,
        }
    item = None
    if params.kind == "knowledge":
        item = KnowledgeItem(
            **scope.model_values(),
            visibility={"personal": "private", "lab": "lab", "project": "project"}[
                entry.scope_type
            ],
            kind="note",
            state="draft",
            title=params.title,
            body=params.body,
            tags=doc.tags,
            revision=1,
            created_by_user_id=current_user.id,
        )
        db_session.add(item)
        await db_session.flush()
        db_session.add(
            KnowledgeRevision(
                knowledge_item_id=item.id,
                revision=1,
                snapshot=snapshot_knowledge(item),
                change_summary="Derived from a research document",
                created_by_user_id=current_user.id,
            )
        )
    else:
        # A package is a draft for the ordinary Protocol editor/import flow;
        # creating a derivation does not publish a runnable method.
        validation = await asyncio.to_thread(validate_document, params.body, {})
        if validation["schema"] is None:
            raise HTTPException(422, validation)
    derived = ResearchDocumentDerivation(
        document_id=document_id,
        source_revision=entry.revision,
        kind=params.kind,
        knowledge_id=item.id if item else None,
        snapshot=snapshot,
        digest=digest,
        created_by_user_id=current_user.id,
    )
    db_session.add(derived)
    await db_session.commit()
    return {
        "id": str(derived.id),
        "knowledge_id": str(item.id) if item else None,
        "kind": params.kind,
    }


@router.get("/{document_id}/export")
async def export_document(
    document_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    entry, doc = await _context(db_session, current_user, document_id)
    files = await _files(db_session, current_user, entry, doc.file_ids)
    if sum(item["size_bytes"] for item in files) > ARCHIVE_MAX_BYTES - 2_000_000:
        raise HTTPException(
            413, "Document archive is too large; download originals individually"
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("document.md" if doc.format_version == "md.v1" else "document.aimd", entry.body)
        archive.writestr(
            "document.json",
            json.dumps(
                {
                    "format": DOCUMENT_FORMAT,
                    "revision": entry.revision,
                    "content": _content(entry, doc),
                    "files": files,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        for item in files:
            file = await db_session.get(ResearchFile, UUID(item["id"]))
            blob = await db_session.get(ResearchFileBlob, file.blob_id)
            raw = await get_file_content(
                blob.storage_object_key, backend=blob.storage_backend
            )
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise HTTPException(409, "Attachment checksum mismatch")
            archive.writestr(f"files/{item['id']}", raw)
            db_session.add(
                ResearchFileAccessAudit(
                    research_file_id=file.id,
                    lab_id=file.lab_id,
                    actor_user_id=current_user.id,
                    action="export",
                    outcome="authorized",
                )
            )
    await db_session.commit()
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="research-document-{entry.id}.zip"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/{document_id}/methods/{derivation_id}/package")
async def export_method(
    document_id: UUID,
    derivation_id: UUID,
    current_user: CurrentUser,
    db_session: DBSession,
):
    await _context(db_session, current_user, document_id)
    row = await db_session.get(ResearchDocumentDerivation, derivation_id)
    if row is None or row.document_id != document_id or row.kind != "protocol":
        raise HTTPException(404, "Method draft not found")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("protocol.aimd", row.snapshot["body"])
        archive.writestr(
            "protocol.toml",
            "[airalogy_protocol]\n"
            + f'id = "document_method_{str(row.id).replace("-", "")[:12]}"\n'
            + f'name = {json.dumps(row.snapshot["title"], ensure_ascii=False)}\nversion = "0.1.0"\n',
        )
        # Source identifiers remain in the private derivation, not the portable method.
    return Response(
        buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="protocol-draft.zip"'},
    )
