"""Meetings: real project permissions, shared document identity and atomic actions."""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import delete, func, select

from app.database import get_db_session
from app.models.meeting import MeetingWorkLink
from app.models.project import ProjectUser
from app.models.research import ResearchTask
from app.routers import meetings, project_work, research_documents, research_log
from app.routers.depends import create_access_token
from app.services.meetings import MeetingContent
from tests.test_record_analysis_postgres import database, seed_analysis


@pytest.mark.parametrize(
    "change",
    [
        {"title": " "},
        {"occurred_at": None},
        {"occurred_at": "2020-01-01T10:00:00"},
        {"occurred_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()},
        {"time_zone": "No/SuchZone"},
        {"participants": [{"name": " "}]},
        {"access": [{"user_id": str(uuid4()), "role": "owner"}]},
    ],
)
def test_meeting_contract_does_not_invent_attendance_or_time(change):
    with pytest.raises(ValidationError):
        MeetingContent.model_validate(
            {
                "title": "Synthetic meeting",
                "occurred_at": "2020-03-15T23:30:00Z",
                **change,
            }
        )


def test_preparation_does_not_require_schedule_or_actual_time():
    item = MeetingContent(title="Synthetic agenda", status="planned")
    assert item.occurred_at is None and item.scheduled_at is None
    assert not item.participants and not item.access


@asynccontextmanager
async def client(sessions):
    app = FastAPI()
    for module in [meetings, research_documents, research_log, project_work]:
        app.include_router(module.router)

    async def session():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db_session] = session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as http:
        yield http


integration = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"), reason="Isolated PostgreSQL required"
)


