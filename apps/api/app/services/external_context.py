"""Independently scoped context and attachment reads; never public object URLs."""

import base64
import hashlib
import re

from fastapi import HTTPException
from sqlalchemy import select

from app.libs.file_storage import (
    default_storage_namespace,
    get_file_with_stream,
    is_managed_storage_backend,
)
from app.models.airalogy_file import AiralogyFile
from app.models.external_research import ExternalAnalysisFile
from app.models.knowledge import (
    KnowledgeItem,
    ResearchFile,
    ResearchFileAccessAudit,
    ResearchFileBlob,
)
from app.models.research_document import ResearchDocument, ResearchMaterial
from app.models.research_log import ResearchLogEntry
from app.services import external_access as boundary
from app.services.knowledge import authorize_knowledge_item, authorize_research_file

KINDS = {
    "knowledge": (KnowledgeItem, "knowledge:read"),
    "document": (ResearchLogEntry, "documents:read"),
    "material": (ResearchFile, "materials:read"),
}
CHUNK = 256 * 1024
MAX_FILE = 16 * 1024 * 1024


def text_only(value):
    # Source prose can contain old signed URLs. Export text, not embedded URLs or file capabilities.
    return re.sub(
        r'(?:https?://|airalogy\.id\.file\.)[^\s<>"\)]+',
        "[link withheld: use an authorized attachment tool]",
        value,
    )


async def asset(db, access, kind, identity):
    model, permission = KINDS[kind]
    boundary.scope(access, permission)
    item = await db.get(model, identity, populate_existing=True)
    if (
        item is None
        or item.project_id != access.project.id
        or item.scope_type != "project"
    ):
        boundary.fail("context_not_found", 404)
    if kind == "knowledge":
        await authorize_knowledge_item(db, access.user, item)
        if item.state == "archived":
            boundary.fail("context_not_found", 404)
        return {
            "id": str(item.id),
            "kind": kind,
            "title": text_only(item.title),
            "revision": item.revision,
            "state": item.state,
            "body": text_only(item.body),
        }
    if kind == "document":
        from app.routers.research_documents import _context

        entry, doc = await _context(db, access.user, identity)
        return {
            "id": str(item.id),
            "kind": kind,
            "title": text_only(entry.title),
            "revision": entry.revision,
            "state": doc.state,
            "body": text_only(entry.body),
            "file_ids": doc.file_ids if "files:read" in access.grant.scopes else [],
        }
    if item.archived_at is not None or await db.get(ResearchMaterial, item.id) is None:
        boundary.fail("context_not_found", 404)
    await authorize_research_file(db, access.user, item)
    blob = await db.get(ResearchFileBlob, item.blob_id)
    return {
        "id": str(item.id),
        "kind": kind,
        "title": text_only(item.filename),
        "sha256": blob.checksum_sha256,
        "size_bytes": blob.size_bytes,
        "body": "",
        "file_id": str(item.id),
    }


async def list_assets(db, access, args):
    model, permission = KINDS[args.kind]
    boundary.scope(access, permission)
    query = select(model.id).where(
        model.project_id == access.project.id, model.scope_type == "project"
    )
    if args.kind == "document":
        query = query.join(ResearchDocument, ResearchDocument.id == ResearchLogEntry.id)
    if args.kind == "material":
        query = query.join(ResearchMaterial, ResearchMaterial.id == ResearchFile.id)
    if args.after_id:
        query = query.where(model.id > args.after_id)
    ids = (await db.scalars(query.order_by(model.id).limit(51))).all()
    items = []
    for identity in ids[:50]:
        try:
            result = await asset(db, access, args.kind, identity)
            items.append({k: v for k, v in result.items() if k != "body"})
        except HTTPException as error:
            if error.status_code not in (403, 404):
                raise
    return {
        "items": items,
        "next_after_id": str(ids[49]) if len(ids) > 50 else None,
        "consistency": "live_listing; read with a digest to pin content",
    }


async def read_asset(db, access, args):
    result = await asset(db, access, args.kind, args.id)
    digest = boundary.digest(result)
    if (args.offset and not args.expected_digest) or (
        args.expected_digest and args.expected_digest != digest
    ):
        boundary.fail("context_changed_restart_read", 409)
    body = result.pop("body")
    return {
        **result,
        "digest": digest,
        "body": body[args.offset : args.offset + 16000],
        "next_offset": args.offset + 16000 if args.offset + 16000 < len(body) else None,
        "untrusted_content": True,
    }


async def bounded_blob(blob):
    backend, namespace = blob.storage_backend, blob.storage_namespace
    if not is_managed_storage_backend(
        backend
    ) or namespace != default_storage_namespace(backend):
        boundary.fail("file_storage_unavailable", 409)
    if (
        blob.size_bytes is None
        or not 0 <= blob.size_bytes <= MAX_FILE
        or not blob.checksum_sha256
    ):
        boundary.fail("file_exceeds_external_limit_or_checksum_unavailable", 413)
    key = blob.storage_object_key
    if isinstance(blob, AiralogyFile):
        if blob.is_external_reference:
            boundary.fail("external_file_reference_not_downloadable", 422)
        key = blob.object_key
    chunks, size = [], 0
    async for chunk in get_file_with_stream(key, backend=backend):
        size += len(chunk)
        if size > MAX_FILE:
            boundary.fail("file_exceeds_external_limit", 413)
        chunks.append(chunk)
    content = b"".join(chunks)
    if (
        len(content) != blob.size_bytes
        or hashlib.sha256(content).hexdigest() != blob.checksum_sha256
    ):
        boundary.fail("file_integrity_failed", 409)
    return content


