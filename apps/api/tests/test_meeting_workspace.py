"""Meeting identity, transcript interchange, selective disclosure and retry behavior."""

import asyncio
from uuid import uuid4

import httpx
import pytest
from app.database import get_db_session
from app.routers import meeting_sources, meeting_workspace, my_work
from app.routers.depends import create_access_token
from app.services.meeting_transcript import export_transcript, parse_transcript
from fastapi import FastAPI

from tests.test_meetings import integration
from tests.test_record_analysis_postgres import database, seed_analysis

VTT = """WEBVTT

00:00:01.125 --> 00:00:03.250
<v 小王>明天答复。</v>
<v Alice>收到。</v>

00:00:04.000 --> 00:00:05.000
<v 小王>再见。</v>
"""


def test_speakers_and_milliseconds_roundtrip():
    cues = parse_transcript("original.vtt", VTT.encode())
    assert [(c.speaker, c.text) for c in cues[:2]] == [
        ("小王", "明天答复。"),
        ("Alice", "收到。"),
    ]
    assert all(c.account_id is None for c in cues)
    for fmt in ("srt", "vtt"):
        assert (
            parse_transcript("copy." + fmt, export_transcript(cues, fmt).encode())
            == cues
        )
    assert cues[0].start == 1125 and cues[0].end == 3250
    assert "小王" in export_transcript(cues, "txt")
    untimed = parse_transcript("plain.txt", "张三：稍后答复".encode())
    assert untimed[0].start is None
    with pytest.raises(ValueError):
        export_transcript(untimed, "vtt")
    with pytest.raises(ValueError):
        parse_transcript(
            "bad.srt",
            b"1\n00:00:01,000 --> 00:00:02,000\nGood\n\n2\nINVALID --> 00:00:04,100\nBad\n",
        )


def test_match_prefers_attending_accounts_and_preserves_ambiguity():
    def person(id, participant):
        return dict(
            id=id, name="小王", username=id, aliases=["王"], participant=participant
        )

    cues = [{"speaker": "小王"}, {"speaker": "王"}, {"speaker": "游客"}]
    people = [person("other", False), person("one", True), person("two", True)]
    matches = meeting_sources.suggestions(cues, people)
    assert matches == {
        "小王": ["one", "two", "other"],
        "王": ["one", "two", "other"],
        "游客": [],
    }
    assert meeting_sources.suggestions([{"speaker": "＠ＯＮＥ"}], people) == {
        "＠ＯＮＥ": ["one"]
    }