@integration
def test_meeting_acl_all_entrypoints_timezone_and_atomic_action():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions, public=True)
            owner = {"Auth-Token": create_access_token(seed.owner)}
            analyst = {"Auth-Token": create_access_token(seed.analyst)}
            outsider = {"Auth-Token": create_access_token(seed.outsider)}
            identity = str(uuid4())
            data = {
                "id": identity,
                "project_id": str(seed.project.id),
                "title": "Synthetic selected meeting",
                "body": "Private discussion and evidence",
                "visibility": "selected",
                "occurred_at": "2020-03-15T23:30:00Z",
                "time_zone": "Asia/Shanghai",
                "time_precision": "datetime",
                "participants": [
                    {"user_id": str(seed.analyst.id), "attendance": "attended"},
                    {
                        "name": "Synthetic external visitor",
                        "organization": "Synthetic partner",
                        "attendance": "invited",
                    },
                ],
            }
            async with client(sessions) as http:

                async def get(path, headers=owner, **params):
                    return await http.get(path, headers=headers, params=params)

                response = await http.post("/meetings", headers=owner, json=data)
                assert response.status_code == 200, response.text
                meeting = response.json()
                assert len(meeting["participants"]) == 2 and meeting["revision"] == 1
                assert (await http.post("/meetings", headers=owner, json=data)).json()[
                    "id"
                ] == identity
                changed_create = await http.post(
                    "/meetings",
                    headers=owner,
                    json={**data, "title": "Different request"},
                )
                assert changed_create.status_code == 409
                # Attendance is not access; public project status is not meeting access.
                for who in [analyst, outsider]:
                    for path in [
                        f"/meetings/{identity}",
                        f"/research-documents/{identity}",
                        f"/research-documents/{identity}/revisions",
                        f"/research-log/entries/{identity}",
                        f"/research-log/entries/{identity}/revisions",
                    ]:
                        assert (await get(path, who)).status_code in [403, 404], path
                params = {
                    "scope_type": "project",
                    "project_id": str(seed.project.id),
                    "source": "meeting",
                    "time_zone": "Asia/Shanghai",
                }
                assert (
                    await get("/meetings", analyst, project_id=str(seed.project.id))
                ).json()["total"] == 0
                assert (
                    await get(
                        "/research-documents",
                        analyst,
                        scope_type="project",
                        project_id=str(seed.project.id),
                    )
                ).json()["total_count"] == 0
                assert (
                    await get(
                        "/research-documents/calendar",
                        analyst,
                        scope_type="project",
                        project_id=str(seed.project.id),
                        month="2020-03-01",
                        time_zone="Asia/Shanghai",
                    )
                ).json()["days"] == []
                assert (
                    await get(
                        "/project-work/sources",
                        analyst,
                        project_id=str(seed.project.id),
                    )
                ).json()["items"] == []
                assert (await get("/research-log/summary", analyst, **params)).json()[
                    "total_count"
                ] == 0
                summary = (await get("/research-log/summary", **params)).json()
                assert summary["summary"] == [{"date": "2020-03-16", "count": 1}], (
                    summary
                )
                timeline = (
                    await get(
                        "/research-log/timeline",
                        **params,
                        date_from="2020-03-16",
                        date_to="2020-03-16",
                    )
                ).json()
                assert (
                    timeline["total_count"] == 1
                    and timeline["items"][0]["id"] == identity
                )
                assert timeline["items"][0]["meeting_id"] == identity
                assert timeline["items"][0]["meeting_time_precision"] == "datetime"
                action = {
                    "id": str(uuid4()),
                    "expected_revision": 1,
                    "title": "Synthetic follow-up",
                    "assignee_user_id": str(seed.owner.id),
                }
                created = await http.post(
                    f"/meetings/{identity}/actions", json=action, headers=owner
                )
                assert created.status_code == 200, created.text
                assert (
                    await http.post(
                        f"/meetings/{identity}/actions", json=action, headers=owner
                    )
                ).status_code == 200
                assert (
                    await http.post(
                        f"/meetings/{identity}/actions",
                        json={**action, "title": "Changed retry"},
                        headers=owner,
                    )
                ).status_code == 409
                async with sessions() as db:
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(MeetingWorkLink)
                            .where(MeetingWorkLink.meeting_id == UUID(identity))
                        )
                        == 1
                    )
                work = (await get("/project-work/" + action["id"], analyst)).json()
                assert work["title"] == action["title"]
                assert work["evidence"][0]["available"] is False
                assert "Private discussion" not in str(work)
                invalid = {
                    **action,
                    "id": str(uuid4()),
                    "assignee_user_id": str(seed.outsider.id),
                }
                assert (
                    await http.post(
                        f"/meetings/{identity}/actions", json=invalid, headers=owner
                    )
                ).status_code == 422
                async with sessions() as db:
                    assert await db.get(ResearchTask, UUID(invalid["id"])) is None
                content = {
                    k: v for k, v in meeting.items() if k in MeetingContent.model_fields
                }
                content["access"] = [
                    {"user_id": str(seed.analyst.id), "role": "editor"}
                ]
                changed = await http.put(
                    f"/meetings/{identity}",
                    headers=owner,
                    json={**content, "expected_revision": 1},
                )
                assert changed.status_code == 200, changed.text
                assert (await get(f"/meetings/{identity}", analyst)).json()["can_edit"]
                document = (
                    await get(f"/research-documents/{identity}", analyst)
                ).json()
                assert not document["can_edit"]
                assert document["meeting_url"].endswith(f"/meetings?meeting={identity}")
                from fastapi import HTTPException

                from app.routers.research_documents import _context

                async with sessions() as db:
                    with pytest.raises(HTTPException) as denied:
                        await _context(db, seed.analyst, UUID(identity), write=True)
                    assert denied.value.status_code == 409

                assert (
                    await http.put(
                        f"/meetings/{identity}",
                        headers=owner,
                        json={**content, "expected_revision": 1},
                    )
                ).status_code == 409
                comment = {"id": str(uuid4()), "body": "Synthetic additional fact"}
                assert (
                    await http.post(
                        f"/meetings/{identity}/comments", headers=analyst, json=comment
                    )
                ).status_code == 200
                assert (
                    await http.post(
                        f"/meetings/{identity}/comments", headers=analyst, json=comment
                    )
                ).status_code == 200
                assert (await get(f"/meetings/{identity}/comments", analyst)).json()[
                    "total"
                ] == 1
                assert (await get("/research-log/summary", analyst, **params)).json()[
                    "total_count"
                ] == 1
                assert (
                    await http.post(
                        "/research-documents",
                        headers=analyst,
                        json={
                            "scope_type": "project",
                            "project_id": str(seed.project.id),
                            "title": "Wider copy",
                            "source_document_id": identity,
                        },
                    )
                ).status_code == 403
                prepared = {
                    **data,
                    "id": str(uuid4()),
                    "title": "Synthetic preparation",
                    "status": "planned",
                    "occurred_at": None,
                }
                assert (
                    await http.post("/meetings", headers=owner, json=prepared)
                ).status_code == 200
                assert (await get("/research-log/summary", **params)).json()[
                    "total_count"
                ] == 1
                # Revoking underlying project access takes effect even when a meeting grant remains.
                async with sessions() as db:
                    await db.execute(
                        delete(ProjectUser).where(
                            ProjectUser.project_id == seed.project.id,
                            ProjectUser.user_id == seed.analyst.id,
                        )
                    )
                    await db.commit()
                updated_after_departure = await http.put(
                    f"/meetings/{identity}",
                    headers=owner,
                    json={
                        **content,
                        "expected_revision": 2,
                        "body": "Historical attendees preserved",
                    },
                )
                assert updated_after_departure.status_code == 200, (
                    updated_after_departure.text
                )
                assert (
                    updated_after_departure.json()["participants"]
                    == changed.json()["participants"]
                )
                assert (await get(f"/meetings/{identity}", analyst)).status_code in [
                    403,
                    404,
                ]

    asyncio.run(run())


