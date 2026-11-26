"""External research reuses AnalysisRun and private file blobs, never a second data store."""

import base64
import binascii
import hashlib
import io
import json
from datetime import timedelta
from pathlib import PurePosixPath
from uuid import UUID, uuid4

from sqlalchemy import and_, delete, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert

from app.models.analysis import AnalysisPipeline, AnalysisPipelineRevision, AnalysisRun
from app.models.external_access import ExternalOperation
from app.models.external_research import (
    ExternalAnalysisFile,
    ExternalAnalysisSource,
    ExternalSnapshot,
)
from app.models.knowledge import ResearchFileBlob
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.services import external_access as boundary
from app.services.browser_paths import project_browser_path
from app.services.external_research_contracts import AnalysisSubmission

ENGINE = "external-research-v1"
MAX_RECORDS = 2000
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_RESULT_BYTES = 1024 * 1024


async def require_export(db, access):
    from app.routers.record_exports import (
        RecordExportParams,
        _resolve_scope_and_authorize,
    )

    boundary.scope(access, "records:read")
    boundary.scope(access, "records:export")
    await _resolve_scope_and_authorize(
        db,
        RecordExportParams(
            scope_type="project",
            lab_id=access.project.lab_id,
            project_id=access.project.id,
        ),
        access.user.id,
    )


async def verify_snapshot(
    db, snapshot, user, *, access=None, allow_expired=False, same_grant=True
):
    if snapshot is None or snapshot.user_id != user.id:
        boundary.fail("snapshot_not_found", 404)
    if access is not None:
        await require_export(db, access)
        if (
            same_grant and snapshot.grant_id != access.grant.id
        ) or snapshot.project_id != access.project.id:
            boundary.fail("snapshot_not_found", 404)
        if snapshot.policy_revision != access.policy.revision:
            boundary.fail("policy_changed_create_snapshot_again", 409)
        if not allow_expired and snapshot.expires_at <= boundary.now():
            boundary.fail("snapshot_expired", 409)
    if boundary.digest(snapshot.content) != snapshot.digest:
        boundary.fail("snapshot_integrity_failed", 409)
    from app.routers.permission import check_user_permission
    from app.services.record_analyses import analysis_scope

    # Recheck exact source ownership and the current tombstone. A newer revision
    # does not rewrite the snapshot, but deletion or revoked access invalidates reads.
    for source in snapshot.content["sources"]:
        protocol, project, _ = await analysis_scope(
            db, UUID(source["protocol_id"]), user
        )
        if project.id != snapshot.project_id:
            boundary.fail("snapshot_sources_unavailable")
        refs = [
            (UUID(row["record_id"]), row["record_version"]) for row in source["records"]
        ]
        if not refs:
            continue
        records = list(
            (
                await db.scalars(
                    select(Record).where(
                        Record.protocol_id == protocol.id,
                        tuple_(Record.id, Record.version).in_(refs),
                        Record.deleted_at.is_(None),
                    )
                )
            ).all()
        )
        if len(records) != len(refs):
            boundary.fail("snapshot_sources_unavailable")
        latest = (
            select(Record.id, func.max(Record.version).label("version"))
            .where(
                Record.protocol_id == protocol.id, Record.id.in_([r[0] for r in refs])
            )
            .group_by(Record.id)
            .subquery()
        )
        deleted = await db.scalar(
            select(func.count())
            .select_from(Record)
            .join(
                latest,
                and_(Record.id == latest.c.id, Record.version == latest.c.version),
            )
            .where(Record.deleted_at.is_not(None))
        )
        if deleted:
            boundary.fail("snapshot_sources_unavailable")
        for record in records:
            await check_user_permission(
                db, project, user, "read_record", protocol=protocol, record=record
            )


