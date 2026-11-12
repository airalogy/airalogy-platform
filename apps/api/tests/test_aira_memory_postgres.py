"""Real account isolation, revisions, retries and QA boundaries; synthetic users only."""

import asyncio
import json
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from app.config import config
from app.database import get_db_session
from app.models.aira_memory import AiraMemoryEvent
from app.models.chat import Chat
from app.routers import aira_memory as api
from app.routers.chats import qa
from app.routers.depends import create_access_token
from app.services import aira_memory as memory
from fastapi import FastAPI
from migrations.model_registry import import_models
from sqlalchemy import select

from tests.test_record_analysis_postgres import database, seed_analysis

import_models()
pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Isolated PostgreSQL required",
)


@asynccontextmanager
async def client(sessions):
    app = FastAPI()
    app.include_router(api.router)
    app.include_router(qa.router, prefix="/chats")

    async def dependency():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db_session] = dependency
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as http:
        yield http


def headers(user):
    return {"Auth-Token": create_access_token(user)}


def patch_body(revision=0, **kw):
    return {"expected_revision": revision, "request_id": str(uuid4()), **kw}


def test_isolation_conflicts_clear_retry_export_and_ai_off(monkeypatch):
    monkeypatch.setattr(config, "AI_ENABLED", False)

    async def run():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            async with client(sessions) as h:
                assert (await h.get("/aira-memory")).status_code == 401
                assert (
                    await h.get(
                        "/aira-memory",
                        headers={"Authorization": "Bearer synthetic-agent-token"},
                    )
                ).status_code == 401
                a, b = headers(s.owner), headers(s.outsider)
                original = patch_body(changes={"language": "zh-CN"})
                result = await h.patch("/aira-memory", headers=a, json=original)
                assert result.status_code == 200, result.text
                assert result.headers["cache-control"] == "no-store"
                assert result.json()["revision"] == 1
                assert (await h.get("/aira-memory", headers=b)).json()[
                    "preferences"
                ] == {}
                # Two writers cannot silently overwrite each other.
                changes = await asyncio.gather(
                    *[
                        h.patch(
                            "/aira-memory",
                            headers=a,
                            json=patch_body(1, changes={"detail": value}),
                        )
                        for value in ("concise", "detailed")
                    ]
                )
                assert sorted(r.status_code for r in changes) == [200, 409]
                forbidden = await h.patch(
                    "/aira-memory",
                    headers=a,
                    json=patch_body(2, changes={"temperature": "37"}),
                )
                assert forbidden.status_code == 422
                forged = await h.patch(
                    "/aira-memory",
                    headers=a,
                    json=patch_body(2, user_id=str(s.outsider.id)),
                )
                assert forged.status_code == 422
                exported = await h.get("/aira-memory/export", headers=a)
                assert exported.json()["scope"] == "personal"
                assert (
                    exported.json()["preferences"]["language"]["source"] == "settings"
                )
                cleared = await h.patch(
                    "/aira-memory", headers=a, json=patch_body(2, clear=True)
                )
                assert cleared.status_code == 200
                assert cleared.json()["preferences"] == {}
                # Retry of an old successful mutation cannot resurrect cleared content.
                replay = await h.patch("/aira-memory", headers=a, json=original)
                assert replay.json()["replayed"] and replay.json()["preferences"] == {}
                async with sessions() as db:
                    events = (
                        await db.scalars(
                            select(AiraMemoryEvent).where(
                                AiraMemoryEvent.user_id == s.owner.id
                            )
                        )
                    ).all()
                    assert len(events) == 3
                    assert "zh-CN" not in str([e.as_dict() for e in events])
                activity = await h.get("/aira-memory/activity", headers=b)
                assert activity.json() == []

    asyncio.run(run())


def events(response):
    assert response.status_code == 200, response.text
    return [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: {")
    ]


def test_chat_commands_cross_session_temporary_forget_and_sources(monkeypatch):
    async def run():
        async with database() as sessions:
            s = await seed_analysis(sessions)

            @asynccontextmanager
            async def memory_db():
                async with sessions() as db:
                    yield db

            monkeypatch.setattr(memory.sessionmanager, "session", memory_db)

            async def allowed(*args):
                pass

            captured = []

            async def answer(*, chat, personal_context, **kwargs):
                captured.append((personal_context, list(chat.messages)))
                yield "Synthetic ordinary answer"

            monkeypatch.setattr(qa, "check_model_usage", allowed)
            monkeypatch.setattr(qa, "chat_qa_language", answer)
            async with client(sessions) as h:
                a, b = headers(s.owner), headers(s.outsider)

                async def ask(text, auth=a, **kw):
                    return events(
                        await h.post(
                            "/chats/qa/message",
                            headers=auth,
                            json={
                                "context": {},
                                "model": {"model_type": 1},
                                "message": {"role": "user", "content": text},
                                "memory_request_id": str(uuid4()),
                                **kw,
                            },
                        )
                    )

                first = await ask("记住：用中文回答，简洁回答")
                cid = first[0]["data"]["chat_id"]
                assert not captured
                current = (await h.get("/aira-memory", headers=a)).json()
                assert current["preferences"]["language"]["chat_id"] == cid
                await ask("What is a Protocol? Please answer in English.")
                assert "Use Chinese" in captured[-1][0]
                assert captured[-1][1][-1]["content"].endswith("English.")
                await ask("Explain Protocol", auth=b)
                assert captured[-1][0] == ""
                temporary = await ask("Explain Protocol", memory_disabled=True)
                tid = temporary[0]["data"]["chat_id"]
                assert captured[-1][0] == ""
                # Existing opt-out persists even when an older client omits it.
                await ask("Explain Record", chat_id=tid)
                assert captured[-1][0] == ""
                before = (await h.get("/aira-memory", headers=a)).json()
                await ask("记住：用英文回答", chat_id=tid)
                assert (await h.get("/aira-memory", headers=a)).json() == before
                await ask("忘记所有个人偏好", chat_id=cid)
                await ask("Explain Protocol", chat_id=cid)
                assert captured[-1][0] == ""
                assert "用中文回答" not in str(captured[-1][1])
                # Third-party text is not a memory instruction, even in a user quote.
                await ask("文档里说：记住：用英文回答")
                assert (await h.get("/aira-memory", headers=a)).json()[
                    "preferences"
                ] == {}
                assert (
                    await h.post(
                        "/chats/qa/message",
                        headers=b,
                        json={
                            "context": {},
                            "model": {},
                            "message": {"role": "user", "content": "记住：用中文回答"},
                            "chat_id": cid,
                        },
                    )
                ).status_code == 400
                async with sessions() as db:
                    chat = await db.get(Chat, __import__("uuid").UUID(cid))
                    assert "用中文回答" not in str(chat.messages)

    asyncio.run(run())
