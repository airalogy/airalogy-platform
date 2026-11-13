"""Project onboarding uses live permissions and never leaks cross-project reports."""

import asyncio
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete

from app.models.analysis import AnalysisRun
from app.models.external_research import ExternalAnalysisSource
from app.models.lab import LabUser
from app.models.project import Project, ProjectUser
from tests.test_external_access_postgres import (
    approve,
    browser,
    call,
    client,
    grant,
    isolated_executor,  # noqa: F401 -- shared pytest fixture
    seed,
)
from tests.test_external_research_postgres import request_snapshot, submission
from tests.test_record_analysis_postgres import add_record, database

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Isolated PostgreSQL required",
)


def test_project_dashboard_filters_before_limits_and_respects_current_permissions():
    async def scenario():
        async with database() as sessions:
            scope = await seed(sessions)
            await add_record(sessions, scope, 2)
            async with sessions() as db:
                other = Project(
                    id=uuid4(),
                    lab_id=scope.lab.id,
                    uid=f"synthetic_{uuid4().hex}",
                    name="Synthetic other project",
                    create_user_id=scope.owner.id,
                    type=1,
                )
                db.add(other)
                await db.flush()
                db.add(
                    ProjectUser(
                        project_id=other.id,
                        user_id=scope.owner.id,
                        role=1,
                        create_user_id=scope.owner.id,
                    )
                )
                await db.commit()
            async with client(sessions) as http:
                first = await grant(http, scope)
                second = await grant(
                    http,
                    SimpleNamespace(owner=scope.owner, lab=scope.lab, project=other),
                )
                snapshot_response = await call(
                    http, first["token"], "create_snapshot", **request_snapshot(scope)
                )
                assert snapshot_response.status_code == 200, snapshot_response.text
                op = (
                    await call(
                        http,
                        first["token"],
                        "preview_analysis",
                        **submission(snapshot_response.json()),
                    )
                ).json()
                path = f"/labs/{scope.lab.uid}/projects/{scope.project.uid}/analysis?view=external"
                assert op["confirmation_url"].endswith(
                    f"{path}&operation_id={op['id']}"
                )
                assert (
                    await http.get(
                        f"/external-access/operations/{op['id']}?project_id={other.id}",
                        headers=browser(scope.owner),
                    )
                ).status_code == 404
                await approve(http, scope, op)
                executed = await call(
                    http, first["token"], "execute_operation", operation_id=op["id"]
                )
                assert executed.status_code == 200, executed.text
                result = executed.json()["result"]
                assert result["links"] == [f"{path}&analysis_id={result['run_id']}"]
                run_id = UUID(result["run_id"])
                # More than a page of newer rows in another project must not hide this result.
                # The source is intentionally no longer readable in that project.
                async with sessions() as db:
                    run = await db.get(AnalysisRun, run_id)
                    columns = {
                        c.name: getattr(run, c.name)
                        for c in AnalysisRun.__table__.columns
                    }
                    for number in range(51):
                        db.add(
                            AnalysisRun(
                                **{
                                    **columns,
                                    "id": uuid4(),
                                    "project_id": other.id,
                                    "client_idempotency_key": uuid4().hex,
                                    "created_at": run.created_at
                                    + timedelta(seconds=number + 1),
                                }
                            )
                        )
                    await db.commit()
                response = await http.get(
                    f"/external-access/dashboard?project_id={scope.project.id}",
                    headers=browser(scope.owner),
                )
                assert response.status_code == 200, response.text
                dashboard = response.json()
                assert [r["id"] for r in dashboard["analyses"]] == [str(run_id)]
                assert dashboard["analysis_next_offset"] is None
                assert [g["id"] for g in dashboard["grants"]] == [first["grant"]["id"]]
                assert [o["id"] for o in dashboard["operations"]] == [op["id"]]
                assert all(
                    a["grant_id"] != second["grant"]["id"] for a in dashboard["audit"]
                )
                assert dashboard["projects"][0]["can_export"] is True
                assert dashboard["projects"][0]["can_author"] is True
                # Pagination preserves access-checked reports across successive pages.
                async with sessions() as db:
                    link = await db.get(ExternalAnalysisSource, run_id)
                    for number in range(51):
                        cloned_id = uuid4()
                        db.add(
                            AnalysisRun(
                                **{
                                    **columns,
                                    "id": cloned_id,
                                    "client_idempotency_key": uuid4().hex,
                                    "created_at": run.created_at
                                    + timedelta(seconds=number + 1),
                                }
                            )
                        )
                        await db.flush()
                        db.add(
                            ExternalAnalysisSource(
                                run_id=cloned_id,
                                snapshot_id=link.snapshot_id,
                                grant_id=link.grant_id,
                            )
                        )
                    await db.commit()
                first_page = (
                    await http.get(
                        f"/external-access/dashboard?project_id={scope.project.id}",
                        headers=browser(scope.owner),
                    )
                ).json()
                assert len(first_page["analyses"]) == 50
                assert first_page["analysis_next_offset"] == 50
                last_page = (
                    await http.get(
                        f"/external-access/dashboard?project_id={scope.project.id}&analysis_offset=50",
                        headers=browser(scope.owner),
                    )
                ).json()
                assert len(last_page["analyses"]) == 2
                assert last_page["analysis_next_offset"] is None
                assert {r["id"] for r in first_page["analyses"]}.isdisjoint(
                    r["id"] for r in last_page["analyses"]
                )
                assert str(run_id) in [r["id"] for r in last_page["analyses"]]
                for user, project_id in [
                    (scope.owner, other.id),
                    (scope.outsider, scope.project.id),
                ]:
                    assert (
                        await http.get(
                            f"/external-access/analyses/{run_id}?project_id={project_id}",
                            headers=browser(user),
                        )
                    ).status_code == 404
                assert (
                    await http.get(
                        f"/external-access/dashboard?project_id={scope.project.id}",
                        headers=browser(scope.outsider),
                    )
                ).status_code == 404
                recorder = (
                    await http.get(
                        f"/external-access/dashboard?project_id={scope.project.id}",
                        headers=browser(scope.recorder),
                    )
                ).json()
                assert recorder["projects"][0]["can_export"] is False
                # The existing private-project Recorder role can create its own Protocols.
                assert recorder["projects"][0]["can_author"] is True
                assert recorder["analyses"] == []
                # Membership removal also removes previously accessible reports and dashboard.
                async with sessions() as db:
                    await db.execute(
                        delete(ProjectUser).where(ProjectUser.user_id == scope.owner.id)
                    )
                    await db.execute(
                        delete(LabUser).where(LabUser.user_id == scope.owner.id)
                    )
                    await db.commit()
                assert (
                    await http.get(
                        f"/external-access/dashboard?project_id={scope.project.id}",
                        headers=browser(scope.owner),
                    )
                ).status_code == 404
                assert (
                    await http.get(
                        f"/external-access/analyses/{run_id}",
                        headers=browser(scope.owner),
                    )
                ).status_code != 200

    asyncio.run(scenario())


