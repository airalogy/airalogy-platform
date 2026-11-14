"""Delegated authoring: exact source, bounded candidate, human-reviewed publication."""

import asyncio
import base64
import difflib
import hashlib
import io
import shutil
import tempfile
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import BackgroundTasks, HTTPException, UploadFile
from sqlalchemy import select
from starlette.datastructures import Headers

from app.config import config
from app.libs.protocol_agent import protocol_exec
from app.models.lab import Lab
from app.models.protocol import Protocol
from app.models.protocol_version import ProtocolMetadata, ProtocolVersion
from app.services import external_access as boundary
from app.services.browser_paths import project_browser_path
from app.services.external_research_contracts import ProtocolCandidate
from app.services.protocol_authoring import SourceFile, validate_sources
from app.services.protocol_exports import build_protocol_export


def archive_bytes(files, binary_files=None):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content.encode())
        for name, content in sorted((binary_files or {}).items()):
            archive.writestr(name, base64.b64decode(content, validate=True))
    return stream.getvalue()


async def target(db, access, protocol_id, base_id, *, succeeded=False):
    if protocol_id is None:
        await boundary.check_user_permission(
            db, access.project, access.user, "create_protocol"
        )
        return None, None
    protocol, version = await boundary.protocol_context(
        db, access, protocol_id, "update_protocol"
    )
    if not succeeded and version.id != base_id:
        boundary.fail("protocol_changed_preview_again", 409)
    return protocol, version


async def exported(db, access, protocol_id, version, output_format):
    boundary.scope(access, "protocols:source")
    protocol, pv = await boundary.protocol_context(
        db, access, protocol_id, version=version
    )
    # Never read the executor directory: it can contain runtime files and credentials.
    with tempfile.TemporaryDirectory(prefix="external-source-") as temporary:
        root = Path(temporary)
        source = root / "source.zip"
        await pv.download_package(str(source))
        try:
            output = await asyncio.to_thread(
                build_protocol_export, source, root, output_format
            )
            if output.stat().st_size > 1_000_000:
                boundary.fail("source_too_large_use_platform_export", 413)
            data = output.read_bytes()
        except (ValueError, zipfile.BadZipFile) as error:
            raise HTTPException(
                422, "Protocol source archive cannot be exported"
            ) from error
    return protocol, pv, data


async def preview(db, access, params):
    from app.routers.protocol_versions import (
        _validate_resource_definition,
        is_new_version,
    )
    from app.services.external_research import new_operation
    from app.services.schema_governance import build_compatibility_report

    boundary.scope(access, "protocols:candidate")
    # Source rights are required when a diff exposes the old implementation.
    boundary.scope(access, "protocols:source")
    protocol, old = await target(db, access, params.protocol_id, params.base_version_id)
    static = await asyncio.to_thread(
        validate_sources,
        [SourceFile(path=k, content=v) for k, v in params.files.items()],
    )
    if static.status != "valid":
        raise HTTPException(
            422, {"code": "protocol_source_invalid", "validation": static.model_dump()}
        )
    name = f"external_preview_{uuid4().hex}"
    root = Path(config.PROTOCOL_DIR) / name
    root.mkdir(parents=True)
    try:
        for filename, content in params.files.items():
            path = root / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        for filename, content in params.binary_files.items():
            path = root / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(content, validate=True))
        result = await protocol_exec("get_protocol_info", name, {"env_vars": {}})
        if not result.get("success"):
            raise HTTPException(
                422,
                {
                    "code": "protocol_validation_failed",
                    "message": "Executor validation failed. Inspect and validate the candidate locally before retrying.",
                },
            )
        info = result["data"]
        if any(
            (root / k).read_text(encoding="utf-8") != v for k, v in params.files.items()
        ):
            boundary.fail("protocol_parser_changed_source", 409)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    try:
        meta = ProtocolMetadata.model_validate(info["meta_data"])
    except ValueError as error:
        raise HTTPException(422, "Invalid Protocol metadata") from error
    _validate_resource_definition(info, meta.kind)
    await target(db, access, params.protocol_id, params.base_version_id)
    if protocol and (
        protocol.uid != meta.id
        or protocol.kind != meta.kind
        or not is_new_version(old.version, meta.version)
    ):
        boundary.fail("protocol_identity_or_version_invalid", 422)
    if not protocol and await db.scalar(
        select(Protocol.id).where(
            Protocol.project_id == access.project.id,
            Protocol.uid == meta.id,
            Protocol.deleted_at.is_(None),
        )
    ):
        boundary.fail("protocol_uid_exists", 409)
    old_files = {}
    if old:
        _, _, raw = await exported(db, access, protocol.id, old.version, "zip")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for member in archive.infolist():
                if member.file_size > 1_000_000:
                    boundary.fail("source_too_large_use_platform_export", 413)
                try:
                    old_files[member.filename] = archive.read(member).decode("utf-8")
                except UnicodeError:
                    old_files[member.filename] = (
                        f"[binary file sha256={hashlib.sha256(archive.read(member)).hexdigest()} bytes={member.file_size}]"
                    )
    proposed_files = dict(params.files)
    for filename, value in params.binary_files.items():
        data = base64.b64decode(value, validate=True)
        proposed_files[filename] = (
            f"[binary file sha256={hashlib.sha256(data).hexdigest()} bytes={len(data)}]"
        )
    changes = []
    total = 0
    for filename in sorted(set(old_files) | set(proposed_files)):
        before, after = old_files.get(filename, ""), proposed_files.get(filename, "")
        if before == after:
            continue
        diff = "".join(
            difflib.unified_diff(
                before.splitlines(keepends=True),
                after.splitlines(keepends=True),
                fromfile=f"base/{filename}",
                tofile=f"candidate/{filename}",
            )
        )
        total += len(diff.encode())
        if total > 1_500_000:
            boundary.fail("diff_too_large", 413)
        changes.append(
            {
                "path": filename,
                "status": "added"
                if filename not in old_files
                else "removed"
                if filename not in proposed_files
                else "modified",
                "diff": diff,
            }
        )
    payload = params.model_dump(mode="json")
    payload["validated_info_digest"] = boundary.digest(info)
    summary = {
        "project_name": access.project.name,
        "protocol_name": meta.name,
        "protocol_uid": meta.id,
        "version": meta.version,
        "base_version": old.version if old else None,
        "base_version_id": str(old.id) if old else None,
        "source_digest": boundary.digest(
            {"files": params.files, "binary_files": params.binary_files}
        ),
        "validation": "static_and_executor_passed",
        "file_changes": changes,
        "compatibility": build_compatibility_report(
            old.json_schema,
            info["json_schema"],
            previous_version=old.version,
            current_version=meta.version,
        )
        if old
        else None,
        "records_changed": 0,
    }
    return await new_operation(
        db,
        access,
        key=params.request_key,
        kind="protocol",
        payload=payload,
        summary=summary,
        protocol_id=params.protocol_id,
        version_id=params.base_version_id,
    )


