"""External research against real SQL/storage, synthetic measurements and both auth boundaries."""

import asyncio
import base64
import hashlib
import os
import zipfile
from uuid import UUID, uuid4

import pytest
from sqlalchemy import update

from app.models.analysis import AnalysisRun
from app.models.external_access import ExternalAccessPolicy
from app.models.record import Record
from app.services import external_access as service
from tests.test_external_access_postgres import (
    approve,
    browser,
    call,
    client,
    delegated,
    grant,
    isolated_executor,  # noqa: F401 -- shared pytest fixture
    seed,
)
from tests.test_record_analysis_postgres import add_record, database

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Isolated PostgreSQL required",
)


def request_snapshot(scope, **kw):
    return {
        "sources": [
            {"protocol_id": str(scope.protocol.id), "fields": ["value", "group"]}
        ],
        "request_key": uuid4().hex,
        **kw,
    }


def submission(snapshot, **kw):
    code = b'print("Synthetic mean = 3")\n'
    return {
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_digest": snapshot["digest"],
        "request_key": uuid4().hex,
        "title": "Synthetic comparison",
        "question": "What is the mean?",
        "report": "Two synthetic observations: 2 and 4. Mean = 3.",
        "method": "Arithmetic mean",
        "execution": "computed",
        "executor": "Synthetic Python client",
        "parameters": {},
        "environment": {"python": "3.13"},
        "limitations": "Synthetic data only; not a scientific claim.",
        "files": [
            {
                "filename": "analysis.py",
                "kind": "code",
                "content_base64": base64.b64encode(code).decode(),
                "sha256": hashlib.sha256(code).hexdigest(),
            }
        ],
        **kw,
    }


def test_snapshot_report_approval_files_and_rerun_are_atomic_and_private():
    async def scenario():
        async with database() as sessions:
            scope = await seed(sessions)
            await add_record(sessions, scope, 2)
            await add_record(sessions, scope, 4, number=2)
            async with client(sessions) as http:
                token = (await grant(http, scope))["token"]
                request = request_snapshot(scope)
                response = await call(http, token, "create_snapshot", **request)
                assert response.status_code == 200, response.text
                snapshot = response.json()
                assert [r["values"]["value"] for r in snapshot["items"]] == [
                    2,
                    4,
                ] or sorted(r["values"]["value"] for r in snapshot["items"]) == [2, 4]
                assert (
                    sum(r["values"]["value"] for r in snapshot["items"])
                    / snapshot["total_count"]
                    == 3
                )
                retry = await call(http, token, "create_snapshot", **request)
                assert retry.json()["digest"] == snapshot["digest"]
                response = await call(
                    http, token, "preview_analysis", **submission(snapshot)
                )
                assert response.status_code == 200, response.text
                op = response.json()
                assert (
                    await call(http, token, "execute_operation", operation_id=op["id"])
                ).status_code == 409
                assert (
                    await http.post(
                        f"/external-access/operations/{op['id']}/decision",
                        headers=delegated(token),
                        json={"digest": op["digest"], "approve": True},
                    )
                ).status_code != 200
                await approve(http, scope, op)
                execution = await call(
                    http, token, "execute_operation", operation_id=op["id"]
                )
                assert execution.status_code == 200, execution.text
                run_id = execution.json()["result"]["run_id"]
                repeat = await call(
                    http, token, "execute_operation", operation_id=op["id"]
                )
                assert repeat.json() == execution.json()
                report = await http.get(
                    f"/external-access/analyses/{run_id}", headers=browser(scope.owner)
                )
                assert report.status_code == 200, report.text
                result = report.json()["result"]
                assert (
                    result["execution_origin"] == "external"
                    and result["verified_by_platform"] is False
                )
                assert result["reproducibility"] == "provided_not_verified"
                file_id = result["files"][0]["id"]
                download = await http.get(
                    f"/external-access/analyses/{run_id}/files/{file_id}",
                    headers=browser(scope.owner),
                )
                assert download.status_code == 200, download.text
                assert (
                    hashlib.sha256(download.content).hexdigest()
                    == result["files"][0]["sha256"]
                )
                assert "attachment" in download.headers["content-disposition"]
                assert (
                    await http.get(
                        f"/external-access/analyses/{run_id}",
                        headers=browser(scope.outsider),
                    )
                ).status_code == 404
                # A new run preserves its predecessor and records the declared reproducibility gap.
                await add_record(sessions, scope, 6, number=3)
                next_snapshot = (
                    await call(
                        http, token, "create_snapshot", **request_snapshot(scope)
                    )
                ).json()
                next_op = (
                    await call(
                        http,
                        token,
                        "preview_analysis",
                        **submission(
                            next_snapshot, rerun_of_id=run_id, files=[], environment={}
                        ),
                    )
                ).json()
                await approve(http, scope, next_op)
                next_run = (
                    await call(
                        http, token, "execute_operation", operation_id=next_op["id"]
                    )
                ).json()
                assert next_run["result"]["run_id"] != run_id
                async with sessions() as db:
                    original = await db.get(AnalysisRun, UUID(run_id))
                    rerun = await db.get(
                        AnalysisRun, UUID(next_run["result"]["run_id"])
                    )
                    assert rerun.rerun_of_id == original.id
                    assert original.result["report"] == result["report"]
                    assert rerun.result["reproducibility"] == "incomplete"
                    assert (
                        rerun.result["method"]["pipeline_id"]
                        == original.result["method"]["pipeline_id"]
                    )
                    assert rerun.result["method"]["revision"] == 2

    asyncio.run(scenario())


