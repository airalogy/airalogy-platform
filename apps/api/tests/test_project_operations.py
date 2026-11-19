"""The fictional instrument integration case, using real database and account ACLs."""

import asyncio
import os
from uuid import uuid4

import httpx
import pytest
from app.database import get_db_session
from app.models.knowledge import ResearchFile, ResearchFileBlob
from app.models.lab import LabRole, LabUser
from app.models.project import Project, ProjectRole, ProjectUser
from app.routers import knowledge, project_operations, project_work, research_documents
from fastapi import FastAPI
from sqlalchemy import update

from tests.test_external_access_postgres import browser
from tests.test_record_analysis_postgres import database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"), reason="Isolated PostgreSQL required"
)


def test_instrument_integration_books():
    asyncio.run(instrument_case())


async def instrument_case():
    async with database() as sessions:
        seed = await seed_analysis(sessions)
        foreign = await seed_analysis(sessions)
        seed.project.name = "仪器数据接入"
        book_id = str(seed.project.id)
        org = "/project-operations/organizations/" + str(seed.lab.id)
        book = "/project-operations/projects/" + book_id
        ceo, lead, finance, client, other = map(
            browser,
            (seed.owner, seed.analyst, seed.recorder, seed.outsider, foreign.owner),
        )
        async with sessions() as db:
            await db.merge(seed.project)
            for user, alias in ((seed.owner, "项目负责人"), (seed.recorder, "核账员")):
                await db.execute(
                    update(LabUser)
                    .where(LabUser.lab_id == seed.lab.id, LabUser.user_id == user.id)
                    .values(alias=alias)
                )
            db.add(
                LabUser(
                    lab_id=seed.lab.id,
                    user_id=seed.outsider.id,
                    role=LabRole.MEMBER,
                    create_user_id=seed.owner.id,
                )
            )
            db.add(
                ProjectUser(
                    project_id=seed.project.id,
                    user_id=seed.outsider.id,
                    role=ProjectRole.VIEWER,
                    create_user_id=seed.owner.id,
                )
            )
            blob = ResearchFileBlob(
                id=uuid4(),
                checksum_sha256=uuid4().hex * 2,
                content_type="text/plain",
                size_bytes=3,
                storage_object_key=str(uuid4()),
            )
            db.add(blob)
            await db.flush()
            file = ResearchFile(
                id=uuid4(),
                blob_id=blob.id,
                filename="synthetic-receipt.txt",
                scope_type="project",
                lab_id=seed.lab.id,
                project_id=seed.project.id,
                visibility="restricted",
                uploaded_by_user_id=seed.recorder.id,
            )
            db.add(file)
            await db.commit()
        app = FastAPI()
        for module in (project_operations, knowledge, research_documents, project_work):
            app.include_router(module.router)

        async def db_session():
            async with sessions() as db:
                yield db

        app.dependency_overrides[get_db_session] = db_session
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as http:

            async def call(method, path, who, data=None, status=200):
                r = await http.request(method, path, headers=who, json=data)
                assert r.status_code == status, (path, r.status_code, r.text)
                return r.json()

            async def write(
                who,
                kind,
                data,
                *,
                eid=None,
                rev=0,
                action="save",
                reason="",
                status=200,
            ):
                body = {
                    "request_id": str(uuid4()),
                    "entry_id": eid or str(uuid4()),
                    "expected_revision": rev,
                    "action": action,
                    "reason": reason,
                    "data": ({"kind": kind, **data} if data is not None else None),
                }
                await call("POST", book + "/entries", who, body, status)
                return body

            async def totals(who=ceo, as_of="2026-11-11"):
                result = await call("GET", book + "?as_of=" + as_of, who)
                p = await call("GET", org + "/overview?as_of=" + as_of, who)
                assert (
                    next(r for r in p["projects"] if str(r["id"]) == book_id)["summary"]
                    == result["summary"]
                )
                return result["summary"]

            def amounts(t, **expected):
                for k, v in expected.items():
                    assert t[k] == (None if v is None else 100 * v), (k, t[k], v)

            assert not (await call("GET", org + "/access", ceo))["enabled"]
            await call("GET", book, ceo, status=403)
            await call("PUT", org, lead, {"enabled": True, "expected_revision": 0}, 403)
            await call("PUT", org, ceo, {"enabled": True, "expected_revision": 0})
            await call("GET", book, ceo, status=403)
            grants = {
                str(seed.owner.id): "viewer",
                str(seed.analyst.id): "lead",
                str(seed.recorder.id): "finance",
            }
            await call(
                "PUT",
                book + "/settings",
                ceo,
                {"enabled": True, "expected_revision": 0, "grants": grants},
            )
            people = (await call("GET", book + "/settings", ceo))["people"]
            assert (
                next(u["name"] for u in people if u["id"] == str(seed.recorder.id))
                == "核账员"
            )
            assert (await call("GET", org + "/overview", ceo))["projects"][0]["owner"][
                "name"
            ] == "项目负责人"
            cost = {
                "title": "采集设备",
                "day": "2026-10-30",
                "category": "material",
                "direct": 600000,
                "payable": 600000,
            }
            c = (await write(lead, "cost", cost))["entry_id"]
            assert (await totals())["pending"] == 1
            await write(lead, "cost", None, eid=c, rev=1, action="verify", status=403)
            await write(
                finance,
                "cost",
                None,
                eid=c,
                rev=1,
                action="return",
                reason="补充采购说明",
            )
            await write(lead, "cost", cost, eid=c, rev=2, reason="补充完成")
            await write(finance, "cost", None, eid=c, rev=3, action="verify")
            assert (await call("GET", book, ceo))["people"][
                str(seed.recorder.id)
            ] == "核账员"
            events = (await call("GET", book + "/entries/" + c + "/history", ceo))[
                "events"
            ]
            assert events[-1]["actor"] == "核账员"
            payment = {
                "title": "设备首付",
                "day": "2026-10-30",
                "direction": "out",
                "cost_id": c,
                "amount": 400000,
            }
            await write(lead, "cash", payment, status=403)
            await write(finance, "cash", payment)
            amounts(
                await totals(),
                direct=6000,
                paid=4000,
                net_cash=-4000,
                unpaid=2000,
                profit=None,
            )
            contract = {
                "title": "合同 A",
                "state": "signed",
                "customer": "虚构客户",
                "gross": 10600000,
                "net": 10000000,
                "signed_date": "2026-11-01",
            }
            docid = str(uuid4())
            await call(
                "POST",
                "/research-documents",
                lead,
                {
                    "id": docid,
                    "scope_type": "project",
                    "project_id": book_id,
                    "title": "虚构签署件",
                    "body": "签署件原文",
                },
            )
            workid = str(uuid4())
            await call(
                "POST",
                "/project-work",
                lead,
                {
                    "id": workid,
                    "project_id": book_id,
                    "kind": "milestone",
                    "title": "内部技术交付",
                },
            )
            contract.update(signed_doc={"id": docid, "version": 1}, work_id=workid)
            a = (await write(lead, "contract", contract))["entry_id"]
            assert (
                await call("GET", book + "/entries/" + a + "/evidence/signed_doc", lead)
            )["body"] == "签署件原文"
            assert (
                workid
                in (
                    await call(
                        "GET", book + "/entries/" + a + "/evidence/work_id", lead
                    )
                )["href"]
            )
            await write(
                lead,
                "contract",
                {**contract, "signed_doc": {"id": docid, "version": 119}},
                status=422,
            )
            await write(
                lead,
                "cost",
                {**cost, "contract_id": a},
                eid=c,
                rev=4,
                reason="签约后归入 A",
            )
            estimate = {
                "day": "2026-11-05",
                "remaining": 3400000,
                "basis": "剩余实施人力",
            }
            f = (await write(lead, "forecast", estimate))["entry_id"]
            await write(
                finance, "closing", {"day": "2026-11-11", "basis": "核实至本日"}
            )
            amounts(await totals(), direct=6000, profit=60000)
            term = {
                "title": "首期",
                "amount": 5000000,
                "contract_id": a,
                "due": "2026-11-10",
            }
            first = (await write(lead, "installment", term))["entry_id"]
            tail = (
                await write(
                    lead,
                    "installment",
                    {
                        "title": "尾期",
                        "amount": 5600000,
                        "contract_id": a,
                        "condition": "客户签回后 30 天",
                    },
                )
            )["entry_id"]
            receipt = {
                "title": "首笔到账",
                "day": "2026-11-09",
                "direction": "in",
                "amount": 3000000,
                "proof_file_id": str(file.id),
            }
            receipt["contract_id"] = a
            r = await write(finance, "cash", receipt)
            assert (await totals())["contracts"][a]["outstanding"] == 10600000
            amounts(await totals(), unmatched=30000, received=30000)
            matched = await write(
                finance,
                "cash",
                {**receipt, "installment_id": first},
                eid=r["entry_id"],
                rev=1,
                reason="核销首期",
            )
            assert (await call("POST", book + "/entries", finance, matched))[
                "revision"
            ] == 2
            assert (await call("POST", book + "/entries", finance, r))["revision"] == 1
            t = await totals()
            amounts(t, overdue=20000, received=30000, net_cash=26000, profit=60000)
            assert (
                t["contracts"][a]["outstanding"] == 7600000
                and t["installments"][tail]["conditional"]
            )
            amounts(await totals(as_of="2026-11-10"), overdue=0)
            await write(
                finance, "cash", {**payment, "amount": 200000, "day": "2026-11-10"}
            )
            amounts(
                await totals(), paid=6000, net_cash=24000, direct=6000, profit=60000
            )
            await write(
                lead,
                "contract",
                {**contract, "title": "合同 B", "gross": 1000000, "net": 1000000},
            )
            shared = (
                await write(
                    lead,
                    "cost",
                    {**cost, "title": "共用", "direct": 100000, "payable": 100000},
                )
            )["entry_id"]
            await write(finance, "cost", None, eid=shared, rev=1, action="verify")
            amounts(
                await totals(),
                gross=116000,
                direct=7000,
                profit=69000,
                net_cash=24000,
                shared=1000,
            )
            await write(ceo, "cost", cost, status=403)
            for who in (client, other):
                await call("GET", book, who, status=403)
                await call("GET", book + "/entries/" + c + "/history", who, status=403)
                await call(
                    "GET",
                    book + "/entries/" + r["entry_id"] + "/evidence/proof_file_id",
                    who,
                    status=403,
                )
            assert (await call("GET", org + "/overview", client))["projects"] == []
            await call("GET", org + "/overview", other, status=403)
            await write(
                lead,
                "forecast",
                {**estimate, "remaining": None},
                eid=f,
                rev=1,
                reason="等待报价",
            )
            amounts(await totals(), profit=None)
            await write(
                lead,
                "forecast",
                {**estimate, "remaining": 0},
                eid=f,
                rev=2,
                reason="后续无投入",
            )
            amounts(await totals(), profit=103000)
            await write(
                lead, "forecast", estimate, eid=f, rev=1, reason="旧输入", status=409
            )
            await write(
                lead,
                "forecast",
                {**estimate, "remaining": 12000000},
                eid=f,
                rev=3,
                reason="新预算",
            )
            amounts(await totals(), profit=-17000)
            await write(
                finance,
                "cash",
                {**receipt, "amount": 3100000, "installment_id": first},
                eid=r["entry_id"],
                rev=2,
                reason="核对银行实收",
            )
            amounts(await totals(), net_cash=25000, overdue=19000)
            events = (
                await call("GET", book + "/entries/" + r["entry_id"] + "/history", ceo)
            )["events"]
            assert (
                events[-1]["before"]["data"]["amount"] == 3000000
                and events[-1]["after"]["data"]["amount"] == 3100000
            )
            assert (
                events[-1]["actor_id"] == str(seed.recorder.id)
                and events[-1]["after"]["verified_at"]
            )
            await write(
                finance,
                "cash",
                None,
                eid=r["entry_id"],
                rev=3,
                reason="重复银行流水",
                action="void",
            )
            amounts(await totals(), received=0, overdue=50000)
            # Another project ended before signature. Concurrent retries form a single entry.
            async with sessions() as db:
                stopped = Project(
                    id=uuid4(),
                    lab_id=seed.lab.id,
                    uid=uuid4().hex,
                    name="停止洽谈（虚构）",
                    create_user_id=seed.owner.id,
                    type=seed.project.type,
                )
                db.add(stopped)
                await db.flush()
                db.add(
                    ProjectUser(
                        project_id=stopped.id,
                        user_id=seed.owner.id,
                        role=ProjectRole.OWNER,
                        create_user_id=seed.owner.id,
                    )
                )
                await db.commit()
            stopped_url = "/project-operations/projects/" + str(stopped.id)
            await call(
                "PUT",
                stopped_url + "/settings",
                ceo,
                {
                    "enabled": True,
                    "expected_revision": 0,
                    "grants": {str(seed.owner.id): "finance"},
                },
            )
            body = {
                "request_id": str(uuid4()),
                "entry_id": str(uuid4()),
                "expected_revision": 0,
                "data": {"kind": "cost", **cost},
            }
            responses = await asyncio.gather(
                *(call("POST", stopped_url + "/entries", ceo, body) for _ in range(2))
            )
            assert responses[0] == responses[1]
            await call(
                "POST",
                stopped_url + "/entries",
                ceo,
                {
                    **body,
                    "request_id": str(uuid4()),
                    "entry_id": str(uuid4()),
                    "data": {**body["data"], "contract_id": a},
                },
                422,
            )
            updates = [
                {
                    **body,
                    "request_id": str(uuid4()),
                    "expected_revision": 1,
                    "action": "verify",
                    "data": None,
                }
                for _ in range(2)
            ]
            mutations = await asyncio.gather(
                *(
                    http.post(stopped_url + "/entries", headers=ceo, json=update)
                    for update in updates
                )
            )
            assert sorted(response.status_code for response in mutations) == [200, 409]
            grouped = (await call("GET", org + "/overview", ceo))["projects"]
            assert len(grouped) == 2
            stopped_result = next(
                row["summary"] for row in grouped if row["id"] == str(stopped.id)
            )
            amounts(stopped_result, gross=0, direct=6000, profit=None)
            assert len((await call("GET", org + "/overview", finance))["projects"]) == 1
            # Test a token issued while the viewer also has native restricted-file access.
            token = (
                await call(
                    "POST",
                    f"/knowledge/files/{file.id}/token",
                    ceo,
                    {"mode": "preview"},
                )
            )["url"]
            await call("PUT", org, ceo, {"enabled": False, "expected_revision": 1})
            await call("GET", book, lead, status=403)
            await call("GET", token, ceo, status=404)
            await call("PUT", org, ceo, {"enabled": True, "expected_revision": 2})
            amounts(await totals(), direct=7000)
            await call(
                "PUT",
                book + "/settings",
                ceo,
                {
                    "enabled": True,
                    "expected_revision": 1,
                    "grants": {
                        k: v for k, v in grants.items() if k != str(seed.owner.id)
                    },
                },
            )
            await call("GET", book, ceo, status=403)
            assert [
                row["id"]
                for row in (await call("GET", org + "/overview", ceo))["projects"]
            ] == [str(stopped.id)]
            await call("GET", token, ceo, status=404)
            await call(
                "POST",
                f"/knowledge/files/{file.id}/token",
                ceo,
                {"mode": "download"},
                404,
            )