def dictionary_schema(spec):
    allowed = {
        "title",
        "description",
        "type",
        "format",
        "minimum",
        "maximum",
        "enum",
        "const",
        "minItems",
        "maxItems",
        "uniqueItems",
        "unit",
        "units",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "pattern",
        "minLength",
        "maxLength",
        "required",
    }
    result = {k: v for k, v in spec.items() if k in allowed}
    if "properties" in spec:
        result["properties"] = {
            k: dictionary_schema(v) for k, v in spec["properties"].items()
        }
    if "items" in spec:
        result["items"] = dictionary_schema(spec["items"])
    return result


def snapshot_view(snapshot, offset=0):
    rows = [
        {"protocol_id": source["protocol_id"], **row}
        for source in snapshot.content["sources"]
        for row in source["records"]
    ]
    return {
        "snapshot_id": str(snapshot.id),
        "digest": snapshot.digest,
        "contract_version": 1,
        "created_at": snapshot.created_at.isoformat(),
        "expires_at": snapshot.expires_at.isoformat(),
        "selection": snapshot.selection,
        "sources": [
            {k: v for k, v in source.items() if k != "records"}
            for source in snapshot.content["sources"]
        ],
        "total_count": len(rows),
        "items": rows[offset : offset + 50],
        "next_offset": offset + 50 if offset + 50 < len(rows) else None,
        "join_policy": "Sources are separate. Explicit keys, units and cardinality are required for joint computation.",
    }


