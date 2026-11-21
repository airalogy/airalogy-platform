"""One organization, several accounts, both external transports and live role changes."""

import asyncio
import os
from uuid import UUID, uuid4

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
            ).status_code == 200
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


def test_fixed_and_ongoing_project_coverage():
    from sqlalchemy import delete
    from app.models.project import ProjectUser, ProjectRole

    async def scenario():
        async with database() as sessions, client(sessions) as http:
            s = await seed(sessions)
            await grant(http, s, scopes=["protocols:read"])
            org = {"organization_id": str(s.lab.id)}
            selected = {
                **org,
                "project_coverage": "selected",
                "selected_project_ids": [str(s.project.id)],
            }
            ongoing = {**org, "project_coverage": "accessible"}
            fixed = (await issue(http, s.analyst, selected, ["protocols:read"])).json()[
                "token"
            ]
            future = (await issue(http, s.analyst, ongoing, ["protocols:read"])).json()
            assert (
                await issue(
                    http,
                    s.analyst,
                    {
                        **ongoing,
                        "selected_project_ids": selected["selected_project_ids"],
                    },
                    ["protocols:read"],
                )
            ).status_code == 422
            assert (
                await issue(http, s.analyst, ongoing, ["projects:create"])
            ).status_code == 422
            assert (
                await issue(
                    http,
                    s.analyst,
                    {**selected, "selected_project_ids": [str(uuid4())]},
                    ["protocols:read"],
                )
            ).status_code == 403
            assert (await call(http, fixed, "list_protocols")).status_code == 422
            registry = (await issue(http, s.owner, org, ["projects:create"])).json()[
                "token"
            ]
            created = (
                await call(
                    http,
                    registry,
                    "create_private_project",
                    name="Synthetic second project",
                    uid="second_" + uuid4().hex[:8],
                    request_id=str(uuid4()),
                )
            ).json()["id"]

            async def ids(token):
                response = await call(http, token, "list_authorized_projects")
                assert response.status_code == 200, response.text
                return {row["id"] for row in response.json()["items"]}

            assert created not in await ids(future["token"])
            async with sessions() as db:
                db.add(
                    ProjectUser(
                        project_id=UUID(created),
                        user_id=s.analyst.id,
                        role=ProjectRole.COLLABORATOR,
                        create_user_id=s.owner.id,
                    )
                )
                await db.commit()
            assert created not in await ids(fixed)
            assert created in await ids(future["token"])
            # Confirmations keep their original project even under a connection spanning both.
            from tests.test_external_access_postgres import CSV

            writer = (
                await issue(
                    http, s.analyst, ongoing, ["protocols:read", "records:import"]
                )
            ).json()["token"]
            preview = await call(
                http,
                writer,
                "preview_import",
                project_id=str(s.project.id),
                protocol_id=str(s.protocol.id),
                csv=CSV,
                request_key="project-bound-preview",
            )
            assert preview.status_code == 200, preview.text
            operation_id = preview.json()["id"]
            other = await call(
                http,
                writer,
                "operation_status",
                project_id=created,
                operation_id=operation_id,
            )
            assert other.status_code == 404
            own = await http.get(
                "/external-access/operations/" + operation_id,
                headers=browser(s.analyst),
                params={"project_id": str(s.project.id)},
            )
            assert own.status_code == 200, own.text
            assert (
                await call(http, fixed, "list_protocols", project_id=created)
            ).status_code == 403
            tools = (await rpc(http, future["token"], "tools/list"))["tools"]
            assert (
                "project_id"
                in next(t for t in tools if t["name"] == "list_protocols")[
                    "inputSchema"
                ]["required"]
            )
            result = await rpc(
                http,
                future["token"],
                "tools/call",
                name="access_context",
                arguments={"project_id": created},
            )
            assert result["structuredContent"]["project"]["id"] == created
            async with sessions() as db:
                await db.execute(
                    delete(ProjectUser).where(
                        ProjectUser.project_id == UUID(created),
                        ProjectUser.user_id == s.analyst.id,
                    )
                )
                await db.commit()
            assert created not in await ids(future["token"])
            assert (
                await call(http, future["token"], "list_protocols", project_id=created)
            ).status_code == 403
            assert (
                await http.delete(
                    "/external-access/grants/" + future["grant"]["id"],
                    headers=browser(s.owner),
                )
            ).status_code == 404
            assert (
                await http.delete(
                    "/external-access/grants/" + future["grant"]["id"],
                    headers=browser(s.analyst),
                )
            ).status_code == 200
            assert (
                await call(http, future["token"], "list_authorized_projects")
            ).status_code == 401

    asyncio.run(scenario())


