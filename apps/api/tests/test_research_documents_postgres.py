"""Real scope/transaction/revision tests; synthetic data in a dedicated database."""

import asyncio
import io
import os
from uuid import UUID, uuid4

import pytest
from app.models.knowledge import OwnerScope
from app.models.research_document import ResearchDocumentSubmission
from app.models.research_log import ResearchLogRevision, ResearchLogScope
from app.routers import research_documents as api
from app.routers import research_materials as materials
from app.services.research_document_archive import read_document_archive
from fastapi import HTTPException, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from tests.test_record_analysis_postgres import database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"),
    reason="Isolated migrated PostgreSQL required",
)


def test_document_lifecycle_authorization_and_immutable_results():
    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            key = uuid4()
            create = api.DocumentCreate(
                id=key,
                scope_type="project",
                project_id=scope.project.id,
                title="Synthetic experiment",
                body='{{var|temperature: float, unit="C"}}',
            )
            async with sessions() as db:
                doc = await api.create_document(create, scope.recorder, db)
                assert doc["revision"] == 1
                assert (await api.create_document(create, scope.recorder, db))[
                    "id"
                ] == str(key)
                with pytest.raises(HTTPException) as denied:
                    await api.get_document(key, scope.outsider, db)
                assert denied.value.status_code in (403, 404)
                with pytest.raises(HTTPException):
                    await api.update_document(
                        key,
                        api.DocumentUpdate(title="Other author", expected_revision=1),
                        scope.owner,
                        db,
                    )
                await db.rollback()
            async with sessions() as db:
                with pytest.raises(HTTPException) as invalid:
                    await api.submit_document(
                        key,
                        api.RevisionRequest(expected_revision=1),
                        scope.recorder,
                        db,
                    )
                assert invalid.value.status_code == 422
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchDocumentSubmission)
                        .where(ResearchDocumentSubmission.document_id == key)
                    )
                    == 0
                )
            update = api.DocumentUpdate(
                title="Synthetic experiment",
                body=create.body,
                record_data={"var": {"temperature": 20}},
                expected_revision=1,
            )
            async with sessions() as db:
                doc = await api.update_document(key, update, scope.recorder, db)
                assert doc["revision"] == 2
                preview = await api.submit_document(
                    key, api.RevisionRequest(expected_revision=2), scope.recorder, db
                )
                request = api.RevisionRequest(
                    expected_revision=2, preview_digest=preview["preview_digest"]
                )
                receipt = await api.submit_document(key, request, scope.recorder, db)
                assert receipt == await api.submit_document(
                    key, request, scope.recorder, db
                )
            async with sessions() as db:
                with pytest.raises(HTTPException) as stale:
                    await api.update_document(key, update, scope.recorder, db)
                assert stale.value.status_code == 409
                await db.rollback()
            changed = api.DocumentUpdate(
                title=create.title,
                body='{{var|temperature: float, unit="F"}}',
                record_data=update.record_data,
                expected_revision=2,
            )
            async with sessions() as db:
                with pytest.raises(HTTPException) as review:
                    await api.update_document(key, changed, scope.recorder, db)
                assert review.value.detail["code"] == "definition_review_required"
                await db.rollback()
            async with sessions() as db:
                preview = await api.preview_document(key, changed, scope.recorder, db)
                changed.preview_digest = preview["preview_digest"]
                doc = await api.update_document(key, changed, scope.recorder, db)
                assert doc["state"] == "draft"
                original = await db.get(
                    ResearchDocumentSubmission, UUID(receipt["submission_id"])
                )
                assert original.snapshot["content"]["body"] == create.body
                assert (
                    original.snapshot["content"]["record_data"]["var"]["temperature"]
                    == 20
                )
                with pytest.raises(DBAPIError):
                    async with db.begin_nested():
                        await db.execute(
                            text(
                                "UPDATE research_document_submissions SET digest='tampered' WHERE id=:id"
                            ),
                            {"id": original.id},
                        )
                restoration = await api.restore_document(
                    key, 2, api.RevisionRequest(expected_revision=3), scope.recorder, db
                )
                restored = await api.restore_document(
                    key,
                    2,
                    api.RevisionRequest(
                        expected_revision=3,
                        preview_digest=restoration["preview_digest"],
                    ),
                    scope.recorder,
                    db,
                )
                assert restored["revision"] == 4 and restored["body"] == create.body
                duplicate = await api.create_document(
                    api.DocumentCreate(
                        scope_type="project",
                        project_id=scope.project.id,
                        title="Repeat",
                        source_document_id=key,
                    ),
                    scope.recorder,
                    db,
                )
                assert not duplicate["record_data"] and not duplicate["file_ids"]
                assert duplicate["origin"]["revision"] == 4
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ResearchLogRevision)
                        .where(ResearchLogRevision.log_entry_id == key)
                    )
                    == 4
                )
            async with sessions() as db:
                personal = await api.create_document(
                    api.DocumentCreate(scope_type="personal", title="Private note"),
                    scope.owner,
                    db,
                )
                with pytest.raises(HTTPException) as private:
                    await api.get_document(UUID(personal["id"]), scope.outsider, db)
                assert private.value.status_code == 404

    asyncio.run(exercise())