@integration
def test_meeting_activity_pagination_counts_every_day_without_counting_edits():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            owner = {"Auth-Token": create_access_token(seed.owner)}
            async with client(sessions) as http:
                for index in range(3):
                    data = {
                        "id": str(uuid4()),
                        "project_id": str(seed.project.id),
                        "title": f"Synthetic meeting {index}",
                        "occurred_at": "2020-01-01T10:00:00Z",
                    }
                    response = await http.post("/meetings", headers=owner, json=data)
                    assert response.status_code == 200, response.text
                    item = response.json()
                    content = {
                        k: v
                        for k, v in item.items()
                        if k in MeetingContent.model_fields
                    }
                    for revision in [1, 2]:
                        r = await http.put(
                            "/meetings/" + item["id"],
                            headers=owner,
                            json={
                                **content,
                                "body": f"Edit {revision}",
                                "expected_revision": revision,
                            },
                        )
                        assert r.status_code == 200, r.text
                params = {
                    "scope_type": "project",
                    "project_id": str(seed.project.id),
                    "source": "meeting",
                    "date_from": "2020-01-01",
                    "date_to": "2020-01-01",
                    "time_zone": "UTC",
                }
                summary = (
                    await http.get(
                        "/research-log/summary", headers=owner, params=params
                    )
                ).json()
                timeline = (
                    await http.get(
                        "/research-log/timeline",
                        headers=owner,
                        params={**params, "page_size": 1, "page": 2},
                    )
                ).json()
                assert summary["total_count"] == timeline["total_count"] == 3
                assert summary["summary"] == [{"date": "2020-01-01", "count": 3}]
                assert len(timeline["items"]) == 1
                assert timeline["items"][0]["meeting_time_precision"] == "date"

    asyncio.run(run())


@integration
def test_private_project_reader_sees_meetings_when_protocol_access_is_denied():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions, public=False)
            async with sessions() as db:
                membership = await db.scalar(
                    select(ProjectUser).where(
                        ProjectUser.project_id == seed.project.id,
                        ProjectUser.user_id == seed.analyst.id,
                    )
                )
                membership.role = (
                    60  # Existing VIEWER can read project logs, not private Protocols.
                )
                await db.commit()
            owner = {"Auth-Token": create_access_token(seed.owner)}
            viewer = {"Auth-Token": create_access_token(seed.analyst)}
            async with client(sessions) as http:
                response = await http.post(
                    "/meetings",
                    headers=owner,
                    json={
                        "id": str(uuid4()),
                        "project_id": str(seed.project.id),
                        "title": "Synthetic readable meeting",
                        "occurred_at": "2020-01-01T10:00:00Z",
                    },
                )
                assert response.status_code == 200, response.text
                identity = response.json()["id"]
                for source, count in [
                    ("all", 1),
                    ("meeting", 1),
                    ("protocol", 0),
                    ("record", 0),
                ]:
                    params = {
                        "scope_type": "project",
                        "project_id": str(seed.project.id),
                        "source": source,
                    }
                    summary = await http.get(
                        "/research-log/summary", headers=viewer, params=params
                    )
                    timeline = await http.get(
                        "/research-log/timeline", headers=viewer, params=params
                    )
                    assert summary.status_code == timeline.status_code == 200, (
                        summary.text,
                        timeline.text,
                    )
                    assert (
                        summary.json()["total_count"]
                        == timeline.json()["total_count"]
                        == count
                    )
                    if count:
                        assert timeline.json()["items"][0]["id"] == identity

    asyncio.run(run())
