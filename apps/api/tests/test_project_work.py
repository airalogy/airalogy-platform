"""Synthetic R&D acceptance: one identity, no Protocol, real authorization/database."""

import asyncio
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from sqlalchemy import func, select

from app.database import get_db_session
from app.models.project import ProjectRole, ProjectUser
from app.models.project_work import ProjectWork
from app.models.research import ResearchRun
from app.routers import project_work, research_documents, research_log, research_tasks
from app.routers.depends import create_access_token
from app.services.project_work_contracts import EvidenceLink, WorkActivity, WorkContent
from tests.test_record_analysis_postgres import database, seed_analysis


@pytest.mark.parametrize(
    "changes",
    [
        {"title": "   "},
        {"state": "blocked"},
        {"state": "done"},
        {"planned_start": "2026-04-02", "planned_end": "2026-04-01"},
        {"collaborator_ids": [str(uuid4())] * 2},
    ],
)
def test_content_validation(changes):
    with pytest.raises(ValidationError):
        WorkContent.model_validate({"title": "Synthetic requirement", **changes})


@pytest.mark.parametrize(
    "kind,outcome",
    [("test", "accepted"), ("decision", "passed"), ("comment", "adopted")],
)
def test_completion_does_not_mean_success(kind, outcome):
    with pytest.raises(ValidationError):
        WorkActivity(
            request_id=uuid4(),
            expected_revision=1,
            kind=kind,
            outcome=outcome,
            body="Synthetic",
        )


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "file:///etc/passwd",
        "https://user:secret@example.test",
        "//example.test",
    ],
)
def test_unsafe_evidence_url(url):
    with pytest.raises(ValidationError):
        EvidenceLink(kind="external", id=url)


@asynccontextmanager
async def client(sessions):
    app = FastAPI()
    app.include_router(project_work.router)
    app.include_router(research_tasks.router)
    app.include_router(research_documents.router)
    app.include_router(research_log.router)

    async def session():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db_session] = session
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as http:
        yield http


def draft(project, **changes):
    return {
        "id": str(uuid4()),
        "project_id": str(project.id),
        "title": "Synthetic glasses prototype",
        **changes,
    }


def update(item, **changes):
    fields = WorkContent.model_fields
    item = {
        **item,
        "evidence": [
            {k: v for k, v in e.items() if k in EvidenceLink.model_fields}
            for e in item["evidence"]
        ],
    }
    return {
        **{k: v for k, v in item.items() if k in fields},
        "expected_revision": item["revision"],
        "request_id": str(uuid4()),
        "change_reason": "Synthetic plan adjustment",
        **changes,
    }


integration = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"), reason="Isolated PostgreSQL required"
)


@integration
def test_manual_lifecycle_permissions_revision_and_idempotency():

    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions, public=True)
            owner = {"Auth-Token": create_access_token(seed.owner)}
            outsider = {"Auth-Token": create_access_token(seed.outsider)}
            async with client(sessions) as http:
                data = draft(
                    seed.project,
                    assignee_user_id=str(seed.owner.id),
                    goal="Prototype optical alignment",
                    acceptance="Document bench result",
                )
                assert (
                    await http.post("/project-work", json=data, headers=outsider)
                ).status_code == 403
                created = await http.post("/project-work", json=data, headers=owner)
                assert created.status_code == 200, created.text
                item = created.json()
                assert item["state"] == "pending" and item["revision"] == 1
                again = await http.post("/project-work", json=data, headers=owner)
                assert again.json()["id"] == item["id"]
                assert (
                    await http.post(
                        "/project-work",
                        json={**data, "title": "Changed"},
                        headers=owner,
                    )
                ).status_code == 409
                path = f"/project-work/{item['id']}"
                assert (await http.get(path, headers=outsider)).status_code == 403
                assert (await http.get(path)).status_code == 401
                body = update(item, state="in_progress")
                changed = await http.put(path, json=body, headers=owner)
                assert changed.status_code == 200, changed.text
                assert (await http.put(path, json=body, headers=owner)).json()[
                    "revision"
                ] == 2
                stale = await http.put(
                    path, json=update(item, title="Stale"), headers=owner
                )
                assert stale.status_code == 409
                invalid_owner = update(
                    changed.json(), assignee_user_id=str(seed.outsider.id)
                )
                assert (
                    await http.put(path, json=invalid_owner, headers=owner)
                ).status_code == 422
                # Ordinary work cannot accidentally start an automated research run.
                assert (
                    await http.get(f"/research-tasks/{item['id']}", headers=owner)
                ).status_code == 409
                tasks = await http.get(
                    "/research-tasks",
                    params={"project_id": str(seed.project.id)},
                    headers=owner,
                )
                assert not tasks.json()["tasks"]
                finished = await http.put(
                    path, json=update(changed.json(), state="done"), headers=owner
                )
                assert finished.status_code == 200, finished.text
                assert finished.json()["completed_at"]
                # Completion alone creates neither test approval nor business acceptance.
                events = (await http.get(path + "/activity", headers=owner)).json()[
                    "events"
                ]
                assert {e["kind"] for e in events} == {"created", "updated"}
                async with sessions() as db:
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(ProjectWork)
                            .where(ProjectWork.task_id == data["id"])
                        )
                        == 1
                    )
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(ResearchRun)
                            .where(ResearchRun.task_id == data["id"])
                        )
                        == 0
                    )

    asyncio.run(run())


