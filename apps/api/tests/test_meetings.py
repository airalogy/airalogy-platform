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
from app.models.meeting import MeetingAccess, MeetingWorkLink
from app.models.project import ProjectUser
from app.models.research import ResearchTask
from app.routers import (
    labs,
    meetings,
    project_people,
    project_work,
    research_documents,
    research_log,
    user_aliases,
)
from app.routers.chats import index as chat_history
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
    for module in [
        labs,
        meetings,
        project_people,
        research_documents,
        research_log,
        project_work,
        user_aliases,
    ]:
        app.include_router(module.router)

    app.include_router(chat_history.router, prefix="/chats")

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
                doc_scope = {
                    "scope_type": "project",
                    "project_id": str(seed.project.id),
                }
                default = (await get("/research-documents", **doc_scope)).json()
                assert default["items"] == [] and default["has_searchable_items"]
                for who in [owner, analyst]:
                    found = (
                        await get(
                            "/research-documents",
                            who,
                            q="Private discussion",
                            **doc_scope,
                        )
                    ).json()
                    days = (
                        await get(
                            "/research-documents/calendar",
                            who,
                            q="Private discussion",
                            month="2020-03-01",
                            **doc_scope,
                        )
                    ).json()["days"]
                    if who == owner:
                        assert found["total_count"] == 1
                        assert found["items"][0]["meeting_url"].endswith(
                            f"/meetings?meeting={identity}"
                        )
                        assert days == [{"date": "2020-03-15", "count": 1}]
                    else:
                        assert found["items"] == [] and not days
                assert not (
                    await get("/research-documents", analyst, **doc_scope)
                ).json()["has_searchable_items"]
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


def test_action_reserves_one_evidence_slot_for_its_meeting_source():
    from app.routers.meetings import Action

    refs = [{"kind": "external", "id": f"https://example.test/{i}"} for i in range(50)]
    with pytest.raises(ValidationError):
        Action(id=uuid4(), expected_revision=1, title="Synthetic action", evidence=refs)
    assert (
        len(
            Action(
                id=uuid4(),
                expected_revision=1,
                title="Synthetic action",
                evidence=refs[:49],
            ).evidence
        )
        == 49
    )


@integration
def test_activity_groups_only_same_transaction_for_meeting_readers():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions, public=False)
            owner = {"Auth-Token": create_access_token(seed.owner)}
            viewer = {"Auth-Token": create_access_token(seed.analyst)}
            meeting_id = str(uuid4())
            project = str(seed.project.id)
            async with client(sessions) as http:
                meeting = await http.post(
                    "/meetings",
                    headers=owner,
                    json={
                        "id": meeting_id,
                        "project_id": project,
                        "title": "Private prototype review",
                        "visibility": "selected",
                        "occurred_at": "2020-01-02T00:00:00Z",
                    },
                )
                assert meeting.status_code == 200, meeting.text
                task_ids = set()
                for size in [4, 2]:
                    actions = [
                        {"id": str(uuid4()), "title": f"Follow-up {n}"}
                        for n in range(size)
                    ]
                    task_ids.update(a["id"] for a in actions)
                    batch = {
                        "request_id": str(uuid4()),
                        "expected_revision": 1,
                        "actions": actions,
                    }
                    for _ in range(2):
                        saved = await http.post(
                            f"/meetings/{meeting_id}/actions/batch",
                            headers=owner,
                            json=batch,
                        )
                        assert saved.status_code == 200, saved.text
                params = {
                    "scope_type": "project",
                    "project_id": project,
                    "source": "research",
                    "group_meeting_actions": True,
                }

                async def timeline(headers, **options):
                    r = await http.get(
                        "/research-log/timeline",
                        headers=headers,
                        params={**params, **options},
                    )
                    assert r.status_code == 200, r.text
                    return r.json()

                visible = await timeline(owner, page_size=100)
                groups = [
                    row
                    for row in visible["items"]
                    if row["event_type"] == "work.meeting_batch"
                ]
                assert [row["payload"]["count"] for row in groups] == [2, 4]
                assert all(row["asset"]["id"] == meeting_id for row in groups)
                individual = await timeline(
                    owner, group_meeting_actions=False, page_size=100
                )
                assert individual["total_count"] == visible["total_count"] + 4
                hidden = await timeline(viewer, page_size=100)
                assert all(
                    row["event_type"] != "work.meeting_batch" for row in hidden["items"]
                )
                assert meeting_id not in str(
                    hidden
                ) and "Private prototype review" not in str(hidden)
                assert task_ids <= {
                    row.get("asset", {}).get("id") for row in hidden["items"]
                }
                summary = await http.get(
                    "/research-log/summary", headers=owner, params=params
                )
                assert summary.json()["total_count"] == visible["total_count"]

    asyncio.run(run())


