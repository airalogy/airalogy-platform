"""Real member permissions, immutable use and concurrent template creation."""

import asyncio
import os
from uuid import UUID

import pytest
from app.models.document_template import DocumentTemplate
from app.models.lab import LabRole, LabUser
from app.models.project import ProjectRole, ProjectUser
from app.routers import document_templates as api
from app.routers import research_documents as documents
from fastapi import HTTPException
from sqlalchemy import select

from tests.test_record_analysis_postgres import database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"),
    reason="Isolated migrated PostgreSQL required",
)


async def create(sessions, user, **params):
    request = api.TemplateCreate(**params)
    async with sessions() as db:
        preview = await api.create_template(request, user, db)
    assert preview["requires_confirmation"]
    request.preview_digest = preview["preview_digest"]
    async with sessions() as db:
        result = await api.create_template(request, user, db)
    return result, request


async def list_scope(db, user, **scope):
    return await api.list_templates(
        user, db, q="", archived=False, page=1, page_size=100, **scope
    )


def test_template_permissions_shared_scopes_and_public_project_isolation():
    async def exercise():
        async with database() as sessions:
            s = await seed_analysis(sessions, public=True)
            personal, _ = await create(
                sessions, s.recorder, scope_type="personal", title="Private starter"
            )
            project, _ = await create(
                sessions,
                s.recorder,
                scope_type="project",
                project_id=s.project.id,
                title="Shared project starter",
            )
            lab, _ = await create(
                sessions,
                s.owner,
                scope_type="lab",
                lab_id=s.lab.id,
                title="Lab starter",
            )
            async with sessions() as db:
                # Even a Lab member cannot read a public Project's private templates
                # without the existing member-level capability.
                db.add(
                    LabUser(
                        lab_id=s.lab.id,
                        user_id=s.outsider.id,
                        role=LabRole.MEMBER,
                        create_user_id=s.owner.id,
                    )
                )
                await db.commit()
                for item in (personal, project):
                    with pytest.raises(HTTPException):
                        await api.get_template(UUID(item["id"]), s.outsider, db)
                assert (await api.get_template(UUID(lab["id"]), s.outsider, db))[
                    "can_edit"
                ] is False
                with pytest.raises(HTTPException):
                    await api.create_template(
                        api.TemplateCreate(
                            scope_type="lab", lab_id=s.lab.id, title="Denied"
                        ),
                        s.recorder,
                        db,
                    )
                await db.rollback()
                assert (await list_scope(db, s.recorder, scope_type="personal"))[
                    "total_count"
                ] == 1
                with pytest.raises(HTTPException):
                    await list_scope(
                        db, s.outsider, scope_type="project", project_id=s.project.id
                    )
                contexts = (await api.available_scopes(s.outsider, db))["items"]
                assert not any(x["project_id"] == str(s.project.id) for x in contexts)
                db.add(
                    ProjectUser(
                        project_id=s.project.id,
                        user_id=s.outsider.id,
                        role=ProjectRole.VIEWER,
                        create_user_id=s.owner.id,
                    )
                )
                await db.commit()
                readable = await api.get_template(UUID(project["id"]), s.outsider, db)
                assert not readable["can_edit"]
                with pytest.raises(HTTPException):
                    await api.update_template(
                        UUID(project["id"]),
                        api.TemplateUpdate(title="Denied", expected_revision=1),
                        s.outsider,
                        db,
                    )
                await db.rollback()
                copy = await documents.create_document(
                    documents.DocumentCreate(
                        scope_type="personal",
                        title="Use shared starter",
                        source_template_id=project["id"],
                        source_template_revision=1,
                    ),
                    s.outsider,
                    db,
                )
                assert copy["origin"]["kind"] == "template"
                assert copy["scope_type"] == "personal"

    asyncio.run(exercise())


