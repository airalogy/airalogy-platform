"""Synthetic workflows: contacts, account links, atomic actions and delegated scope."""

import asyncio
import os
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
import pytest
from app.config import config
from app.database import get_db_session
from app.models.project import ProjectUser
from app.models.project_person import ProjectPerson
from app.models.research import ResearchTask
from app.routers import external_access, meetings, project_people, project_work
from fastapi import FastAPI
from sqlalchemy import delete, select

from tests.test_external_access_postgres import browser, call, grant
from tests.test_record_analysis_postgres import database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"), reason="Isolated PostgreSQL required"
)


@asynccontextmanager
async def client(sessions):
    app = FastAPI()
    for module in [meetings, project_people, project_work, external_access]:
        app.include_router(module.router)

    async def db():
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_db_session] = db
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as http:
        yield http


@pytest.fixture(autouse=True)
def collaboration_mode(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


def test_name_then_admin_account_link_populates_my_tasks_without_granting_access():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            owner, analyst = browser(seed.owner), browser(seed.analyst)
            async with client(sessions) as http:
                person_data = {
                    "id": str(uuid4()),
                    "project_id": str(seed.project.id),
                    "name": "Synthetic colleague",
                }
                response = await http.post(
                    "/project-people", headers=analyst, json=person_data
                )
                assert response.status_code == 200, response.text
                person = response.json()
                same_name = await http.post(
                    "/project-people",
                    headers=analyst,
                    json={**person_data, "id": str(uuid4())},
                )
                assert (
                    same_name.status_code == 200
                    and same_name.json()["id"] != person["id"]
                )
                assert (
                    await http.post(
                        "/project-people", headers=analyst, json=person_data
                    )
                ).json()["id"] == person["id"]
                meeting_id = str(uuid4())
                meeting_response = await http.post(
                    "/meetings",
                    headers=owner,
                    json={
                        "id": meeting_id,
                        "project_id": str(seed.project.id),
                        "title": "Synthetic private meeting",
                        "occurred_at": "2020-01-02T00:00:00Z",
                        "visibility": "selected",
                        "participants": [
                            {"person_id": person["id"], "attendance": "attended"}
                        ],
                    },
                )
                assert meeting_response.status_code == 200, meeting_response.text
                work = {
                    "id": str(uuid4()),
                    "project_id": str(seed.project.id),
                    "title": "Synthetic task",
                    "assignee_person_id": person["id"],
                    "deadline_note": "Before the next meeting",
                }
                response = await http.post("/project-work", headers=owner, json=work)
                assert response.status_code == 200, response.text
                assert response.json()["planned_end"] is None
                assert response.json()["people_snapshot"][0]["name"] == person["name"]
                before = await http.get(
                    "/project-work", headers=analyst, params={"mine": True}
                )
                assert all(item["id"] != work["id"] for item in before.json()["items"])
                change = {
                    "name": person["name"],
                    "user_id": str(seed.analyst.id),
                    "expected_revision": 1,
                }
                assert (
                    await http.put(
                        f"/project-people/{person['id']}", headers=analyst, json=change
                    )
                ).status_code == 403
                # Association is not an invitation or implicit membership grant.
                assert (
                    await http.put(
                        f"/project-people/{person['id']}",
                        headers=owner,
                        json={**change, "user_id": str(seed.outsider.id)},
                    )
                ).status_code == 422
                response = await http.put(
                    f"/project-people/{person['id']}", headers=owner, json=change
                )
                assert response.status_code == 200, response.text
                assert (
                    await http.put(
                        f"/project-people/{person['id']}", headers=owner, json=change
                    )
                ).json()["revision"] == 2
                saved_meeting = (
                    await http.get(f"/meetings/{meeting_id}", headers=owner)
                ).json()
                assert saved_meeting["participants"][0]["name"] == person["name"]
                assert saved_meeting["participants"][0]["user_id"] is None
                assert (
                    await http.get(f"/meetings/{meeting_id}", headers=analyst)
                ).status_code == 404
                filtered = await http.get(
                    "/meetings",
                    headers=owner,
                    params={
                        "project_id": str(seed.project.id),
                        "participant_id": str(seed.analyst.id),
                    },
                )
                assert meeting_id in [m["id"] for m in filtered.json()["items"]]
                after = await http.get(
                    "/project-work", headers=analyst, params={"mine": True}
                )
                assert work["id"] in [item["id"] for item in after.json()["items"]]
                async with sessions() as db:
                    contact = await db.get(ProjectPerson, UUID(person["id"]))
                    assert len(
                        contact.account_history
                    ) == 1 and contact.account_history[0]["actor_id"] == str(
                        seed.owner.id
                    )
                    await db.execute(
                        delete(ProjectUser).where(
                            ProjectUser.project_id == seed.project.id,
                            ProjectUser.user_id == seed.analyst.id,
                        )
                    )
                    await db.commit()
                after_revocation = await http.get(
                    "/project-work", headers=analyst, params={"mine": True}
                )
                assert work["id"] not in [
                    item["id"] for item in after_revocation.json()["items"]
                ]

    asyncio.run(run())


def test_batch_is_atomic_revisioned_and_retry_safe_including_meeting_creation():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            owner = browser(seed.owner)
            async with client(sessions) as http:
                meeting_id, first, second = str(uuid4()), str(uuid4()), str(uuid4())
                content = {
                    "id": meeting_id,
                    "project_id": str(seed.project.id),
                    "title": "Synthetic design meeting",
                    "occurred_at": "2020-01-02T00:00:00Z",
                    "body": "Private source discussion",
                    "visibility": "selected",
                }
                batch = {
                    "request_id": str(uuid4()),
                    "expected_revision": 1,
                    "actions": [
                        {
                            "id": first,
                            "title": "Synthetic action one",
                            "goal": "Explicit task goal",
                            "deadline_note": "Next meeting",
                        },
                        {
                            "id": second,
                            "title": "Synthetic action two",
                            "assignee_person_id": str(uuid4()),
                        },
                    ],
                }
                invalid = await http.post(
                    "/meetings/with-actions",
                    headers=owner,
                    json={"meeting": content, "actions": batch},
                )
                assert invalid.status_code == 422, invalid.text
                assert (
                    await http.get(f"/meetings/{meeting_id}", headers=owner)
                ).status_code == 404
                assert (
                    await http.get(f"/project-work/{first}", headers=owner)
                ).status_code == 404
                batch["actions"][1].pop("assignee_person_id")
                response = await http.post(
                    "/meetings/with-actions",
                    headers=owner,
                    json={"meeting": content, "actions": batch},
                )
                assert response.status_code == 200, response.text
                assert len(response.json()["work"]) == 2
                retry = await http.post(
                    "/meetings/with-actions",
                    headers=owner,
                    json={"meeting": content, "actions": batch},
                )
                assert retry.status_code == 200 and len(retry.json()["work"]) == 2
                changed = {
                    **batch,
                    "actions": [
                        *batch["actions"],
                        {"id": str(uuid4()), "title": "Different batch"},
                    ],
                }
                assert (
                    await http.post(
                        f"/meetings/{meeting_id}/actions/batch",
                        headers=owner,
                        json=changed,
                    )
                ).status_code == 409
                stale = {
                    "request_id": str(uuid4()),
                    "expected_revision": 2,
                    "actions": [{"id": str(uuid4()), "title": "Stale"}],
                }
                assert (
                    await http.post(
                        f"/meetings/{meeting_id}/actions/batch",
                        headers=owner,
                        json=stale,
                    )
                ).status_code == 409
                action = (
                    await http.get(f"/project-work/{first}", headers=owner)
                ).json()
                assert (
                    action["goal"] == "Explicit task goal"
                    and action["planned_end"] is None
                )
                assert "Private source discussion" not in str(action)
                assert action["evidence"][0]["version"] == "1"

    asyncio.run(run())


def test_collaboration_mcp_scope_normal_permissions_and_committed_receipts():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            other = await seed_analysis(sessions)
            async with client(sessions) as http:
                token = (
                    await grant(
                        http, seed, scopes=["collaboration:read", "collaboration:write"]
                    )
                )["token"]
                read_only = (await grant(http, seed, scopes=["collaboration:read"]))[
                    "token"
                ]
                projects = await call(http, token, "list_projects")
                assert projects.status_code == 200, projects.text
                assert [p["id"] for p in projects.json()["items"]] == [
                    str(seed.project.id)
                ]
                person = await http.post(
                    "/external-access/tools/create_project_person",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"id": str(uuid4()), "name": "Synthetic visitor"},
                )
                assert person.status_code == 200, person.text
                item = {
                    "id": str(uuid4()),
                    "title": "Synthetic delegated task",
                    "assignee_person_id": person.json()["id"],
                }
                assert (
                    await call(http, read_only, "create_project_work", **item)
                ).status_code == 403
                result = await call(http, token, "create_project_work", **item)
                assert result.status_code == 200, result.text
                assert result.json()["saved"] and "/work?item=" in result.json()["url"]
                assert (await call(http, token, "create_project_work", **item)).json()[
                    "id"
                ] == item["id"]
                assert (
                    await call(
                        http,
                        token,
                        "create_project_work",
                        **{**item, "title": "Changed retry"},
                    )
                ).status_code == 409
                created = await http.post(
                    "/project-work",
                    headers=browser(other.owner),
                    json={
                        "id": str(uuid4()),
                        "project_id": str(other.project.id),
                        "title": "Other private task",
                    },
                )
                assert (
                    await call(http, token, "get_project_work", id=created.json()["id"])
                ).status_code in {403, 404}
                async with sessions() as db:
                    assert await db.get(ResearchTask, UUID(item["id"]))

    asyncio.run(run())


