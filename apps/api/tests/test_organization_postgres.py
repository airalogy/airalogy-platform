"""Real legacy-schema recovery and Organization/Lab API parity; synthetic data only."""

import asyncio
import os
from contextlib import asynccontextmanager
from importlib import import_module
from uuid import uuid4

import httpx
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import FastAPI
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.config import config
from app.database import get_db_session
from app.models.base import Base
from app.models.lab import Lab, LabUser
from app.models.project import Project
from app.routers import instance, labs, organizations
from app.routers.depends import create_access_token
from migrations.model_registry import import_models
from tests.test_record_analysis_postgres import database, seed_analysis

import_models()
pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"), reason="Isolated PostgreSQL required"
)


@asynccontextmanager
async def client(sessions):
    app = FastAPI()
    for router in (instance.router, labs.router, organizations.router):
        app.include_router(router)

    async def session():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db_session] = session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as http:
        yield http


def test_historical_upgrade_identity_foreign_keys_and_recovery():
    async def run():
        engine = create_async_engine(os.environ["RESOURCE_TEST_DATABASE_URL"])
        migration = import_module("migrations.versions.0085_organization_foundation")
        try:
            async with engine.connect() as connection:
                tx = await connection.begin()
                try:
                    schema = "org_migration_" + uuid4().hex
                    await connection.execute(text(f"CREATE SCHEMA {schema}"))
                    await connection.execute(
                        text(f"SET LOCAL search_path TO {schema}, public")
                    )
                    await connection.execute(
                        text(
                            "CREATE TABLE labs (id UUID PRIMARY KEY, name TEXT NOT NULL)"
                        )
                    )
                    await connection.execute(
                        text(
                            "CREATE TABLE projects (id UUID PRIMARY KEY, lab_id UUID REFERENCES labs(id))"
                        )
                    )
                    identity, project = uuid4(), uuid4()
                    await connection.execute(
                        text("INSERT INTO labs VALUES (:id,'Existing laboratory')"),
                        {"id": identity},
                    )
                    await connection.execute(
                        text("INSERT INTO projects VALUES (:id,:lab)"),
                        {"id": project, "lab": identity},
                    )

                    async def apply(direction):
                        def migrate(sync):
                            with Operations.context(MigrationContext.configure(sync)):
                                getattr(migration, direction)()

                        await connection.run_sync(migrate)

                    await apply("upgrade")
                    await apply(
                        "upgrade"
                    )  # Also accepts current metadata on fresh installation.
                    assert (
                        await connection.execute(
                            text("SELECT id, organization_type FROM labs")
                        )
                    ).one() == (identity, "laboratory")
                    assert (
                        await connection.execute(
                            text("SELECT id, lab_id FROM projects")
                        )
                    ).one() == (project, identity)
                    await apply("downgrade")
                    await apply("upgrade")
                    await connection.execute(
                        text("UPDATE labs SET organization_type='company'")
                    )
                    with pytest.raises(RuntimeError, match="Organization types exist"):
                        await apply("downgrade")
                    assert (
                        await connection.scalar(
                            text("SELECT organization_type FROM labs")
                        )
                        == "company"
                    )
                finally:
                    await tx.rollback()
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_canonical_and_legacy_apis_share_permissions_and_identity(monkeypatch):
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            lab = seed.lab
            users = {name: getattr(seed, name) for name in ("owner", "outsider")}
            monkeypatch.setattr(config, "DEPLOYMENT_MODE", "single_organization")
            monkeypatch.setattr(config, "SINGLE_LAB_UID", lab.uid)
            async with client(sessions) as http:
                owner = {"Auth-Token": create_access_token(users["owner"])}
                outsider = {"Auth-Token": create_access_token(users["outsider"])}
                for prefix in ("labs", "organizations"):
                    assert (await http.get(f"/{prefix}/{lab.id}")).status_code == 401
                    assert (
                        await http.get(f"/{prefix}/{lab.id}", headers=outsider)
                    ).status_code == 403
                    denied = await http.put(
                        f"/{prefix}/{lab.id}",
                        headers=outsider,
                        json={"description": "", "organization_type": "company"},
                    )
                    assert denied.status_code == 403
                    read = await http.get(f"/{prefix}/{lab.id}", headers=owner)
                    assert read.status_code == 200, read.text
                    assert read.json()["data"]["id"] == str(lab.id)
                member_counts = []
                for path, key in (
                    (f"/labs/{lab.id}/users", "users"),
                    (f"/organizations/{lab.id}/members", "members"),
                ):
                    assert (await http.get(path, headers=outsider)).status_code == 403
                    members = await http.get(path, headers=owner)
                    assert members.status_code == 200, members.text
                    member_counts.append(members.json()["total_count"])
                    assert any(
                        user["id"] == str(users["owner"].id)
                        for user in members.json()[key]
                    )
                    # Additional direct memberships cannot bypass single-instance invitations.
                    assert (
                        await http.post(
                            path,
                            headers=owner,
                            json={"user_id": str(users["outsider"].id), "role": 3},
                        )
                    ).status_code == 403
                assert member_counts[0] == member_counts[1]
                changed = await http.put(
                    f"/organizations/{lab.id}",
                    headers=owner,
                    json={
                        "description": "Synthetic R&D",
                        "organization_type": "company",
                    },
                )
                assert changed.status_code == 200, changed.text
                old = await http.get(f"/labs/{lab.id}", headers=owner)
                assert old.json()["data"]["organization_type"] == "company"
                status = (await http.get("/instance")).json()
                assert status["organization"] == status["lab"]
                assert status["single_organization"] and status["single_lab"]
                assert status["organization"]["id"] == str(lab.id)
                # The single-organization boundary applies to both create APIs.
                payload = {"name": "Another Company", "uid": "other_org", "members": []}
                for prefix in ("labs", "organizations"):
                    assert (
                        await http.post(f"/{prefix}", headers=owner, json=payload)
                    ).status_code == 403
            async with sessions() as db:
                assert (
                    await db.get(Project, seed.project.id)
                ).organization_id == lab.id

    asyncio.run(run())