def test_contract_and_existing_receipt_in_one_connection():
    async def scenario():
        async with database() as sessions, client(sessions) as http:
            s = await seed(sessions)
            project = {"project_id": str(s.project.id)}
            scopes = [
                "contracts:read",
                "contracts:create",
                "cash:read",
                "cash:create",
                "cash:link",
            ]
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
                db.add(
                    OperationsGrant(
                        project_id=s.project.id, user_id=s.analyst.id, role="finance"
                    )
                )
                await db.commit()
            old = (
                await grant(
                    http, s, user=s.analyst, scopes=["cash:read", "cash:create"]
                )
            )["token"]
            owner_token = (await issue(http, s.owner, project, scopes)).json()["token"]
            assert (
                await call(http, owner_token, "list_project_contracts")
            ).status_code == 200
            assert (await issue(http, s.analyst, project, scopes)).status_code == 403
            async with sessions() as db:
                grant_row = await db.get(OperationsGrant, (s.project.id, s.analyst.id))
                grant_row.role = "lead_finance"
                await db.commit()
            token = (await issue(http, s.analyst, project, scopes)).json()["token"]
            names = {t["name"] for t in (await rpc(http, token, "tools/list"))["tools"]}
            assert {
                "register_project_contract",
                "link_project_receipt",
                "list_project_contracts",
            } <= names
            assert (await call(http, old, "list_project_contracts")).status_code == 403
            lookup = {"number": "  Test-001 "}
            assert (await call(http, token, "list_project_contracts", **lookup)).json()[
                "items"
            ] == []
            contract = {
                "request_id": str(uuid4()),
                "contract": {
                    "kind": "contract",
                    "number": "TEST-001",
                    "title": "Synthetic contract",
                    "state": "signed",
                    "signed_date": "2025-03-03",
                    "gross": 24700,
                    "customer": "Example lab",
                },
            }
            first = (
                await rpc(
                    http,
                    token,
                    "tools/call",
                    name="register_project_contract",
                    arguments=contract,
                )
            )["structuredContent"]
            assert (
                await call(http, token, "register_project_contract", **contract)
            ).json() == first
            assert (
                await call(
                    http,
                    token,
                    "register_project_contract",
                    **(contract | {"request_id": str(uuid4())}),
                )
            ).status_code == 409
            cash = {
                "request_id": str(uuid4()),
                "cash": {
                    "kind": "cash",
                    "direction": "in",
                    "receipt_purpose": "customer_receipt",
                    "amount": 24700,
                    "day": "2025-03-12",
                    "title": "Synthetic income",
                },
            }
            receipt = (await call(http, old, "record_project_cash", **cash)).json()
            link = {
                "request_id": str(uuid4()),
                "contract_id": first["id"],
                "cash_id": receipt["id"],
                "expected_revision": 1,
            }
            assert (
                await call(http, old, "link_project_receipt", **link)
            ).status_code == 403
            for changes, status in [
                ({"cash_id": str(uuid4())}, 404),
                ({"contract_id": str(uuid4())}, 404),
                ({"expected_revision": 5}, 409),
            ]:
                assert (
                    await call(http, token, "link_project_receipt", **(link | changes))
                ).status_code == status
            saved = (
                await rpc(
                    http,
                    token,
                    "tools/call",
                    name="link_project_receipt",
                    arguments=link,
                )
            )["structuredContent"]
            assert saved["id"] == receipt["id"] and saved["revision"] == 2
            assert (
                await call(http, token, "link_project_receipt", **link)
            ).json() == saved
            assert (
                await call(
                    http,
                    token,
                    "link_project_receipt",
                    **(link | {"contract_id": str(uuid4())}),
                )
            ).status_code == 409
            rows = (await call(http, token, "list_project_cash")).json()["items"]
            assert len(rows) == 1 and rows[0]["data"]["contract_id"] == first["id"]
            summary = (
                await call(http, token, "list_project_contracts", **lookup)
            ).json()
            assert summary["totals"] == {
                "gross": 24700,
                "contract_received": 24700,
                "contract_remaining": 0,
            }
            assert [
                (r["id"], r["received"], r["remaining"]) for r in summary["items"]
            ] == [(first["id"], 24700, 0)]
            async with sessions() as db:
                role = await db.get(OperationsGrant, (s.project.id, s.analyst.id))
                role.role = "viewer"
                await db.commit()
            assert (
                await call(http, token, "link_project_receipt", **link)
            ).status_code == 403
            assert (
                await call(http, token, "register_project_contract", **contract)
            ).status_code == 403

    asyncio.run(scenario())
