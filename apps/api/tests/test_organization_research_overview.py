import asyncio
from uuid import uuid4

from sqlalchemy import select
from app.models.lab import LabRole, LabUser
from app.routers.depends import create_access_token
from tests.test_meetings import client
from tests.test_project_work import draft, integration
from tests.test_record_analysis_postgres import database, seed_analysis


@integration
def test_live_roles_open_plans_and_local_day_across_project_activities():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            foreign = await seed_analysis(sessions)
            async with sessions() as db:
                member = await db.scalar(
                    select(LabUser).where(
                        LabUser.lab_id == seed.lab.id, LabUser.user_id == seed.owner.id
                    )
                )
                member.alias = "Synthetic owner alias"
                await db.commit()
            owner = {"Auth-Token": create_access_token(seed.owner)}
            member = {"Auth-Token": create_access_token(seed.analyst)}
            outsider = {"Auth-Token": create_access_token(foreign.owner)}
            path = f"/project-work/organizations/{seed.lab.id}/overview"
            scope = {
                "scope_type": "lab",
                "lab_id": str(seed.lab.id),
                "organization_overview": True,
                "date_from": "2022-03-16",
                "date_to": "2022-03-16",
                "time_zone": "Asia/Shanghai",
            }
            async with client(sessions) as http:
                for values in [
                    dict(
                        state="blocked",
                        blocker="Awaiting fixture",
                        next_step="Check connector",
                    ),
                    dict(kind="milestone", title="Later", planned_end="2027-02-15"),
                    dict(kind="milestone", title="Earlier", planned_end="2027-02-01"),
                ]:
                    response = await http.post(
                        "/project-work",
                        headers=owner,
                        json=draft(seed.project, **values),
                    )
                    assert response.is_success, response.text
                result = (await http.get(path, headers=owner)).json()["projects"]
                assert len(result) == 1
                assert result[0]["owners"] == ["Synthetic owner alias"]
                assert result[0]["blockers"][0]["text"] == "Awaiting fixture"
                assert result[0]["next_steps"][0]["text"] == "Check connector"
                assert result[0]["milestone"]["title"] == "Earlier"
                for who in [member, outsider]:
                    assert (await http.get(path, headers=who)).status_code == 403
                    for endpoint in ["summary", "timeline"]:
                        assert (
                            await http.get(
                                "/research-log/" + endpoint, params=scope, headers=who
                            )
                        ).status_code == 403
                for kind, identity in [
                    ("project", seed.project.id),
                    ("personal", None),
                ]:
                    r = await http.post(
                        "/research-log/entries",
                        headers=owner,
                        json={
                            "scope_type": kind,
                            "project_id": str(identity) if identity else None,
                            "kind": "progress",
                            "title": f"Synthetic {kind} note",
                            "occurred_at": "2022-03-15T23:30:00Z",
                        },
                    )
                    assert r.is_success, r.text
                daily = await http.get(
                    "/research-log/timeline", params=scope, headers=owner
                )
                assert [x["title"] for x in daily.json()["items"]] == [
                    "Synthetic project note"
                ]
                restricted = await http.post(
                    "/meetings",
                    headers=member,
                    json={
                        "id": str(uuid4()),
                        "project_id": str(seed.project.id),
                        "title": "Selected meeting",
                        "occurred_at": "2022-03-15T21:30:00Z",
                        "time_zone": "Asia/Shanghai",
                        "time_precision": "datetime",
                        "visibility": "selected",
                        "participants": [],
                    },
                )
                assert restricted.is_success, restricted.text
                timeline = await http.get(
                    "/research-log/timeline", params=scope, headers=owner
                )
                assert timeline.json()["total_count"] == 1
                summary = await http.get(
                    "/research-log/summary", params=scope, headers=owner
                )
                assert summary.json()["summary"] == [{"date": "2022-03-16", "count": 1}]
                async with sessions() as db:
                    m = await db.scalar(
                        select(LabUser).where(
                            LabUser.lab_id == seed.lab.id,
                            LabUser.user_id == seed.owner.id,
                        )
                    )
                    m.role = LabRole.MANAGER
                    await db.commit()
                assert (await http.get(path, headers=owner)).is_success
                async with sessions() as db:
                    m = await db.scalar(
                        select(LabUser).where(
                            LabUser.lab_id == seed.lab.id,
                            LabUser.user_id == seed.owner.id,
                        )
                    )
                    m.role = LabRole.MEMBER
                    await db.commit()
                assert (await http.get(path, headers=owner)).status_code == 403
                assert (
                    await http.get(
                        "/research-log/timeline", params=scope, headers=owner
                    )
                ).status_code == 403

    asyncio.run(run())