async def authorize_operation(db, access, op, *, publishing=False):
    boundary.scope(access, "protocols:candidate")
    boundary.scope(access, "protocols:source")
    if publishing:
        boundary.scope(access, "protocols:publish")
    await target(
        db,
        access,
        op.protocol_id,
        op.protocol_version_id,
        succeeded=op.state == "succeeded",
    )
    if op.state == "succeeded":
        await boundary.protocol_context(db, access, UUID(op.result["protocol_id"]))


async def execute(db, access, op):
    from app.routers.protocol_versions import save_protocol_package
    from app.services.external_research import authorize_operation as verify_operation

    await verify_operation(db, access, op)
    await authorize_operation(db, access, op, publishing=True)
    if op.state == "succeeded":
        return boundary.operation_view(op)
    if op.state != "approved" or op.expires_at <= boundary.now():
        boundary.fail("operation_not_approved_or_expired", 409)
    payload = dict(op.payload)
    info_digest = payload.pop("validated_info_digest")
    params = ProtocolCandidate.model_validate(payload)
    raw = archive_bytes(params.files, params.binary_files)

    async def review(info, root):
        if any(
            (root / k).read_bytes() != base64.b64decode(v, validate=True)
            for k, v in params.binary_files.items()
        ):
            boundary.fail("protocol_parser_changed_source", 409)
        await authorize_operation(db, access, op, publishing=True)
        if boundary.digest(info) != info_digest or any(
            (root / k).read_text(encoding="utf-8") != v for k, v in params.files.items()
        ):
            boundary.fail("protocol_validation_changed_preview_again", 409)

    tasks = BackgroundTasks()
    upload = UploadFile(
        io.BytesIO(raw),
        filename="candidate.zip",
        headers=Headers({"content-type": "application/zip"}),
    )
    result = await save_protocol_package(
        access.user,
        db,
        upload,
        tasks,
        access.project.id,
        protocol_id=params.protocol_id,
        commit=False,
        delegated_review=review,
        delegated_source=raw,
    )
    protocol_id = str(result["data"]["id"])
    published = await db.get(Protocol, UUID(protocol_id))
    lab = await db.get(Lab, access.project.lab_id)
    op.state, op.payload = "succeeded", {}
    op.result = {
        "protocol_id": protocol_id,
        "version": op.summary["version"],
        "links": [
            f"{project_browser_path(lab.uid, access.project.uid)}/protocols/{published.uid}"
        ],
    }
    # Shared publisher's cleanup and derived indexing must only run after commit.
    db.info.setdefault("external_background_tasks", []).append(tasks)
    boundary.audit(
        db,
        access.user.id,
        "operation.executed",
        access.grant.id,
        operation_id=str(op.id),
        result=op.result,
    )
    await db.flush()
    return boundary.operation_view(op)


async def call(db, access, name, args):
    if name == "preview_protocol_candidate":
        return await preview(db, access, args)
    protocol, version, data = await exported(
        db, access, args.protocol_id, args.version, args.format
    )
    return {
        "protocol_id": str(protocol.id),
        "protocol_version_id": str(version.id),
        "version": version.version,
        "filename": f"{protocol.uid}-v{version.version}.{args.format}",
        "sha256": hashlib.sha256(data).hexdigest(),
        "content_base64": base64.b64encode(data).decode(),
        "size_bytes": len(data),
        "instruction": "Validate and preview locally with the official Airalogy SDK. Exported source contains no deployment environment variables; never run unreviewed code with credentials.",
    }


def cleanup_temporary(db):
    for path in db.info.pop("external_temporary_paths", []):
        shutil.rmtree(path, ignore_errors=True)
    for path in db.info.pop("external_temporary_files", []):
        Path(path).unlink(missing_ok=True)


async def cleanup_artifacts(db):
    from app.libs.file_storage import delete_file

    db.info.pop("external_background_tasks", None)
    for version_id, key, path in db.info.pop("external_protocol_artifacts", []):
        if await db.get(ProtocolVersion, version_id) is None:
            await delete_file(key)
            shutil.rmtree(path, ignore_errors=True)