@integration
def test_dependency_cycles_parallel_retries_and_private_sources():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            headers = {"Auth-Token": create_access_token(seed.owner)}
            async with client(sessions) as http:
                data = draft(seed.project)
                responses = await asyncio.gather(
                    *(
                        http.post("/project-work", json=data, headers=headers)
                        for _ in range(2)
                    )
                )
                assert all(r.status_code == 200 for r in responses), [
                    r.text for r in responses
                ]
                first = responses[0].json()
                second = (
                    await http.post(
                        "/project-work",
                        json=draft(seed.project, dependency_ids=[first["id"]]),
                        headers=headers,
                    )
                ).json()
                cycle = await http.put(
                    f"/project-work/{first['id']}",
                    json=update(first, dependency_ids=[second["id"]]),
                    headers=headers,
                )
                assert cycle.status_code == 422
                blocked = await http.put(
                    f"/project-work/{second['id']}",
                    json=update(
                        second, state="done", acceptance="Synthetic acceptance"
                    ),
                    headers=headers,
                )
                assert blocked.status_code == 409
                other = await seed_analysis(sessions)
                private_link = {
                    "kind": "protocol",
                    "id": str(other.protocol.id),
                    "version": "0.1.0",
                }
                denied = await http.put(
                    f"/project-work/{first['id']}",
                    json=update(first, evidence=[private_link]),
                    headers=headers,
                )
                assert denied.status_code in {403, 404}
                # No automatic publication of unrelated private evidence.
                read = (
                    await http.get(f"/project-work/{first['id']}", headers=headers)
                ).json()
                assert read["evidence"] == []

    asyncio.run(run())