async def create_snapshot(db, access, args):
    await require_export(db, access)
    selection = args.model_dump(mode="json", exclude={"request_key"})
    fingerprint = boundary.digest(selection)
    existing = await db.scalar(
        select(ExternalSnapshot).where(
            ExternalSnapshot.grant_id == access.grant.id,
            ExternalSnapshot.request_key == args.request_key,
        )
    )
    if existing:
        if existing.request_digest != fingerprint:
            boundary.fail("idempotency_key_conflict", 409)
        await verify_snapshot(db, existing, access.user, access=access)
        return snapshot_view(existing)
    await db.execute(
        delete(ExternalSnapshot).where(
            ExternalSnapshot.user_id == access.user.id,
            ExternalSnapshot.expires_at < boundary.now() - boundary.OPERATION_TTL,
            ~select(ExternalAnalysisSource.run_id)
            .where(ExternalAnalysisSource.snapshot_id == ExternalSnapshot.id)
            .exists(),
        )
    )
    count = await db.scalar(
        select(func.count())
        .select_from(ExternalSnapshot)
        .where(
            ExternalSnapshot.user_id == access.user.id,
            ExternalSnapshot.expires_at > boundary.now(),
        )
    )
    if count >= 20:
        boundary.fail("snapshot_limit", 429)
    contexts = {}
    from app.services.record_analyses import analysis_scope

    for source in sorted(args.sources, key=lambda s: str(s.protocol_id)):
        protocol, _ = await boundary.protocol_context(db, access, source.protocol_id)
        await analysis_scope(db, protocol.id, access.user)
        contexts[source.protocol_id] = protocol
    # One SQL statement captures the latest row and its exact schema for all sources.
    from sqlalchemy import or_

    all_latest = (
        select(Record.id.label("id"), func.max(Record.version).label("version"))
        .where(Record.protocol_id.in_(contexts))
        .group_by(Record.id)
        .subquery()
    )
    from sqlalchemy.orm import aliased

    current = aliased(Record)
    query = (
        select(Record, ProtocolVersion)
        .join(
            ProtocolVersion,
            and_(
                ProtocolVersion.protocol_id == Record.protocol_id,
                ProtocolVersion.version == Record.protocol_version,
            ),
        )
        .join(all_latest, Record.id == all_latest.c.id)
        .join(
            current,
            and_(
                current.id == all_latest.c.id,
                current.version == all_latest.c.version,
            ),
        )
        .where(
            Record.deleted_at.is_(None),
            current.deleted_at.is_(None),
            or_(
                *[
                    and_(
                        Record.protocol_id == s.protocol_id,
                        tuple_(Record.id, Record.version).in_(
                            [(r.id, r.version) for r in s.records]
                        )
                        if s.records
                        else Record.version == all_latest.c.version,
                    )
                    for s in args.sources
                ]
            ),
        )
        .order_by(Record.protocol_id, Record.id)
        .limit(MAX_RECORDS + 1)
    )
    rows = (await db.execute(query)).all()
    if len(rows) > MAX_RECORDS:
        boundary.fail("snapshot_too_large_narrow_selection", 413)
    content = {"contract_version": 1, "sources": []}
    for source in args.sources:
        protocol = contexts[source.protocol_id]
        selected = [(r, v) for r, v in rows if r.protocol_id == protocol.id]
        if source.records and len(selected) != len(source.records):
            boundary.fail("selected_revisions_unavailable")
        if not selected:
            boundary.fail("no_readable_records", 422)
        data, schemas = [], {}
        for record, version in selected:
            await boundary.check_user_permission(
                db,
                access.project,
                access.user,
                "read_record",
                protocol=protocol,
                record=record,
            )
            fields = boundary.external_fields(access, version)
            raw = (record.data or {}).get("var", {})
            values, statuses = {}, {}
            for key in source.fields:
                if any(
                    key == blocked or blocked.startswith(key + ".")
                    for blocked in access.policy.blocked_fields
                ):
                    statuses[key] = "withheld"
                elif key not in version.json_schema.get("vars", {}).get(
                    "properties", {}
                ):
                    statuses[key] = "not_in_schema"
                elif key not in fields:
                    statuses[key] = "unsupported"
                elif key not in raw:
                    statuses[key] = "not_collected"
                elif (
                    boundary.safe_field_value(access, raw[key], fields[key]) != raw[key]
                ):
                    statuses[key] = "withheld"
                else:
                    values[key] = raw[key]
                    statuses[key] = "missing" if raw[key] is None else "available"
            data.append(
                {
                    "record_id": str(record.id),
                    "record_version": record.version,
                    "protocol_version_id": str(version.id),
                    "protocol_version": version.version,
                    "values": values,
                    "field_status": statuses,
                }
            )
            schemas[str(version.id)] = {
                "id": str(version.id),
                "version": version.version,
                "fields": {
                    key: dictionary_schema(spec)
                    for key, spec in fields.items()
                    if key in source.fields
                },
            }
        content["sources"].append(
            {
                "protocol_id": str(protocol.id),
                "name": protocol.name,
                "records": data,
                "schemas": list(schemas.values()),
            }
        )
    if (
        len(json.dumps(content, ensure_ascii=False, allow_nan=False).encode())
        > MAX_SNAPSHOT_BYTES
    ):
        boundary.fail("snapshot_too_large_narrow_selection", 413)
    snapshot = ExternalSnapshot(
        grant_id=access.grant.id,
        project_id=access.project.id,
        user_id=access.user.id,
        request_key=args.request_key,
        request_digest=fingerprint,
        policy_revision=access.policy.revision,
        selection=selection,
        content=content,
        digest=boundary.digest(content),
        created_at=boundary.now(),
        expires_at=boundary.now() + timedelta(hours=24),
    )
    db.add(snapshot)
    await db.flush()
    return snapshot_view(snapshot)


def result_files(params):
    from app.routers.research_materials import material_content_type

    files, total, names = [], 0, set()
    for entry in params.files:
        suffix = PurePosixPath(entry.filename).suffix.lower()
        if (
            entry.filename in names
            or entry.filename in {".", ".."}
            or suffix
            not in {".png", ".jpg", ".jpeg", ".csv", ".json", ".txt", ".md", ".py"}
        ):
            boundary.fail("invalid_result_file", 422)
        names.add(entry.filename)
        try:
            data = base64.b64decode(entry.content_base64, validate=True)
        except (ValueError, binascii.Error):
            boundary.fail("invalid_result_file", 422)
        total += len(data)
        if total > MAX_RESULT_BYTES or hashlib.sha256(data).hexdigest() != entry.sha256:
            boundary.fail("result_file_size_or_digest_mismatch", 422)
        try:
            content_type = material_content_type(data, entry.filename)
            if suffix not in {".png", ".jpg", ".jpeg"}:
                data.decode("utf-8")
        except (ValueError, OSError, UnicodeError):
            boundary.fail("invalid_result_file", 422)
        files.append((entry, data, content_type))
    return files


