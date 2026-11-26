"""Exercise the MCP transport and independent Platform identities against PostgreSQL."""

import asyncio
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.config import config
from app.database import get_db_session
from app.libs.external_request_boundary import ExternalRequestBoundary
from app.routers import external_access, meeting_sources, meeting_workspace, meetings
from tests.test_external_access_postgres import browser, delegated, grant
from tests.test_record_analysis_postgres import database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"), reason="Isolated PostgreSQL required"
)


@asynccontextmanager
async def agent(app, token):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app),
        base_url="http://test",
        headers=delegated(token),
    ) as http:
        async with streamable_http_client("http://test/mcp", http_client=http) as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session


def test_meeting_upload_visibility_and_retries(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")

    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            app = FastAPI()
            for router in (
                meetings.router,
                meeting_workspace.router,
                meeting_sources.router,
                external_access.router,
                external_access.mcp_router,
            ):
                app.include_router(router)
            app.add_middleware(ExternalRequestBoundary)

            async def session():
                async with sessions() as db:
                    yield db

            app.dependency_overrides[get_db_session] = session
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as http:
                # An ordinary member owns this organization meeting. The project owner is not invited.
                organizer, participant, other = seed.analyst, seed.recorder, seed.owner
                legacy = await grant(
                    http, seed, user=organizer, scopes=["collaboration:write"]
                )
                room_id = str(uuid4())
                room = "/meeting-workspace/rooms/" + room_id
                original = dict(
                    id=room_id,
                    lab_id=str(seed.lab.id),
                    title="Synthetic participants-only meeting",
                    body="Initial notes",
                    occurred_at="2026-01-02T10:00:00Z",
                    expected_revision=0,
                    participants=[str(participant.id)],
                    project_ids=[],
                )
                response = await http.put(
                    room, headers=browser(organizer), json=original
                )
                assert response.status_code == 200, response.text

                async def issue(user, **target):
                    response = await http.post(
                        "/external-access/grants",
                        headers=browser(user),
                        json=dict(
                            name="Synthetic meeting uploader",
                            scopes=["meetings:upload"],
                            expires_in_days=1,
                            **target,
                        ),
                    )
                    assert response.status_code == 200, response.text
                    return response.json()["token"]

                async def approve(user, op):
                    path = f"/external-access/operations/{op['id']}"
                    detail = await http.get(path, headers=browser(user))
                    assert detail.status_code == 200
                    assert detail.json()["summary"]["title"] == op["summary"]["title"]
                    assert detail.json()["payload"]["content"]
                    response = await http.post(
                        path + "/decision",
                        headers=browser(user),
                        json=dict(digest=op["digest"], approve=True),
                    )
                    assert response.status_code == 200, response.text

                org_target = dict(organization_id=str(seed.lab.id))
                project_target = dict(project_id=str(seed.project.id))
                token = await issue(organizer, **org_target)
                transcript = dict(
                    meeting_id=room_id,
                    filename="original.vtt",
                    request_key=uuid4().hex,
                    content="WEBVTT\r\n\r\n00:00:01.125 --> 00:00:02.500\r\n<v Alice>Private original</v>\r\n",
                )
                minutes = dict(
                    meeting_id=room_id,
                    filename="minutes.md",
                    request_key=uuid4().hex,
                    content="# Decisions\n\nPrivate minutes\n",
                )
                for denied_token in (
                    legacy["token"],
                    await issue(participant, **org_target),
                    await issue(other, **org_target),
                    await issue(organizer, **project_target),
                ):
                    async with agent(app, denied_token) as denied:
                        for content in [transcript, minutes]:
                            res = await denied.call_tool(
                                "preview_meeting_upload", content
                            )
                            assert (
                                res.isError
                                and "Synthetic participants-only" not in str(res)
                            )

                async with agent(app, token) as mcp:
                    tools = {t.name for t in (await mcp.list_tools()).tools}
                    assert {
                        "preview_meeting_upload",
                        "execute_operation",
                        "operation_status",
                    } <= tools
                    assert "create_private_project" not in tools
                    for data in [transcript, minutes]:
                        preview = await mcp.call_tool("preview_meeting_upload", data)
                        assert not preview.isError, preview
                        op = preview.structuredContent
                        assert (
                            op["state"] == "pending"
                            and "/settings?operation_id=" in op["confirmation_url"]
                        )
                        result_id = {"operation_id": op["id"]}
                        assert (
                            await mcp.call_tool("execute_operation", result_id)
                        ).isError
                        assert (
                            await http.get(
                                f"/external-access/operations/{op['id']}",
                                headers=browser(other),
                            )
                        ).status_code == 404
                        await approve(organizer, op)
                        done = await mcp.call_tool("execute_operation", result_id)
                        assert (
                            not done.isError
                            and done.structuredContent["state"] == "succeeded"
                        ), done
                        again = await mcp.call_tool("execute_operation", result_id)
                        assert (
                            again.structuredContent["result"]
                            == done.structuredContent["result"]
                        )
                        assert (
                            await mcp.call_tool("preview_meeting_upload", data)
                        ).structuredContent["id"] == op["id"]
                    assert (
                        await mcp.call_tool(
                            "preview_meeting_upload",
                            {
                                **transcript,
                                "request_key": uuid4().hex,
                                "content": "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nOther\n",
                            },
                        )
                    ).isError
                    assert (
                        await mcp.call_tool(
                            "preview_meeting_upload",
                            {**minutes, "visibility": "project"},
                        )
                    ).isError

                for user in [organizer, participant]:
                    response = await http.get(room, headers=browser(user))
                    assert (
                        response.json()["body"] == minutes["content"]
                        and response.json()["body_format"] == "md"
                    )
                    assert response.json()["participants"] == [str(participant.id)]
                    response = await http.get(
                        room + "/transcript/original", headers=browser(user)
                    )
                    assert response.content == transcript["content"].encode()
                    cues = (
                        await http.get(room + "/sources", headers=browser(user))
                    ).json()["transcript"]["cues"]
                    assert cues[0]["start"] == 1125 and cues[0]["speaker"] == "Alice"
                for path in [room, room + "/sources", room + "/transcript/original"]:
                    assert (
                        await http.get(path, headers=browser(other))
                    ).status_code == 404

                async with agent(app, token) as mcp:
                    stale = (
                        await mcp.call_tool(
                            "preview_meeting_upload",
                            {
                                **minutes,
                                "request_key": uuid4().hex,
                                "filename": "later.aimd",
                            },
                        )
                    ).structuredContent
                    await approve(organizer, stale)
                    changed = await http.put(
                        room,
                        headers=browser(organizer),
                        json={
                            **original,
                            "expected_revision": 2,
                            "body": minutes["content"],
                            "body_format": "md",
                            "title": "Updated meeting title",
                        },
                    )
                    assert changed.status_code == 200
                    assert (
                        await mcp.call_tool(
                            "execute_operation", {"operation_id": stale["id"]}
                        )
                    ).isError

                # A separately shared edition is pinned even when new minutes arrive.
                sharing = await http.put(
                    room + "/share",
                    headers=browser(organizer),
                    json={"revision": 3, "users": [str(other.id)]},
                )
                assert sharing.status_code == 200
                async with agent(app, token) as mcp:
                    updated = {
                        **minutes,
                        "request_key": uuid4().hex,
                        "content": "Later private minutes",
                    }
                    op = (
                        await mcp.call_tool("preview_meeting_upload", updated)
                    ).structuredContent
                    await approve(organizer, op)
                    result = await mcp.call_tool(
                        "execute_operation", {"operation_id": op["id"]}
                    )
                    assert not result.isError, result
                    assert result.structuredContent["result"]["links"] == [
                        f"/my-work?room={room_id}"
                    ]
                shared = (await http.get(room, headers=browser(other))).json()
                assert (
                    shared["revision"] == 3
                    and shared["body"] == minutes["content"].strip()
                )
                assert not shared["can_read_sources"]
                assert (
                    await http.get(
                        room + "/transcript/original", headers=browser(other)
                    )
                ).status_code == 404
                assert (await http.get(room, headers=browser(participant))).json()[
                    "body"
                ] == updated["content"]

                # A selected project editor can revise minutes. Original sources retain their stricter web ACL.
                mid = str(uuid4())
                obj = {
                    "id": mid,
                    **project_target,
                    "title": "Synthetic editor meeting",
                    "visibility": "selected",
                    "body": "First",
                    "occurred_at": "2026-01-03T10:00:00Z",
                    "participants": [
                        {
                            "user_id": str(organizer.id),
                            "attendance": "attended",
                            "name": organizer.name,
                        }
                    ],
                    "access": [{"user_id": str(organizer.id), "role": "editor"}],
                }
                response = await http.post(
                    "/meetings", headers=browser(seed.owner), json=obj
                )
                assert response.status_code == 200, response.text
                async with agent(
                    app, await issue(organizer, **project_target)
                ) as editor:
                    assert (
                        await editor.call_tool(
                            "preview_meeting_upload", {**transcript, "meeting_id": mid}
                        )
                    ).isError
                    data = {**minutes, "meeting_id": mid, "filename": "project.aimd"}
                    preview = await editor.call_tool("preview_meeting_upload", data)
                    assert not preview.isError, preview
                    op = preview.structuredContent
                    assert "/settings?operation_id=" in op["confirmation_url"]
                    await approve(organizer, op)
                    result = await editor.call_tool(
                        "execute_operation", {"operation_id": op["id"]}
                    )
                    assert not result.isError, result
                    pending = (
                        await editor.call_tool(
                            "preview_meeting_upload",
                            {**data, "request_key": uuid4().hex},
                        )
                    ).structuredContent
                    await approve(organizer, pending)
                    response = await http.get(
                        "/meetings/" + mid, headers=browser(seed.owner)
                    )
                    saved = response.json()
                    assert (
                        saved["body"] == minutes["content"]
                        and saved["body_format"] == "aimd"
                        and saved["visibility"] == "selected"
                    )
                    assert saved["access"] == obj["access"]
                    response = await http.put(
                        "/meetings/" + mid,
                        headers=browser(seed.owner),
                        json={
                            k: v
                            for k, v in {
                                **obj,
                                "expected_revision": saved["revision"],
                                "access": [],
                            }.items()
                            if k not in ("id", "project_id")
                        },
                    )
                    assert response.status_code == 200, response.text
                    assert (
                        await editor.call_tool(
                            "execute_operation", {"operation_id": pending["id"]}
                        )
                    ).isError
                    assert (
                        await editor.call_tool(
                            "operation_status", {"operation_id": op["id"]}
                        )
                    ).isError
                async with agent(
                    app, await issue(seed.owner, **project_target)
                ) as owner:
                    txt = {
                        **transcript,
                        "meeting_id": mid,
                        "filename": "private.txt",
                        "content": "Original project transcript",
                    }
                    op = (
                        await owner.call_tool("preview_meeting_upload", txt)
                    ).structuredContent
                    await approve(seed.owner, op)
                    result = await owner.call_tool(
                        "execute_operation", {"operation_id": op["id"]}
                    )
                    assert not result.isError, result
                    assert result.structuredContent["result"]["links"][0].endswith(
                        f"/meetings?meeting={mid}"
                    )
                project_source = f"/meeting-workspace/rooms/{mid}/transcript/original"
                assert (
                    await http.get(project_source, headers=browser(seed.owner))
                ).content == txt["content"].encode()
                assert (
                    await http.get(project_source, headers=browser(participant))
                ).status_code == 404
                async with agent(app, token) as org:
                    assert (
                        await org.call_tool(
                            "preview_meeting_upload", {**minutes, "meeting_id": mid}
                        )
                    ).isError

    asyncio.run(run())