async def record_files(db, access, args, *, requested_ids=None):
    from app.services.external_research import require_export
    from app.services.record_exports import _walk_file_ids

    boundary.scope(access, "files:read")
    await require_export(db, access)
    protocol, _ = await boundary.protocol_context(db, access, args.protocol_id)
    record = await boundary.read_record(db, access, protocol, args.parent_id)
    values = {
        k: v
        for k, v in (record.data or {}).get("var", {}).items()
        if not any(
            k == blocked or blocked.startswith(k + ".")
            for blocked in access.policy.blocked_fields
        )
    }
    ids = {identity for identity, _, _ in _walk_file_ids(values)}
    if requested_ids is not None:
        ids.intersection_update(requested_ids)
    query = select(AiralogyFile).where(
        AiralogyFile.protocol_id == protocol.id, AiralogyFile.id.in_(ids)
    )
    if requested_ids is None:
        query = query.limit(100)
    files = (await db.scalars(query)).all()
    return record, files


async def file_context(db, access, args):
    boundary.scope(access, "files:read")
    if args.kind == "analysis":
        from app.services.external_research import get_run

        boundary.scope(access, "analysis:read")
        if not args.parent_id:
            boundary.fail("file_parent_required", 422)
        run = await get_run(db, access.user, args.parent_id, access=access)
        file = await db.get(ExternalAnalysisFile, args.file_id)
        if file is None or file.run_id != args.parent_id:
            boundary.fail("file_not_found", 404)
        blob = await db.get(ResearchFileBlob, file.blob_id)
        manifest = next(
            (item for item in run.result["files"] if item["id"] == str(file.id)), None
        )
        if (
            not blob
            or not manifest
            or manifest["sha256"] != blob.checksum_sha256
            or manifest["filename"] != file.filename
        ):
            boundary.fail("file_integrity_failed", 409)
        return file, blob
    if args.kind == "record":
        if not args.parent_id or not args.protocol_id:
            boundary.fail("file_parent_required", 422)
        _, files = await record_files(db, access, args)
        file = next((file for file in files if file.id == args.file_id), None)
        if file is None:
            boundary.fail("file_not_found", 404)
        return file, file
    file = await db.get(ResearchFile, args.file_id, populate_existing=True)
    if (
        file is None
        or file.archived_at is not None
        or file.scope_type != "project"
        or file.project_id != access.project.id
    ):
        boundary.fail("file_not_found", 404)
    if await db.get(ResearchMaterial, file.id):
        boundary.scope(access, "materials:read")
    elif args.parent_id:
        from app.routers.research_documents import _context

        boundary.scope(access, "documents:read")
        entry, doc = await _context(db, access.user, args.parent_id)
        if entry.project_id != access.project.id or str(file.id) not in [
            str(i) for i in doc.file_ids
        ]:
            boundary.fail("file_not_found", 404)
    else:
        boundary.scope(access, "knowledge:read")
    await authorize_research_file(db, access.user, file)
    return file, await db.get(ResearchFileBlob, file.blob_id)


async def read_file(db, access, args):
    file, blob = await file_context(db, access, args)
    result = {
        "file_id": str(file.id),
        "filename": file.filename,
        "sha256": blob.checksum_sha256,
        "size_bytes": blob.size_bytes,
        "chunk_bytes": CHUNK,
    }
    if not args.expected_sha256:
        return result
    if args.expected_sha256 != blob.checksum_sha256:
        boundary.fail("file_changed_restart_read", 409)
    content = await bounded_blob(blob)
    await file_context(db, access, args)
    if isinstance(file, ResearchFile):
        db.add(
            ResearchFileAccessAudit(
                research_file_id=file.id,
                lab_id=file.lab_id,
                actor_user_id=access.user.id,
                action="download",
                outcome="allowed",
            )
        )
    boundary.audit(
        db,
        access.user.id,
        "file.downloaded",
        access.grant.id,
        file_id=str(file.id),
        offset=args.offset,
    )
    return {
        **result,
        "offset": args.offset,
        "content_base64": base64.b64encode(
            content[args.offset : args.offset + CHUNK]
        ).decode(),
        "next_offset": args.offset + CHUNK
        if args.offset + CHUNK < len(content)
        else None,
    }


async def call(db, access, name, args):
    if name == "list_context_assets":
        return await list_assets(db, access, args)
    if name == "read_context_asset":
        return await read_asset(db, access, args)
    if name == "list_record_files":
        record, files = await record_files(db, access, args)
        return {
            "record_id": str(record.id),
            "record_version": record.version,
            "items": [
                {
                    "file_id": str(f.id),
                    "airalogy_id": f.airalogy_id,
                    "filename": f.filename,
                    "sha256": f.checksum_sha256,
                    "size_bytes": f.size_bytes,
                }
                for f in files
            ],
        }
    return await read_file(db, access, args)