def test_snapshot_is_immutable_and_failed_confirmation_leaves_no_result(monkeypatch):
    from sqlalchemy import func, select
    from sqlalchemy.exc import DBAPIError

    from app.models.external_research import ExternalSnapshot

    async def scenario():
        async with database() as sessions, client(sessions) as http:
            scope = await seed(sessions)
            await add_record(sessions, scope, 2)
            token = (await grant(http, scope))["token"]
            snapshot = (
                await call(http, token, "create_snapshot", **request_snapshot(scope))
            ).json()
            async with sessions() as db:
                with pytest.raises(DBAPIError, match="immutable"):
                    await db.execute(
                        update(ExternalSnapshot)
                        .where(ExternalSnapshot.id == UUID(snapshot["snapshot_id"]))
                        .values(digest="0" * 64)
                    )
                await db.rollback()
            op = (
                await call(http, token, "preview_analysis", **submission(snapshot))
            ).json()
            await approve(http, scope, op)
            original = service.audit

            def failing_audit(db, user_id, event, *args, **kwargs):
                if event == "operation.executed":
                    raise RuntimeError("Synthetic result transaction failure")
                return original(db, user_id, event, *args, **kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(service, "audit", failing_audit)
                with pytest.raises(RuntimeError, match="Synthetic result"):
                    await call(http, token, "execute_operation", operation_id=op["id"])
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(AnalysisRun)
                        .where(AnalysisRun.project_id == scope.project.id)
                    )
                    == 0
                )
            retry = await call(http, token, "execute_operation", operation_id=op["id"])
            assert retry.status_code == 200, retry.text

    asyncio.run(scenario())


