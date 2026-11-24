"""The Record columns and existing file references accepted by delegated imports."""

import csv
import io
from uuid import UUID

from fastapi import BackgroundTasks, UploadFile
from sqlalchemy import select

from app.models.airalogy_file import AiralogyFile
from app.services import external_access as boundary
from app.services.external_context import record_files
from app.services.external_research_contracts import RecordFiles
from app.services.record_imports import MAX_IMPORT_ROWS
from app.services.workflow_files import authorized_file, file_ids


def import_file_fields(access, version):
    fields = {}
    for key, schema in (
        version.json_schema.get("vars", {}).get("properties", {}).items()
    ):
        if any(
            b == key or b.startswith(key + ".") for b in access.policy.blocked_fields
        ):
            continue
        spec = boundary.primitive_schema(schema)
        if not isinstance(spec, dict):
            continue
        marker = spec.get("airalogy_type", spec.get("airalogy_built_in_type"))
        if marker == "FileId" and spec.get("type") in ("string", ["string", "null"]):
            fields[key] = spec
    return fields


def execution_columns(version, blocked=()):
    columns = []
    for section in ("step", "check"):
        for field in (version.fields or {}).get(section + "s") or []:
            if not isinstance(field, dict) or not isinstance(field.get("name"), str):
                continue
            prefix = f"{section}.{field['name']}."
            if field["name"] in blocked or prefix[:-1] in blocked:
                continue
            if (
                section == "check" or field.get("check")
            ) and prefix + "checked" not in blocked:
                columns.append(prefix + "checked")
            if prefix + "annotation" not in blocked:
                columns.append(prefix + "annotation")
    return columns


def import_contract(access, version):
    schema = version.json_schema.get("vars") or {}
    properties = schema.get("properties", {})
    variables = boundary.external_fields(access, version)
    files = import_file_fields(access, version)
    has_files = "files:read" in access.grant.scopes
    required = set(schema.get("required", []))
    reason = None
    if properties.keys() - variables.keys() - files.keys():
        reason = "restricted_or_complex_protocol_use_platform"
    elif not has_files and required.intersection(files):
        reason = "files_scope_required"
    columns = [
        f"var.{key}"
        for key in properties
        if key in variables or (has_files and key in files)
    ]
    columns.extend(execution_columns(version, access.policy.blocked_fields))
    output = io.StringIO(newline="")
    csv.writer(output).writerow(columns)
    return output.getvalue(), {
        "supported": reason is None,
        "reason": reason,
        "file_fields": [
            {
                "id": key,
                "title": spec.get("title") or key,
                "required": key in required,
                "file_extension": spec.get("file_extension"),
            }
            for key, spec in files.items()
            if has_files
        ],
    }


def csv_file_values(text, files, execution):
    """Remember only explicit file cells so model defaults cannot attach a different file."""
    if text is None or len(text.encode()) > boundary.MAX_CSV_BYTES:
        boundary.fail("csv_required_or_too_large", 422)
    try:
        reader = csv.reader(
            io.StringIO(text.removeprefix("\ufeff"), newline=""), strict=True
        )
        headers = next(reader, [])
        if not headers or any(
            not (h.startswith("var.") or h in execution) for h in headers
        ):
            boundary.fail("use_canonical_csv_template", 422)
        positions = [
            (i, h[4:])
            for i, h in enumerate(headers)
            if h.startswith("var.") and h[4:] in files
        ]
        rows = []
        for row in reader:
            if not row:
                continue
            if len(rows) >= MAX_IMPORT_ROWS:
                boundary.fail("too_many_rows", 422)
            supplied = {}
            for i, key in positions:
                if i >= len(row) or not row[i].strip():
                    continue
                supplied[key] = row[i]
            rows.append(supplied)
        return rows
    except csv.Error:
        boundary.fail("invalid_csv", 422)


async def authorize_import_files(db, access, protocol, files, rows, sources):
    cells = {(key, ref) for row in rows for key, ref in row.items()}
    if not cells and not sources:
        return
    boundary.scope(access, "files:read")
    ids = set()
    for key, ref in cells:
        parts = ref.split(".")
        if len(parts) != 5 or parts[:3] != ["airalogy", "id", "file"]:
            boundary.fail("canonical_file_id_required", 422)
        try:
            ids.add(UUID(parts[3]))
        except ValueError:
            boundary.fail("canonical_file_id_required", 422)
        extension = files[key].get("file_extension")
        if extension and extension.lower() != parts[4].lower():
            boundary.fail("file_extension_mismatch", 422)
    # An upload may be used before its first Record exists. For another user's
    # file, require a readable source Record and its attachment/export scopes.
    shared = set()
    for source in set(sources):
        _, readable = await record_files(
            db,
            access,
            RecordFiles(protocol_id=protocol.id, parent_id=source),
            requested_ids=ids,
        )
        shared.update(file.id for file in readable)
    stored = (
        await db.scalars(
            select(AiralogyFile).where(
                AiralogyFile.protocol_id == protocol.id,
                AiralogyFile.id.in_(ids),
            )
        )
    ).all()
    if {file.airalogy_id for file in stored} != {ref for _, ref in cells}:
        boundary.fail("import_file_unavailable")
    for file in stored:
        if file.project_id not in (None, access.project.id) or (
            file.user_id != access.user.id and file.id not in shared
        ):
            boundary.fail("import_file_unavailable")
        await authorized_file(db, file, access.user)


async def import_records(db, access, protocol, version, args, *, preview=True):
    from app.routers.records import import_records_transaction

    files = import_file_fields(access, version)
    schema = version.json_schema.get("vars") or {}
    variables = boundary.external_fields(access, version)
    if schema.get("properties", {}).keys() - variables.keys() - files.keys():
        boundary.fail("restricted_or_complex_protocol_use_platform", 422)
    if files.keys() & set(schema.get("required", [])):
        boundary.scope(access, "files:read")
    rows = csv_file_values(
        args.csv, files, set(execution_columns(version, access.policy.blocked_fields))
    )
    await authorize_import_files(
        db, access, protocol, files, rows, args.source_record_ids or []
    )

    def check_normalized(records):
        if len(records) != len(rows):
            boundary.fail("record_import_count_changed", 422)
        for record, supplied in zip(records, rows, strict=True):
            data = record["data"]
            variables = data["var"]
            for key in files:
                if variables.get(key) != supplied.get(key):
                    boundary.fail("import_file_value_changed", 422)
            other = {k: v for k, v in variables.items() if k not in files}
            if any(file_ids({**data, "var": other})):
                boundary.fail("file_reference_requires_file_field", 422)

    return await import_records_transaction(
        protocol.id,
        db,
        access.user,
        BackgroundTasks(),
        UploadFile(filename="records.csv", file=io.BytesIO(args.csv.encode())),
        input_format="csv",
        include_template_defaults=False,
        preview=preview,
        commit=False,
        executor_credentials=False,
        validate_imported=check_normalized,
    )