@pytest.mark.parametrize("confirmed_uid", [None, "company"])
def test_company_bootstrap_private_project_and_legacy_invitation_default(
    monkeypatch, confirmed_uid
):
    async def run():
        url = os.environ["RESOURCE_TEST_DATABASE_URL"]
        admin = create_async_engine(url)
        schema = "org_bootstrap_" + uuid4().hex
        async with admin.begin() as db:
            await db.execute(text(f"CREATE SCHEMA {schema}"))
        engine = create_async_engine(
            url, connect_args={"server_settings": {"search_path": f"{schema},public"}}
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as db:
                await (
                    await db.execution_options(schema_translate_map={None: schema})
                ).run_sync(Base.metadata.create_all)
            monkeypatch.setattr(config, "DEPLOYMENT_MODE", "single_organization")
            monkeypatch.setattr(config, "INITIAL_ADMIN_TOKEN", "synthetic-setup-code")
            monkeypatch.setattr(config, "SINGLE_LAB_UID", "company")
            monkeypatch.setattr(config, "SINGLE_LAB_DEFAULT_PROJECT_UID", "workspace")
            monkeypatch.setattr(
                config, "SINGLE_LAB_DEFAULT_PROJECT_NAME", "Team Workspace"
            )
            async with client(sessions) as http:
                status = await http.get("/instance")
                assert status.status_code == 200, status.text
                assert status.json()["default_organization_uid"] == "company"
                assert status.json()["initialized"] is False
                params = {
                    "setup_token": "wrong",
                    "organization_name": "Synthetic Glasses Company",
                    "organization_type": "company",
                    "username": "owner",
                    "email": "owner@example.org",
                    "name": "Synthetic Owner",
                    "password": "Synthetic123!",
                    "confirm_password": "Synthetic123!",
                }
                assert (
                    await http.post("/instance/bootstrap", json=params)
                ).status_code == 403
                params["setup_token"] = "synthetic-setup-code"
                stale = await http.post(
                    "/instance/bootstrap",
                    json={**params, "organization_uid": "old_company"},
                )
                assert stale.status_code == 409, stale.text
                assert "identifier has changed" in stale.json()["detail"]
                assert (await http.get("/instance")).json()["initialized"] is False
                same_username = await http.post(
                    "/instance/bootstrap", json={**params, "username": "company"}
                )
                assert same_username.status_code == 400, same_username.text
                assert (await http.get("/instance")).json()["initialized"] is False
                if confirmed_uid is not None:
                    params["organization_uid"] = confirmed_uid
                created = await http.post("/instance/bootstrap", json=params)
                assert created.status_code == 200, created.text
                data = created.json()
                assert data["organization"]["name"] == params["organization_name"]
                assert data["organization"]["organization_type"] == "company"
                assert data["organization"]["uid"] == "company"
                status = (await http.get("/instance")).json()
                assert status["initialized"] is True
                assert status["organization"]["uid"] == "company"
                assert (
                    await http.post("/instance/bootstrap", json=params)
                ).status_code == 409
                invitation = instance.CreateInvitationParams(email="member@example.org")
                assert invitation.project_role.value == 30
                monkeypatch.setattr(config, "DEPLOYMENT_MODE", "single_lab")
                assert (
                    instance.CreateInvitationParams(
                        email="member@example.org"
                    ).project_role.value
                    == 40
                )
            async with sessions() as db:
                project = (await db.execute(select(Project))).scalar_one()
                assert project.type == 1 and project.uid == "workspace"
                member = (await db.execute(select(LabUser))).scalar_one()
                assert project.organization_id == member.organization_id
        finally:
            await engine.dispose()
            async with admin.begin() as db:
                await db.execute(text(f"DROP SCHEMA {schema} CASCADE"))
            await admin.dispose()

    asyncio.run(run())