@integration
def test_discussion_decisions_test_outcome_and_approval():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            async with sessions() as db:
                role = await db.scalar(
                    select(ProjectUser).where(
                        ProjectUser.project_id == seed.project.id,
                        ProjectUser.user_id == seed.analyst.id,
                    )
                )
                role.role = ProjectRole.COLLABORATOR
                await db.commit()
            owner = {"Auth-Token": create_access_token(seed.owner)}
            collaborator = {"Auth-Token": create_access_token(seed.analyst)}
            async with client(sessions) as http:
                item = (
                    await http.post(
                        "/project-work", json=draft(seed.project), headers=owner
                    )
                ).json()
                path = f"/project-work/{item['id']}/activity"
                evidence = [
                    {
                        "kind": "external",
                        "id": "https://example.test/synthetic-test-report",
                        "label": "Synthetic measurement report",
                    }
                ]
                body = {
                    "kind": "test",
                    "outcome": "failed",
                    "body": "Alignment tolerance exceeded",
                    "rationale": "Synthetic measured deviation",
                    "evidence": evidence,
                    "occurred_at": "2026-11-01T10:00:00Z",
                    "request_id": str(uuid4()),
                    "expected_revision": 1,
                }
                result = await http.post(path, json=body, headers=collaborator)
                assert result.status_code == 200, result.text
                assert (await http.post(path, json=body, headers=collaborator)).json()[
                    "replayed"
                ]
                item = (
                    await http.get(path.removesuffix("/activity"), headers=owner)
                ).json()
                assert item["state"] == "pending"
                decision = {
                    **body,
                    "kind": "decision",
                    "outcome": "adopted",
                    "request_id": str(uuid4()),
                    "expected_revision": item["revision"],
                    "body": "Adjust optical holder",
                    "scope": "Next prototype",
                }
                assert (
                    await http.post(path, json=decision, headers=collaborator)
                ).status_code == 403
                accepted = await http.post(path, json=decision, headers=owner)
                assert accepted.status_code == 200, accepted.text
                history = (await http.get(path, headers=owner)).json()
                assert history["total"] == 3
                assert history["events"][0]["payload"]["source_revision"] == 2
                assert not any(
                    "request_digest" in e["payload"] for e in history["events"]
                )
                assert (
                    await http.delete(path + "/" + accepted.json()["id"], headers=owner)
                ).status_code == 404

    asyncio.run(run())


@integration
def test_evidence_versions_home_inbox_and_log_do_not_leak():
    async def run():
        from datetime import UTC, datetime

        from sqlalchemy import delete

        from app.models.research_log import ResearchLogEntry

        async with database() as sessions:
            seed = await seed_analysis(sessions)
            headers = {"Auth-Token": create_access_token(seed.owner)}
            collaborator = {"Auth-Token": create_access_token(seed.analyst)}
            async with client(sessions) as http:
                doc_body = {
                    "scope_type": "project",
                    "project_id": str(seed.project.id),
                    "title": "Synthetic design",
                    "body": "Version one evidence",
                }
                doc = await http.post(
                    "/research-documents", json=doc_body, headers=headers
                )
                assert doc.status_code == 200, doc.text
                doc = doc.json()
                reference = {"kind": "document", "id": doc["id"], "version": "1"}
                item = (
                    await http.post(
                        "/project-work",
                        json=draft(
                            seed.project,
                            evidence=[reference],
                            assignee_user_id=str(seed.analyst.id),
                        ),
                        headers=headers,
                    )
                ).json()
                path = f"/project-work/{item['id']}"
                doc_update = await http.put(
                    f"/research-documents/{doc['id']}",
                    json={
                        "title": "Synthetic design updated",
                        "body": "Version two evidence",
                        "expected_revision": 1,
                    },
                    headers=headers,
                )
                assert doc_update.status_code == 200, doc_update.text
                snap = await http.get(
                    f"/project-work/document-snapshot/{doc['id']}/1",
                    params={"project_id": str(seed.project.id)},
                    headers=collaborator,
                )
                assert snap.status_code == 200, snap.text
                assert snap.json()["snapshot"]["body"] == "Version one evidence"
                changed = await http.put(
                    path,
                    json=update(item, goal="Edited without progress"),
                    headers=headers,
                )
                assert changed.status_code == 200, changed.text
                comment = await http.post(
                    path + "/activity",
                    json={
                        "request_id": str(uuid4()),
                        "expected_revision": 2,
                        "kind": "comment",
                        "body": "Discussion is not progress",
                    },
                    headers=headers,
                )
                assert comment.status_code == 200, comment.text
                params = {
                    "scope_type": "project",
                    "project_id": str(seed.project.id),
                    "source": "research",
                }
                log = await http.get(
                    "/research-log/timeline", params=params, headers=headers
                )
                assert log.status_code == 200, log.text
                assert (
                    len(log.json()["items"]) == 1
                )  # creation only, not text saves/comments
                assert log.json()["items"][0]["asset"]["type"] == "project_work"
                inbox = await http.get(
                    "/project-work", params={"active_only": True}, headers=collaborator
                )
                assert [row["id"] for row in inbox.json()["items"]] == [item["id"]]
                async with sessions() as db:
                    entry = await db.get(ResearchLogEntry, doc["id"])
                    entry.archived_at = datetime.now(UTC)
                    await db.commit()
                read = (await http.get(path, headers=collaborator)).json()
                assert read["evidence"] == [{"kind": "unavailable", "available": False}]
                old = (await http.get(path + "/activity", headers=collaborator)).json()
                for event in old["events"]:
                    if "snapshot" in event["payload"]:
                        assert (
                            event["payload"]["snapshot"]["evidence"] == read["evidence"]
                        )
                async with sessions() as db:
                    await db.execute(
                        delete(ProjectUser).where(
                            ProjectUser.project_id == seed.project.id,
                            ProjectUser.user_id == seed.analyst.id,
                        )
                    )
                    await db.commit()
                assert (await http.get(path, headers=collaborator)).status_code == 403
                assert (await http.get("/project-work", headers=collaborator)).json()[
                    "total"
                ] == 0

    asyncio.run(run())