async def new_operation(
    db, access, *, key, kind, payload, summary, protocol_id=None, version_id=None
):
    project_id = access.project.id if access.project else None
    fingerprint = boundary.digest({"kind": kind, "payload": payload})
    existing = await db.scalar(
        select(ExternalOperation).where(
            ExternalOperation.grant_id == access.grant.id,
            ExternalOperation.request_key == key,
        )
    )
    if existing:
        if (
            existing.project_id or access.grant.project_id
        ) != project_id or existing.digest != fingerprint:
            boundary.fail("idempotency_key_conflict", 409)
        await authorize_operation(db, access, existing)
        view = boundary.operation_view(existing)
        if existing.kind == "meeting_upload" and view["state"] == "pending":
            view["confirmation_url"] = await confirmation_url(db, access, existing)
        return view
    await boundary.expire_operations(db, access.grant.id)
    count = await db.scalar(
        select(func.count())
        .select_from(ExternalOperation)
        .where(
            ExternalOperation.grant_id == access.grant.id,
            ExternalOperation.state.in_(["pending", "approved"]),
        )
    )
    if count >= 10:
        boundary.fail("pending_operation_limit", 429)
    op = ExternalOperation(
        project_id=project_id,
        grant_id=access.grant.id,
        request_key=key,
        kind=kind,
        protocol_id=protocol_id,
        protocol_version_id=version_id,
        policy_revision=access.policy.revision,
        digest=fingerprint,
        payload=payload,
        summary=summary,
        created_at=boundary.now(),
        expires_at=boundary.now() + boundary.OPERATION_TTL,
    )
    db.add(op)
    await db.flush()
    boundary.audit(
        db,
        access.user.id,
        "operation.previewed",
        access.grant.id,
        operation_id=str(op.id),
        digest=op.digest,
        kind=kind,
    )
    return {
        **boundary.operation_view(op),
        "confirmation_url": await confirmation_url(db, access, op),
        "instruction": "The user must review and approve in Platform; this credential cannot approve.",
    }


async def project_analysis_path(db, access):
    from app.models.lab import Lab

    lab = await db.get(Lab, access.project.lab_id)
    return f"{project_browser_path(lab.uid, access.project.uid)}/analysis?view=external"


async def confirmation_url(db, access, op):
    from app.config import config

    if op.kind == "meeting_upload":
        from urllib.parse import quote

        return f"{config.SITE_URL.rstrip('/')}/users/{quote(access.user.username, safe='')}/settings?operation_id={op.id}"
    return f"{config.SITE_URL.rstrip('/')}{await project_analysis_path(db, access)}&operation_id={op.id}"


async def preview_analysis(db, access, params):
    boundary.scope(access, "analysis:write")
    snapshot = await db.get(ExternalSnapshot, params.snapshot_id)
    await verify_snapshot(db, snapshot, access.user, access=access)
    if snapshot.digest != params.snapshot_digest:
        boundary.fail("snapshot_digest_mismatch", 409)
    files = result_files(params)
    if params.rerun_of_id:
        previous = await get_run(db, access.user, params.rerun_of_id, access=access)
        if previous.project_id != access.project.id:
            boundary.fail("analysis_not_found", 404)
    summary = {
        "project_name": access.project.name,
        "title": params.title,
        "snapshot_id": str(snapshot.id),
        "snapshot_digest": snapshot.digest,
        "row_count": sum(len(s["records"]) for s in snapshot.content["sources"]),
        "execution_origin": "external",
        "execution": params.execution,
        "reproducibility": "provided_not_verified"
        if params.environment and any(f.kind == "code" for f in params.files)
        else "incomplete",
        "files": [
            {
                "filename": f.filename,
                "kind": f.kind,
                "sha256": f.sha256,
                "size_bytes": len(data),
            }
            for f, data, _ in files
        ],
    }
    return await new_operation(
        db,
        access,
        key=params.request_key,
        kind="analysis",
        payload=params.model_dump(mode="json"),
        summary=summary,
    )