@integration
def test_aira_meeting_draft_checks_writer_and_instance_and_only_returns_proposal(
    monkeypatch,
):
    calls = []

    async def fake_model(prompt, model, *, usage_context, max_response_bytes):
        calls.append(usage_context)
        assert "Synthetic discussion" in prompt
        return {
            "message": "Review your draft",
            "draft": {
                "title": "Synthetic draft",
                "body": "Decision pending.",
                "actions": ["Check fit"],
            },
        }

    from app.services import meeting_drafts

    monkeypatch.setattr(meeting_drafts, "aira_structured_proposal", fake_model)
    monkeypatch.setattr(meetings.config, "DASHSCOPE_API_KEY", "synthetic-unused")
    monkeypatch.setattr(meetings.config, "AI_ENABLED", False)

    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            project_id = str(seed.project.id)
            owner = {"Auth-Token": create_access_token(seed.owner)}
            outsider = {"Auth-Token": create_access_token(seed.outsider)}
            data = {"project_id": project_id, "message": "Synthetic discussion"}
            async with client(sessions) as http:
                endpoint = "/meetings/aira/draft"
                assert (
                    await http.post(endpoint, headers=owner, json=data)
                ).status_code == 503
                monkeypatch.setattr(meetings.config, "AI_ENABLED", True)
                assert (
                    await http.post(endpoint, headers=outsider, json=data)
                ).status_code == 403
                assert not calls
                availability = await http.get(
                    "/meetings/aira/availability",
                    headers=owner,
                    params={"project_id": project_id},
                )
                assert availability.json() == {"available": True}
                response = await http.post(endpoint, headers=owner, json=data)
                assert response.status_code == 200, response.text
                assert response.json()["draft"]["occurred_on"] is None
                assert calls[0].project_id == project_id
                assert calls[0].tenant_id == str(seed.project.lab_id)
                chat_id = response.json()["id"]
                detail_path = f"/meetings/aira/conversations/{chat_id}"
                listed_history = await http.get("/chats/history/global", headers=owner)
                assert listed_history.status_code == 200, listed_history.text
                assert [row["id"] for row in listed_history.json()["items"]] == [
                    chat_id
                ]
                row = listed_history.json()["items"][0]
                assert (
                    row["kind"] == "meeting" and row["project_uid"] == seed.project.uid
                )
                assert (
                    await http.get(detail_path, headers=outsider)
                ).status_code == 404
                assert not (
                    await http.get("/chats/history/global", headers=outsider)
                ).json()["items"]
                first = (await http.get(detail_path, headers=owner)).json()
                assert first["turns"] == [
                    {"user": "Synthetic discussion", "reply": "Review your draft"}
                ]
                resume = {
                    **data,
                    "message": "Synthetic discussion continued",
                    "conversation_id": chat_id,
                    "expected_turns": 1,
                    "request_id": str(uuid4()),
                }
                continued = await http.post(endpoint, headers=owner, json=resume)
                assert continued.status_code == 200, continued.text
                assert len(continued.json()["turns"]) == 2
                assert (
                    await http.post(endpoint, headers=owner, json=resume)
                ).json() == continued.json()
                assert len(calls) == 2
                assert (
                    await http.post(
                        endpoint,
                        headers=owner,
                        json={**resume, "request_id": str(uuid4())},
                    )
                ).status_code == 409
                assert (await http.get(detail_path, headers=owner)).json()["proposal"][
                    "title"
                ] == "Synthetic draft"
                listed = await http.get(
                    "/meetings", headers=owner, params={"project_id": project_id}
                )
                assert listed.json()["total"] == 0

                # A project writer's personal history still respects a private
                # meeting grant when its author later withdraws that grant.
                writer = {"Auth-Token": create_access_token(seed.analyst)}
                meeting_id = str(uuid4())
                meeting = await http.post(
                    "/meetings",
                    headers=owner,
                    json={
                        "id": meeting_id,
                        "project_id": project_id,
                        "title": "Synthetic restricted meeting",
                        "status": "planned",
                        "visibility": "selected",
                        "access": [{"user_id": str(seed.analyst.id), "role": "viewer"}],
                    },
                )
                assert meeting.status_code == 200, meeting.text
                scoped = {**data, "meeting_id": meeting_id}
                saved = await http.post(endpoint, headers=writer, json=scoped)
                assert saved.status_code == 200, saved.text
                saved_id = saved.json()["id"]
                assert [
                    item["id"]
                    for item in (
                        await http.get("/chats/history/global", headers=writer)
                    ).json()["items"]
                ] == [saved_id]
                async with sessions() as db:
                    await db.execute(
                        delete(MeetingAccess).where(
                            MeetingAccess.meeting_id == UUID(meeting_id),
                            MeetingAccess.user_id == seed.analyst.id,
                        )
                    )
                    await db.commit()
                assert not (
                    await http.get("/chats/history/global", headers=writer)
                ).json()["items"]
                assert (
                    await http.get(
                        f"/meetings/aira/conversations/{saved_id}", headers=writer
                    )
                ).status_code == 404
                denied = await http.post(
                    endpoint,
                    headers=writer,
                    json={**scoped, "conversation_id": saved_id, "expected_turns": 1},
                )
                assert denied.status_code == 404
                assert len(calls) == 3

    asyncio.run(run())