@integration
def test_done_dependencies_and_adopted_decisions_cannot_be_silently_reversed():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            headers = {"Auth-Token": create_access_token(seed.owner)}
            collaborator = {"Auth-Token": create_access_token(seed.analyst)}
            async with client(sessions) as http:
                first = (
                    await http.post(
                        "/project-work",
                        json=draft(
                            seed.project,
                            state="done",
                            acceptance="Synthetic evidence reviewed",
                        ),
                        headers=headers,
                    )
                ).json()
                second = (
                    await http.post(
                        "/project-work",
                        json=draft(
                            seed.project,
                            dependency_ids=[first["id"]],
                            state="done",
                            acceptance="Synthetic follow-up completed",
                        ),
                        headers=headers,
                    )
                ).json()
                assert (
                    await http.put(
                        f"/project-work/{first['id']}",
                        json=update(first, state="in_progress"),
                        headers=headers,
                    )
                ).status_code == 409
                assert (
                    await http.put(
                        f"/project-work/{second['id']}",
                        json=update(second, state="in_progress"),
                        headers=headers,
                    )
                ).status_code == 200
                assert (
                    await http.put(
                        f"/project-work/{first['id']}",
                        json=update(first, state="in_progress"),
                        headers=headers,
                    )
                ).status_code == 200
                decision = {
                    "request_id": str(uuid4()),
                    "expected_revision": 2,
                    "kind": "decision",
                    "body": "Synthetic design chosen",
                    "outcome": "adopted",
                    "rationale": "Reviewed synthetic comparison",
                    "evidence": [
                        {"kind": "external", "id": "https://example.test/report"}
                    ],
                }
                path = f"/project-work/{first['id']}/activity"
                accepted = await http.post(path, json=decision, headers=headers)
                assert accepted.status_code == 200, accepted.text
                replacement = {
                    **decision,
                    "request_id": str(uuid4()),
                    "expected_revision": 3,
                    "supersedes": accepted.json()["id"],
                    "outcome": "proposed",
                }
                assert (
                    await http.post(path, json=replacement, headers=collaborator)
                ).status_code == 422
                replacement["outcome"] = "adopted"
                assert (
                    await http.post(path, json=replacement, headers=collaborator)
                ).status_code == 403
                assert (
                    await http.post(path, json=replacement, headers=headers)
                ).status_code == 200

    asyncio.run(run())