def test_material_and_archive_roundtrip_atomicity(monkeypatch):
    blobs = {}

    async def upload(key, stream, **kwargs):
        blobs[key] = stream.read()

    async def download(key, **kwargs):
        return blobs[key]

    async def remove(key, **kwargs):
        blobs.pop(key, None)

    monkeypatch.setattr(materials, "upload_file", upload)
    monkeypatch.setattr(materials, "delete_file", remove)
    monkeypatch.setattr(materials, "get_file_content", download)
    monkeypatch.setattr(api, "get_file_content", download)

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            raw = ("Synthetic original " + uuid4().hex).encode()
            async with sessions() as db:
                request_key = uuid4()

                async def upload_once():
                    return await materials.upload_material(
                        scope.owner,
                        db,
                        UploadFile(filename="notes.txt", file=io.BytesIO(raw)),
                        OwnerScope.PROJECT,
                        request_key,
                        None,
                        scope.project.id,
                        "Synthetic source",
                        None,
                    )

                file = await upload_once()
                assert file["id"] == (await upload_once())["id"]
                doc = await api.create_document(
                    api.DocumentCreate(
                        scope_type="project",
                        project_id=scope.project.id,
                        title="Archive test",
                        body="{{var|value: int}}",
                        record_data={"var": {"value": 7}},
                        file_ids=[file["id"]],
                    ),
                    scope.owner,
                    db,
                )
                with pytest.raises(HTTPException):
                    await api.create_document(
                        api.DocumentCreate(
                            scope_type="personal",
                            title="Wrong audience",
                            file_ids=[file["id"]],
                        ),
                        scope.owner,
                        db,
                    )
                await db.rollback()
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await api.export_document(UUID(doc["id"]), scope.outsider, db)
                response = await api.export_document(UUID(doc["id"]), scope.owner, db)
                content, files, _ = read_document_archive(response.body)
                assert content.body == doc["body"] and files[0][1] == raw
                restore_key = uuid4()

                async def restore(digest=None):
                    return await api.import_document(
                        scope.owner,
                        db,
                        UploadFile(
                            filename="archive.zip", file=io.BytesIO(response.body)
                        ),
                        ResearchLogScope.PROJECT,
                        restore_key,
                        None,
                        scope.project.id,
                        digest,
                    )

                preview = await restore()
                assert preview["requires_confirmation"]
                restored = await restore(preview["preview_digest"])
                assert (
                    restored["id"] != doc["id"]
                    and restored["file_ids"] != doc["file_ids"]
                )
                assert restored["record_data"] == doc["record_data"]
                assert restored["state"] == "draft"
                assert (await restore(preview["preview_digest"]))["id"] == restored[
                    "id"
                ]
                reexport = await api.export_document(
                    UUID(restored["id"]), scope.owner, db
                )
                assert read_document_archive(reexport.body)[1][0][1] == raw

    asyncio.run(exercise())


