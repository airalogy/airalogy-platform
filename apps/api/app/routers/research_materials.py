"""Original research material intake, independent of Protocols and Tasks."""

import asyncio
import hashlib
import io
from datetime import datetime
from pathlib import PurePath
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.config import config
from app.database import DBSession
from app.libs.file_storage import (
    default_storage_backend,
    default_storage_namespace,
    delete_file,
    get_file_content,
    upload_file,
)
from app.models.knowledge import (
    OwnerScope,
    ResearchFile,
    ResearchFileAccessAudit,
    ResearchFileBlob,
    Visibility,
)
from app.models.research_document import ResearchMaterial
from app.models.user import User
from app.routers.depends import CurrentUser
from app.services.knowledge import (
    assert_research_file_upload_quota,
    authorize_research_file,
    extract_pdf_text_async,
    resolve_scope,
    safe_download_filename,
    scope_conditions,
    validate_visibility,
)
from app.services.workflow_files import validate_file_header

router = APIRouter(prefix="/research-materials", tags=["research-materials"])


def material_content_type(data: bytes, filename: str) -> str:
    validate_file_header(io.BytesIO(data), filename)
    suffix = PurePath(filename).suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        with Image.open(io.BytesIO(data)) as image:
            formats = {
                ".png": "PNG",
                ".jpg": "JPEG",
                ".jpeg": "JPEG",
                ".gif": "GIF",
                ".webp": "WEBP",
            }
            if image.format != formats[suffix]:
                raise ValueError("Image bytes do not match their file extension")
            content_type = Image.MIME[image.format]
            image.verify()
            return content_type
    if suffix == ".pdf":
        return "application/pdf"
    # Active or unknown formats are opaque downloads, never same-origin HTML.
    return "application/octet-stream"


def _payload(file, blob, material):
    return {
        "id": str(file.id),
        "filename": file.filename,
        "content_type": blob.content_type,
        "size_bytes": blob.size_bytes,
        "sha256": blob.checksum_sha256,
        "scope_type": file.scope_type,
        "visibility": file.visibility,
        "created_at": file.created_at,
        "source_note": material.source_note,
        "occurred_at": material.occurred_at,
        "previewable": blob.content_type
        in {"application/pdf", "image/png", "image/jpeg", "image/gif", "image/webp"},
    }


async def persist_material(
    db,
    user,
    scope,
    *,
    filename,
    data,
    source_note,
    occurred_at,
    request_key,
    uploaded_keys,
):
    """Stage a logical file in the caller's transaction; never commit here."""
    content_type = await asyncio.to_thread(material_content_type, data, filename)
    checksum = hashlib.sha256(data).hexdigest()
    blob = await db.scalar(
        select(ResearchFileBlob).where(ResearchFileBlob.checksum_sha256 == checksum)
    )
    if blob is None:
        key = f"research-materials/{uuid4().hex}/{checksum}"
        uploaded_keys.append(key)
        await upload_file(
            key, io.BytesIO(data), content_type=content_type, length=len(data)
        )
        identity = await db.scalar(
            insert(ResearchFileBlob)
            .values(
                id=uuid4(),
                checksum_sha256=checksum,
                content_type=content_type,
                size_bytes=len(data),
                storage_backend=default_storage_backend(),
                storage_namespace=default_storage_namespace(),
                storage_object_key=key,
                extracted_text="",
            )
            .on_conflict_do_nothing(index_elements=[ResearchFileBlob.checksum_sha256])
            .returning(ResearchFileBlob.id)
        )
        blob = await db.scalar(
            select(ResearchFileBlob).where(ResearchFileBlob.checksum_sha256 == checksum)
        )
        if identity is None:
            await delete_file(key)
            uploaded_keys.remove(key)
    visibility = {
        "personal": Visibility.PRIVATE,
        "lab": Visibility.LAB,
        "project": Visibility.PROJECT,
    }[scope.scope_type.value]
    validate_visibility(scope, visibility)
    file = ResearchFile(
        id=uuid4(),
        **scope.model_values(),
        blob_id=blob.id,
        filename=filename,
        visibility=visibility.value,
        uploaded_by_user_id=user.id,
    )
    db.add(file)
    await db.flush()
    material = ResearchMaterial(
        id=file.id,
        request_key=request_key,
        source_note=source_note,
        occurred_at=occurred_at,
    )
    db.add(material)
    await db.flush()
    return file, blob, material


async def cleanup_material_uploads(db, uploaded_keys):
    await db.rollback()
    for key in uploaded_keys:
        # Never delete a committed/shared object after an uncertain response.
        referenced = await db.scalar(
            select(ResearchFileBlob.id).where(
                ResearchFileBlob.storage_object_key == key
            )
        )
        if referenced is None:
            await delete_file(key)