async def authorize_operation(db, access, op):
    if (
        op.state in ("pending", "approved")
        and boundary.digest({"kind": op.kind, "payload": op.payload}) != op.digest
    ):
        boundary.fail("operation_integrity_failed", 409)
    if op.policy_revision != access.policy.revision:
        boundary.fail("policy_changed_preview_again", 409)
    if op.kind == "meeting_upload":
        from app.services.external_meeting_uploads import authorized_target

        await authorized_target(db, access, op)
        return
    if op.kind == "protocol":
        from app.services.external_protocols import (
            authorize_operation as authorize_protocol,
        )

        return await authorize_protocol(db, access, op)
    if op.kind != "analysis":
        boundary.fail("unsupported_operation", 422)
    boundary.scope(access, "analysis:write")
    snapshot = await db.get(ExternalSnapshot, UUID(op.summary["snapshot_id"]))
    await verify_snapshot(
        db, snapshot, access.user, access=access, allow_expired=op.state == "succeeded"
    )
    if op.state == "succeeded":
        await get_run(db, access.user, UUID(op.result["run_id"]), access=access)


async def get_run(db, user, run_id, *, access=None):
    run = await db.get(AnalysisRun, run_id)
    if run is None or run.engine_version != ENGINE or run.created_by_user_id != user.id:
        boundary.fail("analysis_not_found", 404)
    link = await db.get(ExternalAnalysisSource, run.id)
    if link is None:
        boundary.fail("analysis_integrity_failed", 409)
    snapshot = await db.get(ExternalSnapshot, link.snapshot_id)
    if (
        snapshot is None
        or snapshot.digest != run.source_digest
        or snapshot.project_id != run.project_id
        or snapshot.grant_id != link.grant_id
    ):
        boundary.fail("analysis_source_integrity_failed", 409)
    await verify_snapshot(
        db, snapshot, user, access=access, allow_expired=True, same_grant=False
    )
    from app.services.record_analyses import verify_run_integrity

    verify_run_integrity(run)
    return run