def test_document_calendar_browse_respects_scope_dates_order_and_pagination():
    from datetime import date, datetime

    from app.models.research_log import ResearchLogEntry

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            ids = []
            times = [
                "2026-11-06T15:59:59+00:00",
                "2026-11-06T16:00:00+00:00",
                "2026-11-07T15:59:59+00:00",
                "2026-11-07T16:00:00+00:00",
            ]
            async with sessions() as db:
                for index, time in enumerate(times):
                    item = await api.create_document(
                        api.DocumentCreate(
                            scope_type="project",
                            project_id=scope.project.id,
                            title=f"Synthetic browse {index}",
                            occurred_at=datetime.fromisoformat(time),
                        ),
                        scope.recorder,
                        db,
                    )
                    ids.append(item["id"])
                await api.create_document(
                    api.DocumentCreate(
                        scope_type="personal",
                        title="Synthetic browse private",
                        occurred_at=datetime.fromisoformat(times[1]),
                    ),
                    scope.owner,
                    db,
                )
                common = {
                    "current_user": scope.recorder,
                    "db_session": db,
                    "scope_type": ResearchLogScope.PROJECT,
                    "project_id": scope.project.id,
                    "lab_id": None,
                    "q": "Synthetic browse",
                    "kind": "",
                    "time_zone": "Asia/Shanghai",
                }
                filtered = await api.list_documents(
                    **common,
                    order="recorded",
                    date_from=date(2026, 11, 7),
                    date_to=date(2026, 11, 7),
                    page=1,
                    page_size=1,
                )
                assert (
                    filtered["total_count"] == 2
                    and filtered["items"][0]["id"] == ids[2]
                )
                page2 = await api.list_documents(
                    **common,
                    order="recorded",
                    date_from=date(2026, 11, 7),
                    date_to=date(2026, 11, 7),
                    page=2,
                    page_size=1,
                )
                assert page2["items"][0]["id"] == ids[1]
                calendar = await api.document_calendar(
                    **common, month=date(2026, 11, 1)
                )
                assert calendar["days"] == [
                    {"date": "2026-11-06", "count": 1},
                    {"date": "2026-11-07", "count": 2},
                    {"date": "2026-11-08", "count": 1},
                ]
                assert not (
                    await api.document_calendar(
                        **{**common, "kind": "meeting"}, month=date(2026, 11, 1)
                    )
                )["days"]
                # Editing a historical document only changes the recent-work order.
                await api.update_document(
                    UUID(ids[0]),
                    api.DocumentUpdate(
                        title="Synthetic browse edited", expected_revision=1
                    ),
                    scope.recorder,
                    db,
                )
                recent = await api.list_documents(
                    **common, order="updated", page=1, page_size=20
                )
                chronological = await api.list_documents(
                    **common, order="recorded", page=1, page_size=20
                )
                assert recent["items"][0]["id"] == ids[0]
                assert chronological["items"][-1]["id"] == ids[0]
                changed = await api.update_document(
                    UUID(ids[0]),
                    api.DocumentUpdate(
                        title="Synthetic browse corrected date",
                        expected_revision=2,
                        occurred_at=datetime.fromisoformat(times[1]),
                    ),
                    scope.recorder,
                    db,
                )
                assert changed["revision"] == 3
                entry = await db.get(ResearchLogEntry, UUID(ids[0]))
                assert entry.occurred_at == datetime.fromisoformat(
                    times[1]
                )  # Log and document share this timestamp.
                entry.archived_at = datetime.fromisoformat(times[-1])
                await db.commit()
                calendar = await api.document_calendar(
                    **common, month=date(2026, 11, 1)
                )
                assert sum(x["count"] for x in calendar["days"]) == 3
                with pytest.raises(HTTPException) as denied:
                    await api.document_calendar(
                        **{**common, "current_user": scope.outsider},
                        month=date(2026, 11, 1),
                    )
                assert denied.value.status_code == 403
                personal = {
                    **common,
                    "scope_type": ResearchLogScope.PERSONAL,
                    "project_id": None,
                }
                assert not (
                    await api.document_calendar(**personal, month=date(2026, 11, 1))
                )["days"]

    asyncio.run(exercise())