@integration
def test_organization_conversation_and_independent_audiences(monkeypatch):
    from datetime import timedelta

    from app.models.project import Project, ProjectRole, ProjectType, ProjectUser
    from app.models.project_guest import ProjectGuest
    from app.models.user import User
    from app.services.meeting_drafts import DraftReply, MeetingProposal
    from app.services.single_lab import utcnow

    blobs = {}

    async def upload(key, stream, mime, size, backend):
        blobs[key] = stream.read()

    async def playback(key, backend):
        yield blobs[key]

    async def ai(turn, model, usage):
        assert "明天答复" in turn.message
        return DraftReply(
            message="Review",
            draft=MeetingProposal(
                title="Draft only", body="Proposal", actions=["Send list"]
            ),
        )

    monkeypatch.setattr(meeting_sources, "upload_file", upload)
    monkeypatch.setattr(meeting_sources, "get_file_with_stream", playback)
    monkeypatch.setattr(meeting_sources, "require_ai_enabled", lambda: None)
    monkeypatch.setattr(meeting_sources, "draft_meeting", ai)
    monkeypatch.setattr(meeting_sources, "enabled_chat_model_types", lambda: (1,))

    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            app = FastAPI()
            for module in (meeting_workspace, meeting_sources, my_work):
                app.include_router(module.router)

            async def session():
                async with sessions() as db:
                    yield db

            app.dependency_overrides[get_db_session] = session
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as http:

                async def call(method, path, who=seed.owner, code=200, **kwargs):
                    response = await http.request(
                        method,
                        path,
                        headers={"Auth-Token": create_access_token(who)},
                        **kwargs,
                    )
                    assert response.status_code == code, response.text
                    return response

                uid = lambda user: str(user.id)
                room_id = str(uuid4())
                base = "/meeting-workspace/rooms/" + room_id
                org = str(seed.lab.id)
                room = dict(
                    id=room_id,
                    lab_id=org,
                    title="Strategy",
                    body="Approved summary",
                    occurred_at="2023-01-10T10:00:00Z",
                    body_format="md",
                    expected_revision=0,
                    participants=[uid(seed.analyst)],
                    project_ids=[],
                )
                assert (await call("PUT", base, json=room)).json()["revision"] == 1
                assert (await call("PUT", base, json=room)).json()["revision"] == 1
                await call("GET", base, seed.analyst)
                await call("GET", base, seed.outsider, 404)
                original = VTT.replace("小王", seed.recorder.name).encode()
                await call(
                    "POST",
                    base + "/transcript",
                    files={"file": ("meeting.vtt", original)},
                )
                cues = (await call("GET", base + "/sources", seed.analyst)).json()[
                    "transcript"
                ]["cues"]
                assert all(c["account_id"] is None for c in cues)
                choices = (await call("GET", base + "/speakers")).json()
                assert choices["matches"][seed.recorder.name] == [uid(seed.recorder)]
                cues[0]["account_id"] = uid(seed.recorder)
                bad = [dict(cues[0], account_id=uid(seed.outsider))]
                await call(
                    "PUT",
                    base + "/transcript",
                    json=dict(expected_revision=1, cues=bad),
                    code=422,
                )
                edit = dict(expected_revision=1, cues=cues)
                await call("PUT", base + "/transcript", json=edit)
                await call("PUT", base + "/transcript", json=edit, code=409)
                assert (
                    await call("GET", base + "/transcript/original")
                ).content == original
                recording = b"RIFF-synthetic-file"
                await call(
                    "POST",
                    base + "/audio",
                    files={"file": ("recording.wav", recording)},
                )
                assert (
                    await call("GET", base + "/audio", seed.analyst)
                ).content == recording
                assert (await call("POST", base + "/draft")).json()["actions"] == [
                    "Send list"
                ]
                assert (await call("GET", base)).json()["body"] == "Approved summary"
                for path in (
                    "",
                    "/sources",
                    "/audio",
                    "/speakers",
                    "/transcript/vtt",
                    "/actions",
                ):
                    await call("GET", base + path, seed.recorder, 404)
                assert (
                    "Strategy"
                    not in (
                        await call(
                            "GET", "/my-work?period=past&scope=visible", seed.recorder
                        )
                    ).text
                )
                task_id = str(uuid4())
                action = dict(
                    id=task_id,
                    title="Send agenda",
                    audience="selected",
                    expected_revision=1,
                    assignee_id=uid(seed.recorder),
                )
                await call("POST", base + "/actions", json=action)
                await call("POST", base + "/actions", json=action)
                task = "/meeting-workspace/tasks/" + task_id
                result = (await call("GET", task, seed.recorder)).json()
                assert result["title"] == "Send agenda" and "meeting_id" not in result
                await call("GET", task, seed.analyst, 404)
                todos = (
                    await call("GET", "/my-work?view=todos", seed.recorder)
                ).json()["items"]
                assert [item["id"] for item in todos].count(task_id) == 1
                await call(
                    "PATCH",
                    task,
                    seed.recorder,
                    json=dict(expected_revision=1, state="done"),
                )
                private_id = str(uuid4())
                await call(
                    "POST",
                    base + "/actions",
                    json=dict(id=private_id, title="Private memo", expected_revision=1),
                )
                await call(
                    "GET", "/meeting-workspace/tasks/" + private_id, seed.analyst, 404
                )
                mine = (await call("GET", "/my-work?period=past")).json()["items"]
                assert (
                    next(item["open_count"] for item in mine if item["id"] == room_id)
                    == 1
                )
                await call(
                    "PUT",
                    base + "/share",
                    json=dict(revision=1, users=[uid(seed.recorder)]),
                )
                room.update(
                    expected_revision=1,
                    body="Unshared negotiation",
                    title="New private title",
                    project_ids=[str(seed.project.id)],
                )
                await call("PUT", base, json=room)
                result = (await call("GET", base, seed.recorder)).json()
                assert (
                    result["body"] == "Approved summary"
                    and result["title"] == "Strategy"
                )
                assert result["project_ids"] == [] and not result["can_read_sources"]
                await call("GET", base + "/sources", seed.recorder, 404)
                await call("PUT", base + "/share", json=dict(revision=2, users=[]))
                await call("GET", base, seed.recorder, 404)
                public_id = str(uuid4())
                project_action = dict(
                    id=public_id,
                    title="Project issue",
                    audience="project",
                    expected_revision=2,
                    project_id=str(seed.project.id),
                    assignee_id=uid(seed.analyst),
                )
                await call("POST", base + "/actions", json=project_action)
                await call("POST", base + "/actions", json=project_action)
                result = (await call("GET", base + "/actions", seed.analyst)).json()
                assert [item["id"] for item in result] == [public_id]
                agenda = (
                    await call(
                        "GET",
                        "/my-work?period=past&project_id=" + str(seed.project.id),
                        seed.analyst,
                    )
                ).json()
                assert room_id in [item["id"] for item in agenda["items"]]
                await call("GET", base, seed.recorder, 404)
                async with sessions() as db:
                    project = Project(
                        id=uuid4(),
                        lab_id=seed.lab.id,
                        uid="other_" + uuid4().hex,
                        name="Other",
                        type=ProjectType.PRIVATE,
                        create_user_id=seed.owner.id,
                    )
                    db.add(project)
                    await db.flush()
                    db.add(
                        ProjectUser(
                            project_id=project.id,
                            user_id=seed.owner.id,
                            create_user_id=seed.owner.id,
                            role=ProjectRole.OWNER,
                        )
                    )
                    outsider = await db.get(User, seed.outsider.id)
                    outsider.project_guest = True
                    grant = ProjectGuest(
                        user_id=outsider.id,
                        project_id=seed.project.id,
                        role=ProjectRole.EXPLORER,
                    )
                    db.add(grant)
                    await db.commit()
                room.update(
                    expected_revision=2,
                    project_ids=[str(seed.project.id), str(project.id)],
                )
                await call("PUT", base, json=room)
                assert (await call("GET", base, seed.analyst)).json()[
                    "project_ids"
                ] == [str(seed.project.id)]
                choices = (await call("GET", base + "/speakers")).json()
                assert uid(seed.outsider) in {p["id"] for p in choices["people"]}
                guest_task = str(uuid4())
                delegated = {
                    **action,
                    "id": guest_task,
                    "expected_revision": 3,
                    "assignee_id": uid(seed.outsider),
                }
                await call(
                    "POST",
                    base + "/actions",
                    json={**delegated, "project_id": str(project.id)},
                    code=422,
                )
                await call(
                    "POST",
                    base + "/actions",
                    json={**delegated, "project_id": str(seed.project.id)},
                )
                guest_path = "/meeting-workspace/tasks/" + guest_task
                await call("GET", guest_path, seed.outsider)
                await call("GET", base + "/sources", seed.outsider, 403)
                async with sessions() as db:
                    grant = await db.get(
                        ProjectGuest, (seed.outsider.id, seed.project.id)
                    )
                    grant.access_until = utcnow() - timedelta(minutes=1)
                    await db.commit()
                await call("GET", guest_path, seed.outsider, 404)

    asyncio.run(run())
