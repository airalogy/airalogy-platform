"""One organization, several accounts, both external transports and live role changes."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.models.external_access import ExternalAudit
from app.models.lab import LabRole, LabUser
from app.models.project_operations import (
    OperationsBook,
    OperationsEvent,
    OperationsGrant,
    OperationsOrganization,
)
from tests.test_external_access_postgres import (
    browser,
    call,
    client,
    delegated,
    grant,
    isolated_executor,  # noqa: F401
    seed,
)
from tests.test_record_analysis_postgres import database

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"), reason="Dedicated PostgreSQL required"
)


async def rpc(http, token, method, **params):
    response = await http.post(
        "/mcp",
        headers={
            **delegated(token),
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
    )
    assert response.status_code == 200, response.text
    return response.json()["result"]


async def issue(http, user, target, scopes):
    return await http.post(
        "/external-access/grants",
        headers=browser(user),
        json={**target, "name": "Synthetic user connection", "scopes": scopes},
    )


def test_personal_roles_project_registration_and_cash():
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            s = await seed(sessions)
            old = (await grant(http, s, scopes=["collaboration:read"]))["token"]
            org = {"organization_id": str(s.lab.id)}
            project = {"project_id": str(s.project.id)}
            org_scopes = ["projects:find", "projects:create"]
            assert (await issue(http, s.analyst, org, org_scopes)).status_code == 403
            assert (await issue(http, s.owner, org, ["cash:read"])).status_code == 422
            assert (
                await issue(http, s.owner, project, ["cash:read"])
            ).status_code == 403
            org_token = (await issue(http, s.owner, org, org_scopes)).json()["token"]
            tools = await rpc(http, org_token, "tools/list")
            assert {t["name"] for t in tools["tools"]} == {
                "access_context",
                "find_organization_project",
                "create_private_project",
            }
            assert (await call(http, old, "list_project_cash")).status_code == 403
            args = {
                "request_id": str(uuid4()),
                "uid": "demo_" + uuid4().hex[:12],
                "name": "Synthetic registration",
                "contract_number": "TEST-001",
            }
            results = await asyncio.gather(
                call(http, org_token, "create_private_project", **args),
                rpc(
                    http,
                    org_token,
                    "tools/call",
                    name="create_private_project",
                    arguments=args,
                ),
            )
            assert results[0].status_code == 200, results[0].text
            created = results[0].json()
            assert results[1]["structuredContent"] == created
            assert created["url"].endswith("/overview")
            assert (
                await call(
                    http,
                    org_token,
                    "find_organization_project",
                    by="contract_number",
                    query="test-001",
                )
            ).json()["items"] == [created]
            for changes in (
                {"name": "Changed request"},
                {
                    "request_id": str(uuid4()),
                    "uid": "other_demo",
                    "name": "Another project",
                },
            ):
                assert (
                    await call(
                        http, org_token, "create_private_project", **(args | changes)
                    )
                ).status_code == 409
            assert (await call(http, org_token, "list_project_cash")).status_code == 403
            async with sessions() as db:
                db.add(
                    OperationsOrganization(
                        organization_id=s.lab.id, enabled=True, revision=1
                    )
                )
                db.add(
                    OperationsBook(project_id=s.project.id, enabled=True, revision=1)
                )
                await db.flush()
                for user, role in [(s.analyst, "finance"), (s.recorder, "viewer")]:
                    db.add(
                        OperationsGrant(
                            project_id=s.project.id, user_id=user.id, role=role
                        )
                    )
                await db.commit()
            assert (
                await issue(http, s.owner, project, ["cash:create"])
            ).status_code == 403
            assert (
                await issue(http, s.recorder, project, ["cash:create"])
            ).status_code == 403
            viewer = (await issue(http, s.recorder, project, ["cash:read"])).json()[
                "token"
            ]
            finance = (
                await issue(http, s.analyst, project, ["cash:read", "cash:create"])
            ).json()["token"]
            cash = {
                "request_id": str(uuid4()),
                "cash": {
                    "kind": "cash",
                    "title": "Synthetic receipt",
                    "direction": "in",
                    "amount": 10000,
                    "day": "2025-01-10",
                },
            }
            assert (
                await rpc(
                    http,
                    viewer,
                    "tools/call",
                    name="record_project_cash",
                    arguments=cash,
                )
            )["isError"]
            assert (
                await call(
                    http,
                    finance,
                    "record_project_cash",
                    **cash,
                    project_id=created["id"],
                )
            ).status_code == 422
            first = await call(http, finance, "record_project_cash", **cash)
            assert first.status_code == 200, first.text
            replay = await rpc(
                http, finance, "tools/call", name="record_project_cash", arguments=cash
            )
            assert first.json() == replay["structuredContent"]
            assert (
                await call(
                    http,
                    finance,
                    "record_project_cash",
                    request_id=cash["request_id"],
                    cash={**cash["cash"], "amount": 1},
                )
            ).status_code == 409
            paid = await call(
                http,
                finance,
                "record_project_cash",
                request_id=str(uuid4()),
                cash={**cash["cash"], "direction": "out", "amount": 2501},
            )
            assert paid.status_code == 200, paid.text
            rows = (await call(http, viewer, "list_project_cash")).json()
            assert len(rows["items"]) == 2 and rows["totals"] == {
                "received": 10000,
                "paid": 2501,
                "net_cash": 7499,
            }
            async with sessions() as db:
                actors = (
                    await db.scalars(
                        select(OperationsEvent.actor_id).where(
                            OperationsEvent.project_id == s.project.id
                        )
                    )
                ).all()
                assert actors == [s.analyst.id, s.analyst.id]
                assert await db.scalar(
                    select(ExternalAudit.id).where(
                        ExternalAudit.user_id == s.analyst.id,
                        ExternalAudit.event == "tool.record_project_cash",
                    )
                )
                await db.execute(
                    update(OperationsGrant)
                    .where(
                        OperationsGrant.project_id == s.project.id,
                        OperationsGrant.user_id == s.analyst.id,
                    )
                    .values(role="viewer")
                )
                await db.execute(
                    update(LabUser)
                    .where(LabUser.lab_id == s.lab.id, LabUser.user_id == s.owner.id)
                    .values(role=LabRole.MEMBER)
                )
                await db.commit()
            assert (await call(http, org_token, "access_context")).status_code == 403
            assert (
                await call(http, finance, "record_project_cash", **cash)
            ).status_code == 403
            assert {
                t["name"] for t in (await rpc(http, finance, "tools/list"))["tools"]
            } == {"access_context", "list_project_cash"}
            assert (
                await rpc(
                    http,
                    finance,
                    "tools/call",
                    name="record_project_cash",
                    arguments=cash,
                )
            )["isError"]
            assert (await call(http, finance, "list_project_cash")).status_code == 200

    asyncio.run(scenario())