@integration
def test_private_viewer_opens_project_metadata_without_protocol_or_write_access():
    from fastapi import HTTPException

    from app.routers.permission import check_user_permission
    from app.routers.projects import project_response

    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            async with sessions() as db:
                membership = await db.scalar(
                    select(ProjectUser).where(
                        ProjectUser.project_id == seed.project.id,
                        ProjectUser.user_id == seed.analyst.id,
                    )
                )
                membership.role = ProjectRole.VIEWER
                await db.commit()
                assert (
                    await project_response(seed.project, seed.lab, seed.analyst, db)
                )["user_role"] == ProjectRole.VIEWER
                with pytest.raises(HTTPException):
                    await check_user_permission(
                        db,
                        seed.project,
                        seed.analyst,
                        "read_protocol",
                        protocol=seed.protocol,
                    )
                with pytest.raises(HTTPException):
                    await project_response(seed.project, seed.lab, seed.outsider, db)
            owner = {"Auth-Token": create_access_token(seed.owner)}
            viewer = {"Auth-Token": create_access_token(seed.analyst)}
            async with client(sessions) as http:
                item = (
                    await http.post(
                        "/project-work", json=draft(seed.project), headers=owner
                    )
                ).json()
                path = f"/project-work/{item['id']}"
                hidden_protocols = await http.get(
                    "/project-work/sources",
                    params={"project_id": str(seed.project.id), "kind": "protocol"},
                    headers=viewer,
                )
                assert (
                    hidden_protocols.status_code == 200
                    and hidden_protocols.json()["items"] == []
                )
                snapshot = await http.get(
                    f"/project-work/protocol-snapshot/{seed.protocol.id}/1.0.0",
                    params={"project_id": str(seed.project.id)},
                    headers=owner,
                )
                assert (
                    snapshot.status_code == 200
                    and snapshot.json()["snapshot"]["body"] == "Synthetic measurement"
                )
                read = await http.get(path, headers=viewer)
                assert read.status_code == 200 and not read.json()["can_write"]
                assert (
                    await http.put(
                        path,
                        json=update(item, title="Unauthorized write"),
                        headers=viewer,
                    )
                ).status_code == 403

    asyncio.run(run())


@integration
def test_board_moves_preserve_content_and_enforce_revision_permissions_and_dependencies():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            owner = {"Auth-Token": create_access_token(seed.owner)}
            outsider = {"Auth-Token": create_access_token(seed.outsider)}
            async with client(sessions) as http:

                async def create(**changes):
                    response = await http.post(
                        "/project-work",
                        headers=owner,
                        json=draft(seed.project, **changes),
                    )
                    assert response.status_code == 200, response.text
                    return response.json()

                def move(item, target, **changes):
                    return {
                        "state": target,
                        "expected_revision": item["revision"],
                        "request_id": str(uuid4()),
                        "change_reason": "Move on synthetic board",
                        **changes,
                    }

                parent = await create()
                item = await create(
                    goal="Retain these notes", dependency_ids=[parent["id"]]
                )
                path = f"/project-work/{item['id']}/state"
                payload = move(item, "in_progress")
                assert (
                    await http.patch(path, headers=outsider, json=payload)
                ).status_code == 403
                first = await http.patch(path, headers=owner, json=payload)
                assert first.status_code == 200, first.text
                started = first.json()
                assert (
                    started["goal"] == item["goal"]
                    and started["dependency_ids"] == item["dependency_ids"]
                )
                assert started["revision"] == item["revision"] + 1
                assert (
                    await http.patch(path, headers=owner, json=payload)
                ).json() == started
                assert (
                    await http.patch(path, headers=owner, json=move(item, "pending"))
                ).status_code == 409
                assert (
                    await http.patch(path, headers=owner, json=move(started, "blocked"))
                ).status_code == 422
                blocked = (
                    await http.patch(
                        path,
                        headers=owner,
                        json=move(started, "blocked", blocker="Awaiting parts"),
                    )
                ).json()
                assert blocked["blocker"] == "Awaiting parts"
                assert (
                    await http.patch(path, headers=owner, json=move(blocked, "done"))
                ).status_code == 422
                complete = move(blocked, "done", acceptance="Reviewed against criteria")
                assert (
                    await http.patch(path, headers=owner, json=complete)
                ).status_code == 409
                parent_path = f"/project-work/{parent['id']}/state"
                parent = (
                    await http.patch(
                        parent_path,
                        headers=owner,
                        json=move(parent, "done", acceptance="Bench checked"),
                    )
                ).json()
                finished = (await http.patch(path, headers=owner, json=complete)).json()
                assert finished["state"] == "done" and finished["completed_at"]
                assert (
                    await http.patch(
                        parent_path, headers=owner, json=move(parent, "in_progress")
                    )
                ).status_code == 409
                events = (
                    await http.get(
                        f"/project-work/{item['id']}/activity", headers=owner
                    )
                ).json()["events"]
                assert len(events) == 4

    asyncio.run(run())