def test_external_research_migration_roundtrip_in_isolated_schema():
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    from app.models.external_research import (
        ExternalAnalysisFile,
        ExternalAnalysisSource,
        ExternalOAuthClient,
        ExternalOAuthCode,
        ExternalSnapshot,
    )

    async def scenario():
        async with database() as sessions, sessions() as db:
            connection = await db.connection()

            def roundtrip(conn):
                schema = "external_roundtrip_" + uuid4().hex
                conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
                conn.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
                legacy = import_module("migrations.versions.0078_external_agent_access")
                current = import_module("migrations.versions.0082_external_research")
                with Operations.context(MigrationContext.configure(conn)):
                    legacy.upgrade()
                    current.upgrade()
                    current.downgrade()
                    current.upgrade()
                for model in [
                    ExternalSnapshot,
                    ExternalAnalysisSource,
                    ExternalAnalysisFile,
                    ExternalOAuthClient,
                    ExternalOAuthCode,
                ]:
                    assert {
                        c["name"]
                        for c in inspect(conn).get_columns(
                            model.__tablename__, schema=schema
                        )
                    } == set(model.__table__.c.keys())

            await connection.run_sync(roundtrip)
            await db.rollback()

    asyncio.run(scenario())


def test_snapshot_pagination_freezes_revisions_and_withheld_is_not_null():
    async def scenario():
        async with database() as sessions:
            scope = await seed(sessions)
            rows = [
                await add_record(sessions, scope, i, number=i + 1) for i in range(60)
            ]
            async with client(sessions) as http:
                token = (await grant(http, scope))["token"]
                async with sessions() as db:
                    policy = await db.get(ExternalAccessPolicy, scope.lab.id)
                    policy.blocked_fields = ["group"]
                    policy.revision += 1
                    await db.commit()
                snapshot = (
                    await call(
                        http, token, "create_snapshot", **request_snapshot(scope)
                    )
                ).json()
                assert snapshot["total_count"] == 60 and snapshot["next_offset"] == 50
                assert all(
                    "group" not in r["values"]
                    and r["field_status"]["group"] == "withheld"
                    for r in snapshot["items"]
                )
                await add_record(
                    sessions, scope, 999, record_id=rows[-1].id, revision=2, number=60
                )
                await add_record(sessions, scope, 88, number=61)
                page = await call(
                    http,
                    token,
                    "read_snapshot",
                    snapshot_id=snapshot["snapshot_id"],
                    offset=50,
                )
                assert page.status_code == 200, page.text
                combined = snapshot["items"] + page.json()["items"]
                assert sorted(r["values"]["value"] for r in combined) == list(range(60))
                assert len({r["record_id"] for r in combined}) == 60
                assert page.json()["digest"] == snapshot["digest"]
                assert page.json()["next_offset"] is None
                async with sessions() as db:
                    await db.execute(
                        update(Record)
                        .where(Record.id == rows[-1].id, Record.version == 2)
                        .values(deleted_at=service.now().replace(tzinfo=None))
                    )
                    await db.commit()
                assert (
                    await call(
                        http,
                        token,
                        "read_snapshot",
                        snapshot_id=snapshot["snapshot_id"],
                    )
                ).status_code == 403

    asyncio.run(scenario())


def test_old_tokens_export_permission_revocation_and_stale_confirmation():
    async def scenario():
        async with database() as sessions:
            scope = await seed(sessions)
            await add_record(sessions, scope, 2)
            async with client(sessions) as http:
                old = (
                    await grant(http, scope, scopes=["protocols:read", "records:read"])
                )["token"]
                assert (
                    await call(http, old, "create_snapshot", **request_snapshot(scope))
                ).status_code == 403
                analyst = (await grant(http, scope, user=scope.analyst))["token"]
                assert (
                    await call(
                        http, analyst, "create_snapshot", **request_snapshot(scope)
                    )
                ).status_code == 403
                owner_grant = await grant(http, scope)
                token = owner_grant["token"]
                snapshot = (
                    await call(
                        http, token, "create_snapshot", **request_snapshot(scope)
                    )
                ).json()
                bad = submission(snapshot)
                bad["files"][0]["sha256"] = "0" * 64
                assert (
                    await call(http, token, "preview_analysis", **bad)
                ).status_code == 422
                op = (
                    await call(http, token, "preview_analysis", **submission(snapshot))
                ).json()
                await approve(http, scope, op)
                async with sessions() as db:
                    policy = await db.get(ExternalAccessPolicy, scope.lab.id)
                    policy.revision += 1
                    await db.commit()
                assert (
                    await call(http, token, "execute_operation", operation_id=op["id"])
                ).status_code == 409
                assert (
                    await call(
                        http,
                        token,
                        "read_snapshot",
                        snapshot_id=snapshot["snapshot_id"],
                    )
                ).status_code == 409
                await http.delete(
                    f"/external-access/grants/{owner_grant['grant']['id']}",
                    headers=browser(scope.owner),
                )
                assert (await call(http, token, "access_context")).status_code == 401

    asyncio.run(scenario())