def test_source_values_are_excluded_and_existing_documents_pin_template_content():
    async def exercise():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            body = "# Synthetic method\n{{var|planned: int = 5}} {{var|measured: int}}"
            async with sessions() as db:
                original = await documents.create_document(
                    documents.DocumentCreate(
                        scope_type="personal",
                        title="Private working note",
                        body=body,
                        record_data={"var": {"planned": 99, "measured": 42}},
                        tags=["private"],
                        collection="Private study",
                    ),
                    s.owner,
                    db,
                )
            item, _request = await create(
                sessions,
                s.owner,
                scope_type="project",
                project_id=s.project.id,
                title="Reusable method",
                body=body,
                source_document_id=original["id"],
                source_revision=1,
            )
            assert (
                "source" not in item
                and "record_data" not in item
                and "file_ids" not in item
            )
            async with sessions() as db:
                doc = await documents.create_document(
                    documents.DocumentCreate(
                        scope_type="project",
                        project_id=s.project.id,
                        title="New work",
                        source_template_id=item["id"],
                        source_template_revision=1,
                        record_data={"var": {"measured": 123}},
                    ),
                    s.recorder,
                    db,
                )
                assert doc["record_data"] == {"var": {"planned": 5}}
                assert not doc["file_ids"] and not doc["tags"] and not doc["collection"]
                assert original["id"] not in str(doc["origin"])
                update = api.TemplateUpdate(
                    title="Reusable method 2",
                    body=body.replace("= 5", "= 7"),
                    expected_revision=1,
                )
                preview = await api.update_template(
                    UUID(item["id"]), update, s.owner, db
                )
                update.preview_digest = preview["preview_digest"]
                saved = await api.update_template(UUID(item["id"]), update, s.owner, db)
                assert saved["revision"] == 2
                unchanged = await documents.get_document(
                    UUID(doc["id"]), s.recorder, db
                )
                assert (
                    unchanged["body"] == body
                    and unchanged["record_data"]["var"]["planned"] == 5
                )
                with pytest.raises(HTTPException) as stale:
                    await documents.create_document(
                        documents.DocumentCreate(
                            scope_type="personal",
                            title="Stale selection",
                            source_template_id=item["id"],
                            source_template_revision=1,
                        ),
                        s.owner,
                        db,
                    )
                assert stale.value.status_code == 409
                await db.rollback()
                archived = await api.archive_template(
                    UUID(item["id"]),
                    api.ArchiveRequest(expected_revision=2, archived=True),
                    s.owner,
                    db,
                )
                assert archived["archived"]
                with pytest.raises(HTTPException):
                    await documents.create_document(
                        documents.DocumentCreate(
                            scope_type="personal",
                            title="Archived",
                            source_template_id=item["id"],
                            source_template_revision=3,
                        ),
                        s.owner,
                        db,
                    )
                await db.rollback()
                restored = await api.archive_template(
                    UUID(item["id"]),
                    api.ArchiveRequest(expected_revision=3, archived=False),
                    s.owner,
                    db,
                )
                assert restored["revision"] == 4 and not restored["archived"]
                history = await api.template_history(UUID(item["id"]), s.recorder, db)
                assert [x["revision"] for x in history["items"]] == [4, 3, 2, 1]
                assert history["items"][-1]["snapshot"]["body"] == body

    asyncio.run(exercise())


def test_preview_binding_concurrent_idempotency_and_revoked_membership():
    async def exercise():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            request = api.TemplateCreate(
                scope_type="project",
                project_id=s.project.id,
                title="Concurrent starter",
            )
            async with sessions() as db:
                preview = await api.create_template(request, s.recorder, db)
            request.preview_digest = preview["preview_digest"]

            async def save():
                async with sessions() as db:
                    return await api.create_template(request, s.recorder, db)

            a, b = await asyncio.gather(save(), save())
            assert a["id"] == b["id"] and a["revision"] == 1
            async with sessions() as db:
                changed = request.model_copy(update={"title": "Different content"})
                with pytest.raises(HTTPException) as conflict:
                    await api.create_template(changed, s.recorder, db)
                assert conflict.value.status_code == 409
                await db.rollback()
                update = api.TemplateUpdate(title="New version", expected_revision=1)
                preview = await api.update_template(
                    UUID(a["id"]), update, s.recorder, db
                )
                update.preview_digest = preview["preview_digest"]
                update.body = "Changed after preview"
                with pytest.raises(HTTPException) as changed_preview:
                    await api.update_template(UUID(a["id"]), update, s.recorder, db)
                assert changed_preview.value.status_code == 409
                await db.rollback()
                assert (await db.get(DocumentTemplate, UUID(a["id"]))).revision == 1
                member = await db.scalar(
                    select(ProjectUser).where(
                        ProjectUser.project_id == s.project.id,
                        ProjectUser.user_id == s.recorder.id,
                    )
                )
                await db.delete(member)
                await db.commit()
                with pytest.raises(HTTPException):
                    await api.get_template(UUID(a["id"]), s.recorder, db)
                with pytest.raises(HTTPException):
                    await documents.create_document(
                        documents.DocumentCreate(
                            scope_type="personal",
                            title="No longer authorized",
                            source_template_id=a["id"],
                            source_template_revision=1,
                        ),
                        s.recorder,
                        db,
                    )

    asyncio.run(exercise())


def test_cross_scope_copy_creates_independent_template_and_requires_source_access():
    async def exercise():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            original, _ = await create(
                sessions,
                s.owner,
                scope_type="personal",
                title="Private starter",
                body="## Reusable instructions",
            )
            shared, _ = await create(
                sessions,
                s.owner,
                scope_type="lab",
                lab_id=s.lab.id,
                title="Lab copy",
                body=original["body"],
                source_template_id=original["id"],
                source_template_revision=1,
            )
            assert shared["id"] != original["id"] and "source" not in shared
            async with sessions() as db:
                with pytest.raises(HTTPException):
                    await api.get_template(UUID(original["id"]), s.recorder, db)
                assert (await api.get_template(UUID(shared["id"]), s.recorder, db))[
                    "body"
                ] == original["body"]
                with pytest.raises(HTTPException):
                    await api.create_template(
                        api.TemplateCreate(
                            scope_type="personal",
                            title="Private leak",
                            source_template_id=original["id"],
                            source_template_revision=1,
                        ),
                        s.recorder,
                        db,
                    )
                await db.rollback()
                with pytest.raises(HTTPException) as stale:
                    await api.create_template(
                        api.TemplateCreate(
                            scope_type="personal",
                            title="Stale copy",
                            source_template_id=shared["id"],
                            source_template_revision=99,
                        ),
                        s.recorder,
                        db,
                    )
                assert stale.value.status_code == 409

    asyncio.run(exercise())
