"""Project history is personal, bounded, and reauthorized on every replay."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.config import config
from app.models.pinned_item import PinnedItem, PinnedResourceType
from app.models.project import Project, ProjectType, ProjectUser
from app.models.project_visit import ProjectVisit
from app.models.protocol import Protocol
from app.models.research_log import ResearchLogEntry
from app.routers import research_documents as documents
from app.routers import workspace as api
from app.routers.pinned_items import get_pinned_items
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, func, select, update

from tests.test_record_analysis_postgres import add_record, database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"),
    reason="Isolated migrated PostgreSQL required",
)


@pytest.fixture(params=["flat", "structured"])
def permission_mode(request, monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", request.param)


async def visit(sessions, user, **data):
    async with sessions() as db:
        return await api.capture_project_visit(
            api.ProjectVisitRequest(**data), user, db
        )


async def recent(sessions, user):
    async with sessions() as db:
        return (await api.recent_projects(user, db))["items"]


def test_workspace_actor_history_upsert_canonical_routes_and_no_read_side_effects(
    permission_mode,
):
    async def exercise():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            args = {
                "project_id": s.project.id,
                "kind": "protocol",
                "protocol_uid": s.protocol.uid,
            }
            await asyncio.gather(
                *(visit(sessions, s.recorder, **args) for _ in range(4))
            )
            items = await recent(sessions, s.recorder)
            assert len(items) == 1
            assert items[0]["target"]["route"] == {
                "name": "protocol-detail",
                "params": {
                    "labUid": s.lab.uid,
                    "projectUid": s.project.uid,
                    "protocolUid": s.protocol.uid,
                },
            }
            timestamp = items[0]["visited_at"]
            assert await recent(sessions, s.owner) == []
            async with sessions() as db:
                await db.execute(
                    update(Project)
                    .where(Project.id == s.project.id)
                    .values(name="Synthetic renamed project")
                )
                await db.commit()
                stored = (
                    await db.scalars(
                        select(ProjectVisit).where(
                            ProjectVisit.user_id == s.recorder.id
                        )
                    )
                ).all()
                assert len(stored) == 1
                assert set(stored[0].target) == {
                    "kind",
                    "section",
                    "project_id",
                    "protocol_uid",
                }
            renamed = (await recent(sessions, s.recorder))[0]
            assert renamed["name"] == "Synthetic renamed project"
            assert renamed["visited_at"] == timestamp
            with pytest.raises(HTTPException):
                await visit(sessions, s.outsider, **args)
            assert await recent(sessions, s.outsider) == []
            with pytest.raises(ValidationError):
                api.ProjectVisitRequest(
                    **args, user_id=s.owner.id, url="https://example.test"
                )
            async with sessions() as db:
                await db.execute(
                    delete(ProjectUser).where(
                        ProjectUser.project_id == s.project.id,
                        ProjectUser.user_id == s.recorder.id,
                    )
                )
                await db.commit()
            assert await recent(sessions, s.recorder) == []

    asyncio.run(exercise())


def test_workspace_document_scope_deleted_target_and_public_project_privacy(
    permission_mode,
):
    async def exercise():
        async with database() as sessions:
            s = await seed_analysis(sessions, public=True)
            async with sessions() as db:
                personal = await documents.create_document(
                    documents.DocumentCreate(
                        id=uuid4(),
                        scope_type="personal",
                        title="Synthetic private writing",
                    ),
                    s.recorder,
                    db,
                )
                project = await documents.create_document(
                    documents.DocumentCreate(
                        id=uuid4(),
                        scope_type="project",
                        project_id=s.project.id,
                        title="Synthetic project writing",
                    ),
                    s.recorder,
                    db,
                )
            assert await visit(
                sessions, s.recorder, kind="document", resource_id=personal["id"]
            ) == {"recorded": False}
            assert await recent(sessions, s.recorder) == []
            await visit(
                sessions, s.recorder, kind="document", resource_id=project["id"]
            )
            row = (await recent(sessions, s.recorder))[0]
            assert row["target"]["route"]["params"] == {"documentId": project["id"]}
            with pytest.raises(HTTPException):
                await visit(
                    sessions, s.outsider, kind="document", resource_id=project["id"]
                )
            async with sessions() as db:
                await db.execute(
                    delete(ProjectUser).where(
                        ProjectUser.user_id == s.recorder.id,
                        ProjectUser.project_id == s.project.id,
                    )
                )
                await db.commit()
            row = (await recent(sessions, s.recorder))[0]
            assert (
                row["target"] is None
            )  # Public Project survives; private document must not.
            await visit(sessions, s.owner, kind="document", resource_id=project["id"])
            async with sessions() as db:
                await db.execute(
                    update(ResearchLogEntry)
                    .where(ResearchLogEntry.id == UUID(project["id"]))
                    .values(archived_at=datetime.now(UTC))
                )
                await db.commit()
            assert (await recent(sessions, s.owner))[0]["target"] is None

    asyncio.run(exercise())


def test_workspace_record_self_only_and_draft_destinations_recheck_permissions(
    permission_mode,
):
    async def exercise():
        async with database() as sessions:
            s = await seed_analysis(sessions, public=True)
            own = await add_record(sessions, s, 1, author=s.recorder)
            other = await add_record(sessions, s, 2, author=s.owner, number=2)
            data = {
                "project_id": s.project.id,
                "kind": "record",
                "protocol_uid": s.protocol.uid,
                "record_version": 1,
            }
            await visit(sessions, s.recorder, **data, resource_id=own.id)
            assert (await recent(sessions, s.recorder))[0]["target"]["route"]["params"][
                "recordId"
            ] == str(own.id)
            with pytest.raises(HTTPException):
                await visit(sessions, s.recorder, **data, resource_id=other.id)
            async with sessions() as db:
                request = api.DraftDestinationsRequest(
                    protocol_ids=[s.protocol.id, s.protocol.id, uuid4()]
                )
                result = await api.draft_destinations(request, s.recorder, db)
                assert len(result["items"]) == 1
                assert (
                    result["items"][0]["target"]["route"]["name"] == "protocol-detail"
                )
                assert (await api.draft_destinations(request, s.outsider, db))[
                    "items"
                ] == []
            before = (await recent(sessions, s.recorder))[0]
            assert (
                before["target"]["kind"] == "record"
            )  # Draft lookups never alter history.
            async with sessions() as db:
                await db.execute(
                    update(Protocol)
                    .where(Protocol.id == s.protocol.id)
                    .values(deleted_at=datetime.now(UTC).replace(tzinfo=None))
                )
                await db.commit()
                assert (await api.draft_destinations(request, s.recorder, db))[
                    "items"
                ] == []
            assert (await recent(sessions, s.recorder))[0]["target"] is None

    asyncio.run(exercise())


def test_workspace_limit_keeps_pins_and_removes_revoked_pin_metadata(permission_mode):
    async def exercise():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            now = datetime.now(UTC)
            async with sessions() as db:
                pin = PinnedItem(
                    user_id=s.recorder.id,
                    resource_type=PinnedResourceType.PROJECT,
                    resource_id=s.project.id,
                    sort_order=0,
                )
                db.add(pin)
                db.add(
                    PinnedItem(
                        user_id=s.recorder.id,
                        resource_type=PinnedResourceType.PROTOCOL,
                        resource_id=s.protocol.id,
                        sort_order=1,
                    )
                )
                for i in range(51):
                    p = Project(
                        id=uuid4(),
                        lab_id=s.lab.id,
                        uid="synthetic_" + uuid4().hex,
                        name="Synthetic other project",
                        create_user_id=s.owner.id,
                        type=ProjectType.PUBLIC,
                    )
                    db.add(p)
                    await db.flush()
                    db.add(
                        ProjectVisit(
                            user_id=s.recorder.id,
                            project_id=p.id,
                            target={"kind": "project", "project_id": str(p.id)},
                            visited_at=now - timedelta(days=i + 1),
                        )
                    )
                await db.commit()
                last_id = p.id
            await visit(sessions, s.recorder, project_id=last_id)
            async with sessions() as db:
                assert (
                    await db.scalar(
                        select(func.count())
                        .select_from(ProjectVisit)
                        .where(ProjectVisit.user_id == s.recorder.id)
                    )
                    == 50
                )
            rows = await recent(sessions, s.recorder)
            assert rows[0]["id"] == str(s.project.id)
            assert rows[0]["visited_at"] is None
            assert rows[1]["id"] == str(last_id)
            async with sessions() as db:
                assert len((await get_pinned_items(db, s.recorder))["items"]) == 2
                await db.execute(
                    delete(ProjectUser).where(
                        ProjectUser.project_id == s.project.id,
                        ProjectUser.user_id == s.recorder.id,
                    )
                )
                await db.commit()
                assert (await get_pinned_items(db, s.recorder))["items"] == []
            assert not any(
                row["id"] == str(s.project.id)
                for row in await recent(sessions, s.recorder)
            )

    asyncio.run(exercise())


def test_workspace_single_lab_history_stays_inside_configured_lab(monkeypatch):
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", "single_lab")
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "structured")
    monkeypatch.setattr(config, "SINGLE_LAB_UID", "other_configured_lab")

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions, public=True)
            with pytest.raises(HTTPException) as denied:
                await visit(sessions, scope.owner, project_id=scope.project.id)
            assert denied.value.status_code == 404
            async with sessions() as db:
                db.add(
                    ProjectVisit(
                        user_id=scope.owner.id,
                        project_id=scope.project.id,
                        target={"project_id": str(scope.project.id)},
                    )
                )
                await db.commit()
            assert await recent(sessions, scope.owner) == []
            # The Project entry and no-history homepage fallback must also enforce
            # the configured workspace, even without a client-side Lab filter.
            from app.routers.users import UserProjectQueryParams, get_user_projects

            async def projects(params):
                async with sessions() as db:
                    return await get_user_projects(
                        user_id=scope.owner.id,
                        current_user=scope.owner,
                        db_session=db,
                        page=1,
                        page_size=10,
                        sorted_by=None,
                        params=params,
                    )

            assert (await projects(UserProjectQueryParams()))["total_count"] == 0
            assert (await projects(UserProjectQueryParams(lab_uid=scope.lab.uid)))[
                "total_count"
            ] == 0
            monkeypatch.setattr(config, "SINGLE_LAB_UID", scope.lab.uid)
            assert (await projects(UserProjectQueryParams()))["total_count"] == 1

            # Fixed-Lab navigation uses the effective-access list, so Lab managers
            # and delegated members do not lose projects when the Lab layer folds.
            from app.routers.projects import get_projects

            async with sessions() as db:
                db.add(
                    Project(
                        uid=f"single_workspace_{uuid4().hex[:8]}",
                        name="Synthetic Lab-managed Project",
                        lab_id=scope.lab.id,
                        create_user_id=scope.owner.id,
                        type=ProjectType.PRIVATE,
                    )
                )
                await db.commit()

            async def workspace_projects(user):
                async with sessions() as db:
                    return await get_projects(
                        db_session=db, current_user=user, lab_uid=scope.lab.uid
                    )

            assert (await workspace_projects(scope.owner))["total_count"] == 2
            assert (await workspace_projects(scope.outsider))["total_count"] == 0
            with pytest.raises(HTTPException) as anonymous:
                await workspace_projects(None)
            assert anonymous.value.status_code == 401
            monkeypatch.setattr(config, "SINGLE_LAB_UID", "other_configured_lab")
            assert (await workspace_projects(scope.owner))["total_count"] == 0

    asyncio.run(exercise())