def test_protocol_candidate_validates_confirms_and_publishes_exact_source(monkeypatch):
    async def scenario():
        from io import BytesIO
        from pathlib import Path

        from sqlalchemy import select

        from app.config import config
        from app.models.protocol_version import ProtocolVersion
        from app.services.external_protocols import archive_bytes

        async with database() as sessions:
            scope = await seed(sessions)
            record = await add_record(sessions, scope, 2)
            root = Path(config.PROTOCOL_DIR) / scope.version.package_name
            files = {p.name: p.read_text() for p in root.iterdir() if p.is_file()}
            async with sessions() as db:
                version = await db.get(ProtocolVersion, scope.version.id)
                raw = archive_bytes(files)
                await version.upload_package(BytesIO(raw), length=len(raw))
            async with client(sessions) as http:
                token = (await grant(http, scope))["token"]
                source = await call(
                    http,
                    token,
                    "download_protocol_source",
                    protocol_id=str(scope.protocol.id),
                    version="1.0.0",
                    format="aira",
                )
                assert source.status_code == 200, source.text
                assert (
                    hashlib.sha256(
                        base64.b64decode(source.json()["content_base64"])
                    ).hexdigest()
                    == source.json()["sha256"]
                )
                files["protocol.toml"] = files["protocol.toml"].replace(
                    '"1.0.0"', '"1.1.0"'
                )
                files["protocol.aimd"] += '\n{{var|note: str = ""}}\n'
                args = {
                    "request_key": uuid4().hex,
                    "protocol_id": str(scope.protocol.id),
                    "base_version_id": str(scope.version.id),
                    "files": files,
                }
                op_response = await call(
                    http, token, "preview_protocol_candidate", **args
                )
                assert op_response.status_code == 200, op_response.text
                op = op_response.json()
                assert op["summary"]["validation"] == "static_and_executor_passed"
                assert op["summary"]["records_changed"] == 0
                assert (
                    await call(http, token, "execute_operation", operation_id=op["id"])
                ).status_code == 409
                await approve(http, scope, op)
                original_audit = service.audit

                def failing_receipt(db, user_id, event, *args, **kwargs):
                    if event == "operation.executed":
                        raise RuntimeError("Synthetic publication receipt failure")
                    return original_audit(db, user_id, event, *args, **kwargs)

                with monkeypatch.context() as patch:
                    patch.setattr(service, "audit", failing_receipt)
                    with pytest.raises(RuntimeError, match="Synthetic publication"):
                        await call(
                            http, token, "execute_operation", operation_id=op["id"]
                        )
                async with sessions() as db:
                    assert (
                        await db.scalar(
                            select(ProtocolVersion.id).where(
                                ProtocolVersion.protocol_id == scope.protocol.id,
                                ProtocolVersion.version == "1.1.0",
                            )
                        )
                        is None
                    )
                executed = await call(
                    http, token, "execute_operation", operation_id=op["id"]
                )
                assert executed.status_code == 200, executed.text
                assert executed.json()["result"]["version"] == "1.1.0"
                exported = await call(
                    http,
                    token,
                    "download_protocol_source",
                    protocol_id=str(scope.protocol.id),
                    version="1.1.0",
                    format="zip",
                )
                with zipfile.ZipFile(
                    BytesIO(base64.b64decode(exported.json()["content_base64"]))
                ) as package:
                    assert set(package.namelist()) == set(files)
                    assert {
                        name: package.read(name).decode() for name in package.namelist()
                    } == files
                repeated = await call(
                    http, token, "execute_operation", operation_id=op["id"]
                )
                assert repeated.json() == executed.json()
                async with sessions() as db:
                    old_record = await db.scalar(
                        select(Record).where(Record.id == record.id)
                    )
                    assert old_record.protocol_version == "1.0.0"
                    latest = await db.scalar(
                        select(ProtocolVersion).where(
                            ProtocolVersion.protocol_id == scope.protocol.id,
                            ProtocolVersion.version == "1.1.0",
                        )
                    )
                    assert "note" in latest.json_schema["vars"]["properties"]
                stale = await call(
                    http,
                    token,
                    "preview_protocol_candidate",
                    **{**args, "request_key": uuid4().hex},
                )
                assert stale.status_code == 409
                malicious = await call(
                    http,
                    token,
                    "preview_protocol_candidate",
                    request_key=uuid4().hex,
                    files={**files, ".env": "SECRET=not-a-real-secret"},
                )
                assert malicious.status_code == 422
                read_only = (await grant(http, scope, scopes=["protocols:read"]))[
                    "token"
                ]
                assert (
                    await call(
                        http,
                        read_only,
                        "download_protocol_source",
                        protocol_id=str(scope.protocol.id),
                        version="1.0.0",
                    )
                ).status_code == 403

    asyncio.run(scenario())


