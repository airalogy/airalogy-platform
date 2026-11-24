"""Check organization membership at read time, independently of the sharing UI."""

import asyncio
import os
from importlib import import_module
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.config import config
from app.models.lab import Lab, LabUser
from app.models.project import Project, ProjectUser
from app.models.protocol import Protocol
from app.routers import workspace_sharing as sharing
from app.routers.projects import project_response
from app.routers.protocols import protocol_response
from fastapi import HTTPException
from migrations.model_registry import import_models
from sqlalchemy import delete, text

from tests.test_record_analysis_postgres import database, seed_analysis

import_models()
pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Isolated PostgreSQL required",
)


def test_current_membership_required_for_project_protocol_and_organization_link(
    monkeypatch,
):
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", "single_organization")
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")

    async def exercise():
        async with database() as sessions:
            scope = await seed_analysis(sessions)
            monkeypatch.setattr(config, "SINGLE_LAB_UID", scope.lab.uid)
            async with sessions() as db:
                await db.execute(
                    delete(ProjectUser).where(
                        ProjectUser.project_id == scope.project.id,
                        ProjectUser.user_id == scope.analyst.id,
                    )
                )
                await db.commit()
                await sharing.change_reading(
                    scope.project.id, sharing.Toggle(enabled=True), db, scope.owner
                )
                draft = await sharing.sharing_options(
                    scope.project.id, db, scope.owner, scope.protocol.id, "1.0.0"
                )
                published = await sharing.publish(
                    scope.project.id,
                    sharing.Publish(audience="organization", preview=draft["preview"]),
                    db,
                    scope.owner,
                    scope.protocol.id,
                    "1.0.0",
                )

            async def check(user, allowed):
                async with sessions() as db:
                    project = await db.get(Project, scope.project.id)
                    lab = await db.get(Lab, scope.lab.id)
                    protocol = await db.get(Protocol, scope.protocol.id)
                    for read in [
                        project_response(project, lab, user, db),
                        protocol_response(db, user, protocol, project=project, lab=lab),
                        sharing.read_publication(published["id"], db, user),
                    ]:
                        if allowed:
                            assert await read
                        else:
                            with pytest.raises(HTTPException) as error:
                                await read
                            assert error.value.status_code == 404

            await check(scope.analyst, True)
            await check(scope.outsider, False)
            await check(None, False)
            async with sessions() as db:
                await db.execute(
                    delete(LabUser).where(
                        LabUser.user_id == scope.analyst.id,
                        LabUser.lab_id == scope.lab.id,
                    )
                )
                await db.commit()
            await check(scope.analyst, False)

    asyncio.run(exercise())


@pytest.mark.parametrize("profile", ["single_organization", "community"])
def test_migration_of_existing_public_and_private_projects(monkeypatch, profile):
    monkeypatch.setattr(config, "DEPLOYMENT_MODE", profile)
    monkeypatch.setattr(config, "SINGLE_LAB_UID", "test_org")
    revision = import_module("migrations.versions.0098_workspace_publications")

    def rehearse(connection):
        schema = "visibility_" + uuid4().hex
        connection.exec_driver_sql(f"CREATE SCHEMA {schema}")
        connection.exec_driver_sql(f"SET LOCAL search_path TO {schema}")
        for table in ["users", "protocol_versions"]:
            connection.exec_driver_sql(f"CREATE TABLE {table} (id uuid PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE labs (id uuid PRIMARY KEY, uid text)")
        connection.exec_driver_sql(
            "CREATE TABLE projects (id uuid PRIMARY KEY, lab_id uuid, type integer)"
        )
        org, other = uuid4(), uuid4()
        connection.execute(
            text("INSERT INTO labs VALUES (:id,'test_org'),(:other,'other')"),
            {"id": org, "other": other},
        )
        identities = [uuid4(), uuid4(), uuid4()]
        for project_id, org_id, kind in zip(
            identities, [org, org, other], [2, 1, 2], strict=True
        ):
            connection.execute(
                text("INSERT INTO projects VALUES (:id,:org,:kind)"),
                {"id": project_id, "org": org_id, "kind": kind},
            )
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
        for project_id, expected in zip(
            identities,
            [
                (1, True) if profile == "single_organization" else (2, False),
                (1, False),
                (2, False),
            ],
            strict=True,
        ):
            assert (
                connection.execute(
                    text(
                        "SELECT type, organization_readable FROM projects WHERE id=:id"
                    ),
                    {"id": project_id},
                ).one()
                == expected
            )
        assert not connection.scalar(
            text("SELECT bool_or(external_publication_enabled) FROM labs")
        )
        assert (
            connection.scalar(text("SELECT count(*) FROM workspace_publications")) == 0
        )

    async def exercise():
        async with database() as sessions, sessions() as db:
            await (await db.connection()).run_sync(rehearse)
            await (
                db.rollback()
            )  # The private schema and its synthetic rows disappear together.

    asyncio.run(exercise())