def test_independent_mcp_client_saves_and_reads_meeting_actions():
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    from tests.test_external_access_postgres import client as mcp_client

    async def run():
        async with database() as sessions, mcp_client(sessions) as http:
            seed = await seed_analysis(sessions)
            token = (
                await grant(
                    http, seed, scopes=["collaboration:read", "collaboration:write"]
                )
            )["token"]
            http.headers.update({"Authorization": f"Bearer {token}"})
            async with (
                streamable_http_client("http://test/mcp", http_client=http) as (
                    read,
                    write,
                    _,
                ),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert {
                    "create_meeting_with_actions",
                    "get_meeting",
                    "update_project_work",
                    "list_project_people",
                } <= names
                identity, task_id = str(uuid4()), str(uuid4())
                request = {
                    "id": identity,
                    "request_id": str(uuid4()),
                    "content": {
                        "title": "Synthetic MCP meeting",
                        "occurred_at": "2020-01-01T00:00:00Z",
                    },
                    "actions": [
                        {
                            "id": task_id,
                            "title": "Synthetic MCP action",
                            "deadline_note": "Next meeting",
                        }
                    ],
                }
                result = await session.call_tool("create_meeting_with_actions", request)
                assert not result.isError, result
                assert (
                    result.structuredContent["saved"]
                    and len(result.structuredContent["work"]) == 1
                )
                retry = await session.call_tool("create_meeting_with_actions", request)
                assert not retry.isError and len(retry.structuredContent["work"]) == 1
                read_back = await session.call_tool("get_meeting", {"id": identity})
                assert (
                    not read_back.isError
                    and read_back.structuredContent["work"][0]["item"]["id"] == task_id
                )
                assert (
                    "saved" in read_back.structuredContent
                    and read_back.structuredContent["saved"] is False
                )

    asyncio.run(run())