def test_context_files_and_nested_values_need_explicit_scopes_and_current_access():
    async def scenario():
        from sqlalchemy import select

        from app.models.knowledge import (
            KnowledgeItem,
            OwnerScope,
            ResearchFile,
            ResearchFileAccessAudit,
        )
        from app.models.protocol_version import ProtocolVersion
        from app.models.research_document import ResearchDocument
        from app.models.research_log import ResearchLogEntry
        from app.routers.research_materials import persist_material
        from app.services.knowledge import resolve_scope

        async with database() as sessions:
            scope = await seed(sessions)
            record = await add_record(sessions, scope, 3)
            async with sessions() as db:
                item = KnowledgeItem(
                    scope_type="project",
                    lab_id=scope.lab.id,
                    project_id=scope.project.id,
                    visibility="project",
                    title="Synthetic note",
                    body="Synthetic context " * 2000,
                    kind="note",
                    state="draft",
                    created_by_user_id=scope.owner.id,
                )
                hidden = KnowledgeItem(
                    scope_type="personal",
                    owner_user_id=scope.owner.id,
                    visibility="private",
                    title="Private synthetic note",
                    body="Private",
                    kind="note",
                    state="draft",
                    created_by_user_id=scope.owner.id,
                )
                doc = ResearchLogEntry(
                    scope_type="project",
                    lab_id=scope.lab.id,
                    project_id=scope.project.id,
                    title="Synthetic document",
                    kind="progress",
                    body="## Synthetic plan",
                    created_by_user_id=scope.owner.id,
                    occurred_at=service.now(),
                )
                db.add_all([item, hidden, doc])
                await db.flush()
                db.add(ResearchDocument(id=doc.id))
                material_scope = await resolve_scope(
                    db,
                    scope.owner,
                    scope_type=OwnerScope.PROJECT,
                    lab_id=scope.lab.id,
                    project_id=scope.project.id,
                    capability="knowledge.import",
                )
                content = b"synthetic,data\n" * 25000
                file, blob, _ = await persist_material(
                    db,
                    scope.owner,
                    material_scope,
                    filename="synthetic.csv",
                    data=content,
                    source_note="Synthetic",
                    occurred_at=None,
                    request_key=uuid4(),
                    uploaded_keys=[],
                )
                pv = await db.get(ProtocolVersion, scope.version.id)
                pv.json_schema = {
                    "vars": {
                        "type": "object",
                        "properties": {
                            "value": {"type": "number"},
                            "nested": {
                                "type": "object",
                                "properties": {"count": {"type": "integer"}},
                                "additionalProperties": False,
                            },
                        },
                    }
                }
                await db.execute(
                    update(Record)
                    .where(Record.id == record.id)
                    .values(data={"var": {"value": 3, "nested": {"count": 2}}})
                )
                await db.commit()
            async with client(sessions) as http:
                token = (await grant(http, scope))["token"]
                readonly = (
                    await grant(
                        http,
                        scope,
                        scopes=["protocols:read", "records:read", "records:export"],
                    )
                )["token"]
                assert (
                    await call(http, readonly, "list_context_assets", kind="knowledge")
                ).status_code == 403
                listing = (
                    await call(http, token, "list_context_assets", kind="knowledge")
                ).json()
                assert [x["id"] for x in listing["items"]] == [str(item.id)]
                assert (
                    await call(
                        http,
                        token,
                        "read_context_asset",
                        kind="knowledge",
                        id=str(hidden.id),
                    )
                ).status_code == 404
                page1 = (
                    await call(
                        http,
                        token,
                        "read_context_asset",
                        kind="knowledge",
                        id=str(item.id),
                    )
                ).json()
                assert page1["next_offset"] == 16000
                assert (
                    await call(
                        http,
                        token,
                        "read_context_asset",
                        kind="knowledge",
                        id=str(item.id),
                        offset=16000,
                    )
                ).status_code == 409
                page2 = (
                    await call(
                        http,
                        token,
                        "read_context_asset",
                        kind="knowledge",
                        id=str(item.id),
                        offset=16000,
                        expected_digest=page1["digest"],
                    )
                ).json()
                assert page1["body"] + page2["body"] == item.body[:32000]
                assert (
                    await call(
                        http,
                        token,
                        "read_context_asset",
                        kind="document",
                        id=str(doc.id),
                    )
                ).json()["body"] == doc.body
                parts, offset = [], 0
                while True:
                    response = await call(
                        http,
                        token,
                        "read_research_file",
                        kind="research",
                        file_id=str(file.id),
                        expected_sha256=blob.checksum_sha256,
                        offset=offset,
                    )
                    assert response.status_code == 200, response.text
                    chunk = response.json()
                    parts.append(base64.b64decode(chunk["content_base64"]))
                    offset = chunk["next_offset"]
                    if offset is None:
                        break
                assert b"".join(parts) == content
                base = request_snapshot(
                    scope,
                    sources=[
                        {
                            "protocol_id": str(scope.protocol.id),
                            "fields": ["value", "nested"],
                        }
                    ],
                )
                basic = (await call(http, readonly, "create_snapshot", **base)).json()
                assert basic["items"][0]["field_status"]["nested"] == "unsupported"
                full = (await call(http, token, "create_snapshot", **base)).json()
                assert full["items"][0]["values"]["nested"] == {"count": 2}
                await add_record(sessions, scope, 5, number=2)
                changed = (
                    await call(
                        http, token, "snapshot_changes", snapshot_id=full["snapshot_id"]
                    )
                ).json()
                assert changed["changed"] and changed["items"][0]["kind"] == "added"
                async with sessions() as db:
                    assert await db.scalar(
                        select(ResearchFileAccessAudit.id).where(
                            ResearchFileAccessAudit.research_file_id == file.id
                        )
                    )
                    await db.execute(
                        update(ResearchFile)
                        .where(ResearchFile.id == file.id)
                        .values(archived_at=service.now())
                    )
                    await db.commit()
                assert (
                    await call(
                        http,
                        token,
                        "read_research_file",
                        kind="research",
                        file_id=str(file.id),
                        expected_sha256=blob.checksum_sha256,
                    )
                ).status_code == 404

    asyncio.run(scenario())