@router.get("")
async def list_materials(
    current_user: CurrentUser,
    db_session: DBSession,
    scope_type: OwnerScope,
    lab_id: UUID | None = None,
    project_id: UUID | None = None,
    q: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
):
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=scope_type,
        lab_id=lab_id,
        project_id=project_id,
        capability="knowledge.read",
    )
    # The archive creates normal scope-visible material. Restricted paper files
    # remain in their existing interface and are not broadened by this listing.
    query = (
        select(ResearchFile, ResearchFileBlob, ResearchMaterial)
        .join(ResearchFileBlob, ResearchFileBlob.id == ResearchFile.blob_id)
        .join(ResearchMaterial, ResearchMaterial.id == ResearchFile.id)
        .where(
            *scope_conditions(ResearchFile, scope),
            ResearchFile.archived_at.is_(None),
            ResearchFile.visibility != "restricted",
        )
    )
    if q:
        query = query.where(ResearchFile.filename.ilike(f"%{q}%"))
    total = await db_session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await db_session.execute(
            query.order_by(ResearchFile.created_at.desc(), ResearchFile.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    can_upload = True
    try:
        await resolve_scope(
            db_session,
            current_user,
            scope_type=scope_type,
            lab_id=lab_id,
            project_id=project_id,
            capability="knowledge.import",
        )
    except HTTPException:
        can_upload = False
    return {
        "items": [_payload(*row) for row in rows],
        "total_count": total,
        "can_upload": can_upload,
    }


@router.post("")
async def upload_material(
    current_user: CurrentUser,
    db_session: DBSession,
    file: Annotated[UploadFile, File()],
    scope_type: Annotated[OwnerScope, Form()],
    request_key: Annotated[UUID, Form()],
    lab_id: Annotated[UUID | None, Form()] = None,
    project_id: Annotated[UUID | None, Form()] = None,
    source_note: Annotated[str, Form(max_length=4000)] = "",
    occurred_at: Annotated[datetime | None, Form()] = None,
):
    scope = await resolve_scope(
        db_session,
        current_user,
        scope_type=scope_type,
        lab_id=lab_id,
        project_id=project_id,
        capability="knowledge.import",
    )
    if occurred_at is not None and occurred_at.tzinfo is None:
        raise HTTPException(422, "Occurrence time requires a timezone")
    filename = safe_download_filename(file.filename or "material.bin")
    if len(filename) > 512:
        raise HTTPException(422, "Filename must be at most 512 characters")
    data = await file.read(config.KNOWLEDGE_PDF_MAX_BYTES + 1)
    if not data or len(data) > config.KNOWLEDGE_PDF_MAX_BYTES:
        raise HTTPException(413, "File is empty or exceeds the configured size limit")
    try:
        await asyncio.to_thread(material_content_type, data, filename)
    except Exception as error:
        raise HTTPException(
            415, "File content does not match its declared format"
        ) from error
    # Resolve retries before quota so a committed upload can be recovered even
    # when that upload used the last available slot.
    await db_session.scalar(
        select(User.id).where(User.id == current_user.id).with_for_update()
    )
    checksum = hashlib.sha256(data).hexdigest()
    previous = await db_session.scalar(
        select(ResearchMaterial).where(ResearchMaterial.request_key == request_key)
    )
    if previous:
        old_file = await db_session.get(ResearchFile, previous.id)
        old_blob = await db_session.get(ResearchFileBlob, old_file.blob_id)
        if (
            old_file.uploaded_by_user_id != current_user.id
            or old_blob.checksum_sha256 != checksum
            or old_file.filename != filename
            or previous.source_note != source_note
            or previous.occurred_at != occurred_at
            or any(
                getattr(old_file, key) != value
                for key, value in scope.model_values().items()
            )
        ):
            raise HTTPException(409, "Upload key already used for another file")
        await authorize_research_file(db_session, current_user, old_file)
        return _payload(old_file, old_blob, previous)
    await assert_research_file_upload_quota(db_session, current_user.id, len(data))
    uploaded_keys = []
    try:
        result = await persist_material(
            db_session,
            current_user,
            scope,
            filename=filename,
            data=data,
            source_note=source_note,
            occurred_at=occurred_at,
            request_key=request_key,
            uploaded_keys=uploaded_keys,
        )
        await db_session.commit()
        return _payload(*result)
    except Exception:
        await cleanup_material_uploads(db_session, uploaded_keys)
        raise


@router.get("/{file_id}/text")
async def extract_material_text(
    file_id: UUID, current_user: CurrentUser, db_session: DBSession
):
    file = await db_session.get(ResearchFile, file_id)
    material = await db_session.get(ResearchMaterial, file_id)
    if file is None or material is None or file.archived_at is not None:
        raise HTTPException(404, "Material not found")
    await authorize_research_file(db_session, current_user, file)
    blob = await db_session.get(ResearchFileBlob, file.blob_id)
    if blob.size_bytes > min(config.KNOWLEDGE_PDF_MAX_BYTES, 20 * 1024 * 1024):
        raise HTTPException(413, "Material is too large for text extraction")
    data = await get_file_content(blob.storage_object_key, backend=blob.storage_backend)
    if hashlib.sha256(data).hexdigest() != blob.checksum_sha256:
        raise HTTPException(409, "Material checksum mismatch")
    if blob.content_type == "application/pdf":
        text = await extract_pdf_text_async(data)
    elif PurePath(file.filename).suffix.lower() in {
        ".txt",
        ".md",
        ".aimd",
        ".csv",
        ".tsv",
        ".json",
    }:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise HTTPException(
                422, "Use a UTF-8 source or transcribe this material manually"
            ) from error
    else:
        raise HTTPException(
            422, "This format requires manual transcription; the original is preserved"
        )
    db_session.add(
        ResearchFileAccessAudit(
            research_file_id=file.id,
            lab_id=file.lab_id,
            actor_user_id=current_user.id,
            action="extract",
            outcome="authorized",
        )
    )
    await db_session.commit()
    return {
        "file_id": str(file.id),
        "sha256": blob.checksum_sha256,
        "text": text[:200_000],
        "truncated": len(text) > 200_000,
        "requires_review": True,
        "method": "text-extraction",
        "empty": not text.strip(),
    }