@integration
def test_organization_display_name_scope_permissions_and_research_identity():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            other = await seed_analysis(sessions)
            account_id = str(seed.analyst.id)
            project_id = str(seed.project.id)
            owner = {"Auth-Token": create_access_token(seed.owner)}
            manager = {"Auth-Token": create_access_token(seed.recorder)}
            member = {"Auth-Token": create_access_token(seed.analyst)}
            path = f"/labs/{seed.lab.id}/users/{account_id}"

            async with client(sessions) as http:

                async def rename(name, headers):
                    return await http.put(
                        path,
                        headers=headers,
                        json={"user_id": account_id, "alias": name},
                    )

                assert (await rename("Denied", member)).status_code == 403
                promote = await http.put(
                    f"/labs/{seed.lab.id}/users/{seed.recorder.id}",
                    headers=owner,
                    json={"user_id": str(seed.recorder.id), "role": 2},
                )
                assert promote.status_code == 200
                assert (
                    await rename("  Synthetic Team Name  ", manager)
                ).status_code == 200
                denied = await http.put(
                    f"/labs/{seed.lab.id}/users/{seed.owner.id}",
                    headers=manager,
                    json={"user_id": str(seed.owner.id), "alias": "Denied"},
                )
                assert denied.status_code == 403
                add_other = await http.post(
                    f"/labs/{other.lab.id}/users",
                    headers={"Auth-Token": create_access_token(other.owner)},
                    json={"user_id": account_id, "alias": "Other team"},
                )
                assert add_other.status_code == 200, add_other.text

                private = await http.post(
                    "/users/set_user_alias",
                    headers=owner,
                    json={
                        "target_user_id": account_id,
                        "alias": "Synthetic private note",
                    },
                )
                assert private.status_code == 200
                for observer, expected in [
                    (owner, "Synthetic private note"),
                    (member, None),
                ]:
                    lookup = await http.post(
                        "/users/get_user_aliases",
                        headers=observer,
                        json={
                            "user_ids": [account_id],
                            "lab_id": str(seed.lab.id),
                        },
                    )
                    assert lookup.status_code == 200, lookup.text
                    assert lookup.json()[0]["lab_alias"] == "Synthetic Team Name"
                    assert lookup.json()[0]["user_alias"] == expected
                outside = await http.post(
                    "/users/get_user_aliases",
                    headers=owner,
                    json={
                        "user_ids": [account_id],
                        "lab_id": str(other.lab.id),
                    },
                )
                assert outside.status_code == 403

                work_id = str(uuid4())
                work = await http.post(
                    "/project-work",
                    headers=owner,
                    json={
                        "id": work_id,
                        "project_id": project_id,
                        "title": "Synthetic ownership",
                        "assignee_user_id": account_id,
                    },
                )
                assert work.status_code == 200, work.text
                for endpoint in ("/project-work/members", "/meetings/members"):
                    response = await http.get(
                        endpoint, params={"project_id": project_id}, headers=owner
                    )
                    choice = next(
                        m for m in response.json()["members"] if m["id"] == account_id
                    )
                    assert (
                        choice["display_name"],
                        choice["name"],
                        choice["username"],
                    ) == (
                        "Synthetic Team Name",
                        seed.analyst.name,
                        seed.analyst.username,
                    )
                meeting = await http.post(
                    "/meetings",
                    headers=owner,
                    json={
                        "id": str(uuid4()),
                        "project_id": project_id,
                        "title": "Synthetic check",
                        "status": "planned",
                        "participants": [{"user_id": account_id}],
                    },
                )
                assert meeting.status_code == 200, meeting.text
                saved = meeting.json()
                assert saved["participants"][0]["name"] == "Synthetic Team Name"
                # A role-only save must retain the organization name.
                promoted = await http.put(
                    path, headers=owner, json={"user_id": account_id, "role": 2}
                )
                assert promoted.status_code == 200
                assert (await rename("Denied", manager)).status_code == 403
                org_members = (
                    await http.get(f"/labs/{seed.lab.id}/users", headers=owner)
                ).json()["users"]
                row = next(m for m in org_members if m["id"] == account_id)
                assert (row["lab_alias"], row["lab_role"]) == ("Synthetic Team Name", 2)
                assert (await rename(None, owner)).status_code == 200
                org_members = (
                    await http.get(f"/labs/{seed.lab.id}/users", headers=owner)
                ).json()["users"]
                row = next(m for m in org_members if m["id"] == account_id)
                assert (row["lab_alias"], row["lab_role"]) == (None, 2)
                choices = (
                    await http.get(
                        "/meetings/members",
                        params={"project_id": project_id},
                        headers=owner,
                    )
                ).json()["members"]
                assert (
                    next(m["display_name"] for m in choices if m["id"] == account_id)
                    == seed.analyst.name
                )
                other_members = (
                    await http.get(
                        f"/labs/{other.lab.id}/users",
                        headers={"Auth-Token": create_access_token(other.owner)},
                    )
                ).json()["users"]
                assert (
                    next(m["lab_alias"] for m in other_members if m["id"] == account_id)
                    == "Other team"
                )
                mine = await http.get(
                    "/project-work",
                    params={"project_id": project_id, "mine": True},
                    headers=member,
                )
                assert any(
                    w["id"] == work_id and w["assignee_user_id"] == account_id
                    for w in mine.json()["items"]
                )
                reread = await http.get(f"/meetings/{saved['id']}", headers=owner)
                assert reread.json()["participants"] == saved["participants"]

    asyncio.run(run())