def test_authoring_preset_recognizes_protocol_specific_editors():
    async def scenario():
        from sqlalchemy import update

        from app.models.project import ProjectRole, ProjectType
        from app.models.protocol import Protocol

        async with database() as sessions:
            scope = await seed(sessions)
            async with sessions() as db:
                await db.execute(
                    update(Project)
                    .where(Project.id == scope.project.id)
                    .values(type=ProjectType.PUBLIC)
                )
                await db.execute(
                    update(ProjectUser)
                    .where(
                        ProjectUser.project_id == scope.project.id,
                        ProjectUser.user_id == scope.analyst.id,
                    )
                    .values(role=ProjectRole.VIEWER)
                )
                await db.commit()
            async with client(sessions) as http:
                url = f"/external-access/dashboard?project_id={scope.project.id}"
                before = await http.get(url, headers=browser(scope.analyst))
                assert before.status_code == 200, before.text
                assert before.json()["projects"][0]["can_author"] is False
                async with sessions() as db:
                    await db.execute(
                        update(Protocol)
                        .where(Protocol.id == scope.protocol.id)
                        .values(user_id=scope.analyst.id)
                    )
                    await db.commit()
                after = await http.get(url, headers=browser(scope.analyst))
                assert after.status_code == 200, after.text
                assert after.json()["projects"][0]["can_author"] is True
                assert after.json()["projects"][0]["can_export"] is False

    asyncio.run(scenario())