async def execute_analysis(db, access, op):
    if op.kind == "protocol":
        from app.services.external_protocols import execute

        return await execute(db, access, op)
    await authorize_operation(db, access, op)
    if op.state == "succeeded":
        return boundary.operation_view(op)
    if op.state != "approved" or op.expires_at <= boundary.now():
        boundary.fail("operation_not_approved_or_expired", 409)
    params = AnalysisSubmission.model_validate(op.payload)
    snapshot = await db.get(ExternalSnapshot, params.snapshot_id)
    files = result_files(params)
    from app.services.knowledge import assert_research_file_upload_quota

    await assert_research_file_upload_quota(
        db,
        access.user.id,
        sum(len(data) for _, data, _ in files),
        incoming_count=len(files),
    )
    recipe = {
        "contract_version": 1,
        "kind": "external",
        "method": params.method,
        "parameters": params.parameters,
        "environment": params.environment,
        "code": [
            {"filename": f.filename, "sha256": f.sha256}
            for f in params.files
            if f.kind == "code"
        ],
    }
    result = {
        "title": params.title,
        "report": params.report,
        "limitations": params.limitations,
        "execution_origin": "external",
        "execution": params.execution,
        "executor": params.executor,
        "reproducibility": op.summary["reproducibility"],
        "verified_by_platform": False,
        "files": [],
    }
    run = AnalysisRun(
        id=uuid4(),
        project_id=access.project.id,
        protocol_id=None,
        source_scope="project",
        created_by_user_id=access.user.id,
        rerun_of_id=params.rerun_of_id,
        question=params.question,
        recipe=recipe,
        source_selection=snapshot.selection,
        source_snapshot=snapshot.content,
        source_digest=snapshot.digest,
        recipe_digest=boundary.digest(recipe),
        preview_digest=op.digest,
        client_idempotency_key=f"external-{op.id}",
        status="succeeded",
        engine_version=ENGINE,
        started_at=boundary.now(),
        finished_at=boundary.now(),
    )
    outputs = []
    from app.libs.file_storage import (
        default_storage_backend,
        default_storage_namespace,
        delete_file,
        upload_file,
    )

    for entry, data, content_type in files:
        blob = await db.scalar(
            select(ResearchFileBlob).where(
                ResearchFileBlob.checksum_sha256 == entry.sha256
            )
        )
        if blob is None:
            key = f"external-analysis/{uuid4().hex}/{entry.sha256}"
            db.info.setdefault("external_uploaded_keys", []).append(key)
            await upload_file(
                key, io.BytesIO(data), content_type=content_type, length=len(data)
            )
            identity = await db.scalar(
                insert(ResearchFileBlob)
                .values(
                    id=uuid4(),
                    checksum_sha256=entry.sha256,
                    content_type=content_type,
                    size_bytes=len(data),
                    storage_backend=default_storage_backend(),
                    storage_namespace=default_storage_namespace(),
                    storage_object_key=key,
                    extracted_text="",
                )
                .on_conflict_do_nothing(
                    index_elements=[ResearchFileBlob.checksum_sha256]
                )
                .returning(ResearchFileBlob.id)
            )
            if identity is None:
                await delete_file(key)
                db.info["external_uploaded_keys"].remove(key)
            blob = await db.scalar(
                select(ResearchFileBlob).where(
                    ResearchFileBlob.checksum_sha256 == entry.sha256
                )
            )
        output = ExternalAnalysisFile(
            id=uuid4(),
            run_id=run.id,
            blob_id=blob.id,
            filename=entry.filename,
            kind=entry.kind,
        )
        outputs.append(output)
        result["files"].append(
            {
                "id": str(output.id),
                "filename": entry.filename,
                "kind": entry.kind,
                "sha256": entry.sha256,
                "size_bytes": len(data),
            }
        )
    # Ordinary versioned methods, explicitly tagged for external execution.
    previous = (
        await get_run(db, access.user, params.rerun_of_id, access=access)
        if params.rerun_of_id
        else None
    )
    previous_revision = (
        await db.get(AnalysisPipelineRevision, previous.pipeline_revision_id)
        if previous and previous.pipeline_revision_id
        else None
    )
    pipeline = (
        await db.get(
            AnalysisPipeline, previous_revision.pipeline_id, with_for_update=True
        )
        if previous_revision
        else None
    )
    if pipeline is None:
        pipeline = AnalysisPipeline(
            id=uuid4(),
            project_id=access.project.id,
            protocol_id=None,
            source_scope="project",
            created_by_user_id=access.user.id,
            title=params.title,
            current_revision=1,
        )
        db.add(pipeline)
        await db.flush()
    elif previous_revision.recipe_digest != run.recipe_digest:
        pipeline.current_revision += 1
    if previous_revision and previous_revision.recipe_digest == run.recipe_digest:
        revision = previous_revision
    else:
        from app.services.record_analyses import method_revision_digest

        provenance = {
            "analysis_id": str(run.id),
            "engine_version": ENGINE,
            "snapshot_id": str(snapshot.id),
            "source_digest": snapshot.digest,
        }
        provenance["method_digest"] = method_revision_digest(
            recipe, snapshot.selection, provenance
        )
        revision = AnalysisPipelineRevision(
            id=uuid4(),
            pipeline_id=pipeline.id,
            revision=pipeline.current_revision,
            recipe=recipe,
            recipe_digest=run.recipe_digest,
            source_selection=snapshot.selection,
            provenance=provenance,
            created_by_user_id=access.user.id,
        )
        db.add(revision)
        await db.flush()
    run.pipeline_revision_id = revision.id
    result["method"] = {
        "pipeline_id": str(pipeline.id),
        "revision_id": str(revision.id),
        "revision": revision.revision,
    }
    run.result, run.result_digest = result, boundary.digest(result)
    db.add(run)
    await db.flush()
    db.add(
        ExternalAnalysisSource(
            run_id=run.id, snapshot_id=snapshot.id, grant_id=access.grant.id
        )
    )
    db.add_all(outputs)
    op.state, op.payload = "succeeded", {}
    op.result = {
        "run_id": str(run.id),
        "links": [f"{await project_analysis_path(db, access)}&analysis_id={run.id}"],
    }
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
    if name in (
        "list_context_assets",
        "read_context_asset",
        "read_research_file",
        "list_record_files",
    ):
        from app.services.external_context import call as context_call

        return await context_call(db, access, name, args)
    if name == "snapshot_changes":
        return await snapshot_changes(db, access, args)

    if name in ("download_protocol_source", "preview_protocol_candidate"):
        from app.services.external_protocols import call as protocol_call

        return await protocol_call(db, access, name, args)
    if name == "create_snapshot":
        return await create_snapshot(db, access, args)
    if name == "read_snapshot":
        snapshot = await db.get(ExternalSnapshot, args.snapshot_id)
        await verify_snapshot(db, snapshot, access.user, access=access)
        return snapshot_view(snapshot, args.offset)
    if name == "preview_analysis":
        return await preview_analysis(db, access, args)
    if name == "get_external_analysis":
        boundary.scope(access, "analysis:read")
        run = await get_run(db, access.user, args.run_id, access=access)
        return run.as_dict(excludes=["source_snapshot"])
    boundary.fail("unknown_tool", 404)


async def snapshot_changes(db, access, args):
    snapshot = await db.get(ExternalSnapshot, args.snapshot_id)
    await verify_snapshot(
        db, snapshot, access.user, access=access, allow_expired=True, same_grant=False
    )
    changes = []
    for source in snapshot.content["sources"]:
        old = {row["record_id"]: row["record_version"] for row in source["records"]}
        latest = (
            select(Record.id, func.max(Record.version).label("version"))
            .where(Record.protocol_id == UUID(source["protocol_id"]))
            .group_by(Record.id)
            .subquery()
        )
        selection = next(
            s
            for s in snapshot.selection["sources"]
            if s["protocol_id"] == source["protocol_id"]
        )
        query = (
            select(Record)
            .join(
                latest,
                and_(Record.id == latest.c.id, Record.version == latest.c.version),
            )
            .where(Record.deleted_at.is_(None))
        )
        if selection.get("records"):
            query = query.where(Record.id.in_([UUID(i) for i in old]))
        rows = (await db.scalars(query.limit(MAX_RECORDS + 1))).all()
        if len(rows) > MAX_RECORDS:
            boundary.fail("change_set_too_large_narrow_selection", 413)
        protocol, _ = await boundary.protocol_context(
            db, access, UUID(source["protocol_id"])
        )
        for record in rows:
            await boundary.check_user_permission(
                db,
                access.project,
                access.user,
                "read_record",
                protocol=protocol,
                record=record,
            )
            before = old.get(str(record.id))
            if before != record.version:
                changes.append(
                    {
                        "protocol_id": str(protocol.id),
                        "record_id": str(record.id),
                        "previous_version": before,
                        "current_version": record.version,
                        "kind": "added" if before is None else "revised",
                    }
                )
    return {
        "snapshot_id": str(snapshot.id),
        "snapshot_digest": snapshot.digest,
        "changed": bool(changes),
        "total_count": len(changes),
        "items": changes[args.offset : args.offset + 50],
        "next_offset": args.offset + 50 if args.offset + 50 < len(changes) else None,
        "consistency": "live_notification; create a new snapshot before analysis",
    }
