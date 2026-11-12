"""Versioning, receipt identity, privacy and concurrent retries against PostgreSQL."""

import asyncio
import os
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import delete, func, select, update

from app.config import config
from app.database import get_db_session
from app.models.lab import LabUser
from app.models.project import Project, ProjectUser
from app.models.protocol import Protocol
from app.models.protocol_rating import (
    ProtocolRating,
    ProtocolRatingRevision,
    ProtocolUse,
)
from app.models.protocol_version import ProtocolVersion
from app.models.record import Record
from app.routers import protocol_ratings as api
from app.routers.depends import create_access_token

# Load the actual runtime metadata, so focused FK lifecycle tests do not
# accidentally depend on another test module's import order.
from migrations.model_registry import import_models
from tests.test_record_analysis_postgres import add_record, database, seed_analysis

import_models()

pytestmark = pytest.mark.skipif(
    not os.environ.get("RESOURCE_TEST_DATABASE_URL"),
    reason="Isolated PostgreSQL required",
)


@pytest.fixture(autouse=True)
def flat(monkeypatch):
    monkeypatch.setattr(config, "LAB_STRUCTURE_MODE", "flat")
    monkeypatch.setattr(config, "AI_ENABLED", False)


@asynccontextmanager
async def client(sessions):
    app = FastAPI()
    app.include_router(api.router)

    async def dependency():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db_session] = dependency
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as http:
        yield http


def headers(user):
    return {"Auth-Token": create_access_token(user)} if user else {}


def url(s, suffix="", version="1.0.0"):
    return f"/protocol-ratings/{s.protocol.id}{suffix}?version={version}"


async def submit_use(h, s, user, records, **kw):
    body = {
        "request_key": uuid4().hex,
        "record_ids": [str(r.id) for r in records],
        "outcome": "as_planned",
        "is_real": True,
        **kw,
    }
    response = await h.post(url(s, "/uses"), headers=headers(user), json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


async def rate(h, s, user, **kw):
    body = {"expected_revision": 0, "score": 4, "comment": "Synthetic feedback", **kw}
    response = await h.put(url(s, "/mine"), headers=headers(user), json=body)
    assert response.status_code == 200, response.text
    return response.json(), body


async def get_summary(h, s, user=None, **params):
    response = await h.get(
        url(s), headers=headers(user), params={"version": "1.0.0", **params}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_grouped_records_revisions_concurrent_retry_and_rating_history():
    async def scenario():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            r1 = await add_record(sessions, s, 2, author=s.analyst)
            r2 = await add_record(sessions, s, 3, author=s.analyst, number=2)
            await add_record(
                sessions, s, 4, author=s.analyst, record_id=r1.id, revision=2
            )
            async with client(sessions) as h:
                use, body = await submit_use(h, s, s.analyst, [r1, r2])
                retries = await asyncio.gather(
                    *[
                        h.post(url(s, "/uses"), headers=headers(s.analyst), json=body)
                        for _ in range(3)
                    ]
                )
                assert all(
                    r.status_code == 200 and r.json()["id"] == use["id"]
                    for r in retries
                )
                conflict = await h.post(
                    url(s, "/uses"),
                    headers=headers(s.analyst),
                    json={**body, "request_key": uuid4().hex},
                )
                assert conflict.status_code == 409
                changed_key = await h.post(
                    url(s, "/uses"),
                    headers=headers(s.analyst),
                    json={**body, "comment": "changed"},
                )
                assert changed_key.status_code == 409
                review, request = await rate(h, s, s.analyst, use_id=use["id"])
                retry = await h.put(
                    url(s, "/mine"), headers=headers(s.analyst), json=request
                )
                assert retry.json()["rating"]["revision"] == 1
                changed, _ = await rate(
                    h, s, s.analyst, expected_revision=1, score=2, use_id=use["id"]
                )
                assert len(changed["history"]) == 2
                stale = await h.put(
                    url(s, "/mine"),
                    headers=headers(s.analyst),
                    json={**request, "score": 5},
                )
                assert stale.status_code == 409
                summary = await get_summary(h, s, s.owner)
                assert summary["records_count"] == 2 and summary["use_count"] == 1
                assert (
                    summary["unclassified_records"] == 0
                    and summary["rating_count"] == 1
                )
                assert summary["rating_average"] == 2 and summary["score"] is None
                async with sessions() as db:
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(ProtocolUse)
                            .where(ProtocolUse.id == UUID(use["id"]))
                        )
                        == 1
                    )
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(ProtocolRatingRevision)
                            .where(
                                ProtocolRatingRevision.object_id
                                == UUID(review["rating"]["id"])
                            )
                        )
                        == 2
                    )

    asyncio.run(scenario())


def test_private_public_opt_in_withdrawal_and_author_opinions():
    async def scenario():
        async with database() as sessions:
            s = await seed_analysis(sessions, public=True)
            r = await add_record(sessions, s, 1, author=s.analyst)
            async with client(sessions) as h:
                use, _ = await submit_use(h, s, s.analyst, [r])
                await rate(h, s, s.analyst, use_id=use["id"])
                await rate(h, s, s.owner, score=5)
                own = await get_summary(h, s, s.owner)
                assert own["rating_count"] == 1
                assert {r["kind"] for r in own["reviews"]} == {"author", "use"}
                public = await get_summary(h, s)
                assert (
                    public["use_count"] == public["rating_count"] == 0
                    and not public["reviews"]
                )
                bad = await h.put(
                    url(s, "/mine"),
                    headers=headers(s.analyst),
                    json={
                        "expected_revision": 1,
                        "score": 4,
                        "use_id": use["id"],
                        "public": True,
                    },
                )
                assert bad.status_code == 403
                body = {
                    "expected_revision": 1,
                    "outcome": "as_planned",
                    "is_real": True,
                    "public": True,
                    "comment": "",
                    "active": True,
                }
                shared = await h.put(
                    url(s, f"/uses/{use['id']}"), headers=headers(s.analyst), json=body
                )
                assert shared.status_code == 200, shared.text
                await rate(
                    h, s, s.analyst, expected_revision=1, use_id=use["id"], public=True
                )
                public = await get_summary(h, s)
                assert public["use_count"] == 1 and public["rating_count"] == 1
                assert "record_ids" not in str(public["reviews"])
                refused = await h.put(
                    url(s, f"/uses/{use['id']}"),
                    headers=headers(s.owner),
                    json={**body, "expected_revision": 2, "active": False},
                )
                assert refused.status_code == 404
                withdrawn = await h.put(
                    url(s, f"/uses/{use['id']}"),
                    headers=headers(s.analyst),
                    json={**body, "expected_revision": 2, "active": False},
                )
                assert withdrawn.status_code == 200
                public = await get_summary(h, s)
                assert public["use_count"] == public["rating_count"] == 0

    asyncio.run(scenario())


def test_private_evidence_never_public_and_permission_revocation_removes_counts():
    async def scenario():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            r = await add_record(sessions, s, 1, author=s.analyst)
            async with client(sessions) as h:
                bad = await h.post(
                    url(s, "/uses"),
                    headers=headers(s.analyst),
                    json={
                        "request_key": uuid4().hex,
                        "record_ids": [str(r.id)],
                        "outcome": "as_planned",
                        "public": True,
                    },
                )
                assert bad.status_code == 403
                use, _ = await submit_use(h, s, s.analyst, [r])
                await rate(h, s, s.analyst, use_id=use["id"])
                denied = await h.get(url(s), headers=headers(s.outsider))
                assert denied.status_code == 404
                assert (await get_summary(h, s, s.owner))["rating_count"] == 1
                # A recorder cannot see another member's private evidence/derived metrics.
                assert (await get_summary(h, s, s.recorder))["use_count"] == 0
                async with sessions() as db:
                    await db.execute(
                        delete(ProjectUser).where(ProjectUser.user_id == s.analyst.id)
                    )
                    await db.execute(
                        delete(LabUser).where(LabUser.user_id == s.analyst.id)
                    )
                    await db.commit()
                summary = await get_summary(h, s, s.owner)
                assert summary["rating_count"] == summary["use_count"] == 0

    asyncio.run(scenario())


def test_test_and_unknown_receipts_never_score_and_versions_do_not_inherit():
    async def scenario():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            r = await add_record(sessions, s, 1, author=s.analyst)
            async with sessions() as db:
                db.add(
                    ProtocolVersion(
                        id=uuid4(),
                        protocol_id=s.protocol.id,
                        version="2.0.0",
                        json_schema={},
                        fields={},
                        assigners={},
                        assigner_graph={},
                        meta_data={},
                    )
                )
                await db.commit()
            async with client(sessions) as h:
                use, _ = await submit_use(h, s, s.analyst, [r], is_real=False)
                await rate(h, s, s.analyst, use_id=use["id"], score=5)
                result = await get_summary(h, s, s.owner)
                assert result["rating_count"] == result["use_count"] == 0
                assert result["reviews"][0]["kind"] == "reading"
                for outcome in ("unknown", "stopped"):
                    res = await h.put(
                        url(s, f"/uses/{use['id']}"),
                        headers=headers(s.analyst),
                        json={
                            "expected_revision": use["revision"],
                            "outcome": outcome,
                            "is_real": True,
                        },
                    )
                    assert res.status_code == 200, res.text
                    use = res.json()
                    result = await get_summary(h, s, s.owner)
                    assert result["use_count"] == (1 if outcome == "stopped" else 0)
                wrong = await h.put(
                    url(s, "/mine", "2.0.0"),
                    headers=headers(s.analyst),
                    json={"expected_revision": 0, "score": 5, "use_id": use["id"]},
                )
                assert wrong.status_code == 422
                newer = await h.get(url(s, version="2.0.0"), headers=headers(s.owner))
                assert newer.json()["rating_count"] == newer.json()["use_count"] == 0
                async with sessions() as db:
                    await db.execute(
                        update(Record)
                        .where(Record.id == r.id)
                        .values(deleted_at=func.now())
                    )
                    await db.commit()
                assert (await get_summary(h, s, s.owner))["use_count"] == 0
                mine = (await h.get(url(s, "/mine"), headers=headers(s.analyst))).json()
                assert mine["uses"][0]["eligible"] is False
                withdrawn = await h.put(
                    url(s, f"/uses/{use['id']}"),
                    headers=headers(s.analyst),
                    json={
                        "expected_revision": use["revision"],
                        "outcome": "stopped",
                        "is_real": True,
                        "active": False,
                    },
                )
                assert withdrawn.status_code == 200
                await rate(
                    h,
                    s,
                    s.analyst,
                    expected_revision=1,
                    use_id=use["id"],
                    score=5,
                    active=False,
                )

    asyncio.run(scenario())


def test_foreign_records_invalid_inputs_and_concurrent_first_ratings():
    async def scenario():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            r = await add_record(sessions, s, 1)
            async with client(sessions) as h:
                res = await h.post(
                    url(s, "/uses"),
                    headers=headers(s.analyst),
                    json={
                        "request_key": uuid4().hex,
                        "record_ids": [str(r.id)],
                        "outcome": "as_planned",
                    },
                )
                assert res.status_code == 422
                for score in (0, 6, 1.5, True, "5"):
                    invalid = await h.put(
                        url(s, "/mine"),
                        headers=headers(s.analyst),
                        json={"expected_revision": 0, "score": score},
                    )
                    assert invalid.status_code == 422
                responses = await asyncio.gather(
                    *[
                        h.put(
                            url(s, "/mine"),
                            headers=headers(s.analyst),
                            json={"expected_revision": 0, "score": 4},
                        )
                        for _ in range(4)
                    ]
                )
                assert all(r.status_code == 200 for r in responses)
                assert len({r.json()["rating"]["id"] for r in responses}) == 1
                async with sessions() as db:
                    assert (
                        await db.scalar(
                            select(func.count())
                            .select_from(ProtocolRating)
                            .where(ProtocolRating.protocol_version_id == s.version.id)
                        )
                        == 1
                    )

    asyncio.run(scenario())


def test_cross_lab_adoption_is_deduplicated_and_never_counts_as_original_execution():
    async def scenario():
        async with database() as sessions:
            source = await seed_analysis(sessions, public=True)
            fork = await seed_analysis(sessions, public=True)
            empty = await seed_analysis(sessions, public=True)
            async with sessions() as db:
                for child in (fork, empty):
                    await db.execute(
                        update(Protocol)
                        .where(Protocol.id == child.protocol.id)
                        .values(
                            parent_protocol_id=source.protocol.id,
                            parent_protocol_version="1.0.0",
                        )
                    )
                await db.commit()
            r = await add_record(sessions, fork, 2, author=fork.analyst)
            async with client(sessions) as h:
                use, _ = await submit_use(h, fork, fork.analyst, [r], public=True)
                # Source author's review is not fabricated from the child execution.
                before = await get_summary(h, source)
                assert before["use_count"] == 0
                assert (
                    before["effective_reuse_count"] == 1 and before["copies_count"] == 2
                )
                await rate(h, source, fork.analyst, use_id=use["id"], public=True)
                after = await get_summary(h, source)
                assert after["rating_count"] == 1
                assert after["use_count"] == 0 and after["lab_count"] == 1
                assert (await get_summary(h, fork))["use_count"] == 1
                r2 = await add_record(sessions, fork, 3, author=fork.analyst, number=2)
                await submit_use(h, fork, fork.analyst, [r2], public=True)
                assert (await get_summary(h, source))["effective_reuse_count"] == 1
                async with sessions() as db:
                    await db.execute(
                        update(Project)
                        .where(Project.id == fork.project.id)
                        .values(type=1)
                    )
                    await db.commit()
                hidden = await get_summary(h, source)
                assert hidden["effective_reuse_count"] == hidden["rating_count"] == 0
                assert hidden["copies_count"] == 1

    asyncio.run(scenario())


def test_existing_research_run_is_reused_and_cancelled_runs_stop_counting():
    from app.models.research import (
        ResearchAction,
        ResearchProtocolRun,
        ResearchRun,
        ResearchTask,
    )

    async def scenario():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            r = await add_record(sessions, s, 1, author=s.analyst)
            async with sessions() as db:
                task = ResearchTask(
                    lab_id=s.lab.id,
                    project_id=s.project.id,
                    title="Synthetic execution",
                    goal="Synthetic only",
                    owner_user_id=s.analyst.id,
                    created_by_user_id=s.analyst.id,
                )
                db.add(task)
                await db.flush()
                run = ResearchRun(
                    task_id=task.id, run_number=1, requested_by_user_id=s.analyst.id
                )
                db.add(run)
                await db.flush()
                action = ResearchAction(
                    run_id=run.id,
                    sequence=1,
                    plan_version=1,
                    kind="protocol_run",
                    status="completed",
                    title="Synthetic action",
                    executor_type="human",
                    preview_digest="0" * 64,
                    idempotency_key=uuid4().hex,
                )
                db.add(action)
                await db.flush()
                protocol_run = ResearchProtocolRun(
                    action_id=action.id,
                    protocol_id=s.protocol.id,
                    protocol_version_id=s.version.id,
                    protocol_version="1.0.0",
                    record_id=r.id,
                    record_version=r.version,
                )
                db.add(protocol_run)
                await db.commit()
            async with client(sessions) as h:
                # Existing executions lacking real/test confirmation remain unknown.
                assert (await get_summary(h, s, s.owner))["use_count"] == 0
                use, _ = await submit_use(h, s, s.analyst, [r])
                assert use["research_run_id"] == str(protocol_run.id)
                assert (await get_summary(h, s, s.owner))["use_count"] == 1
                async with sessions() as db:
                    await db.execute(
                        update(ResearchAction)
                        .where(ResearchAction.id == action.id)
                        .values(status="cancelled")
                    )
                    await db.commit()
                assert (await get_summary(h, s, s.owner))["use_count"] == 0

    asyncio.run(scenario())


def test_three_actual_non_author_reviewers_produce_reproducible_score():
    from app.models.project import ProjectRole

    async def scenario():
        async with database() as sessions:
            s = await seed_analysis(sessions, public=True)
            async with sessions() as db:
                db.add(
                    ProjectUser(
                        project_id=s.project.id,
                        user_id=s.outsider.id,
                        role=ProjectRole.RECORDER,
                        create_user_id=s.owner.id,
                    )
                )
                db.add(
                    LabUser(
                        lab_id=s.lab.id,
                        user_id=s.outsider.id,
                        role=20,
                        create_user_id=s.owner.id,
                    )
                )
                await db.commit()
            async with client(sessions) as h:
                for index, user in enumerate((s.analyst, s.recorder, s.outsider)):
                    r = await add_record(
                        sessions, s, index, author=user, number=index + 1
                    )
                    use, _ = await submit_use(h, s, user, [r], public=True)
                    await rate(
                        h, s, user, use_id=use["id"], score=index + 3, public=True
                    )
                result = await get_summary(h, s)
                assert result["rating_count"] == 3 and result["rating_average"] == 4
                assert result["score"] is not None and 0 <= result["score"] <= 100
                assert result["use_count"] == 3 and result["lab_count"] == 1
                assert (
                    round(
                        result["components"]["rating_points"]
                        + result["components"]["adoption_points"],
                        1,
                    )
                    == result["score"]
                )
                repeat = await get_summary(h, s)
                assert (
                    repeat["basis"] == result["basis"]
                    and repeat["score"] == result["score"]
                )

    asyncio.run(scenario())


def test_migration_round_trip_in_a_rolled_back_transaction():
    from importlib import import_module

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    async def scenario():
        async with database() as sessions, sessions() as db:
            conn = await db.connection()

            def check(sync):
                migration = import_module("migrations.versions.0083_protocol_rating")
                with Operations.context(MigrationContext.configure(sync)):
                    migration.downgrade()
                    assert "protocol_ratings" not in inspect(sync).get_table_names()
                    migration.upgrade()
                    assert (
                        "protocol_rating_revisions" in inspect(sync).get_table_names()
                    )
                    constraints = inspect(sync).get_unique_constraints(
                        "protocol_ratings"
                    )
                    assert any(
                        c["column_names"] == ["protocol_version_id", "user_id"]
                        for c in constraints
                    )

            await conn.run_sync(check)
            # Restore all pre-test tables and contents, including receipts.
            await db.rollback()

    asyncio.run(scenario())


def test_explicit_lab_cleanup_is_scoped_and_preserves_foreign_lineage():
    from app.services.protocol_rating import delete_lab_rating_data

    async def scenario():
        async with database() as sessions:
            original = await seed_analysis(sessions, public=True)
            adopted = await seed_analysis(sessions, public=True)
            async with sessions() as db:
                await db.execute(
                    update(Protocol)
                    .where(Protocol.id == adopted.protocol.id)
                    .values(
                        parent_protocol_id=original.protocol.id,
                        parent_protocol_version="1.0.0",
                    )
                )
                await db.commit()
            r = await add_record(sessions, adopted, 1, author=adopted.analyst)
            async with client(sessions) as h:
                use, _ = await submit_use(h, adopted, adopted.analyst, [r], public=True)
                review, _ = await rate(
                    h, original, adopted.analyst, use_id=use["id"], public=True
                )
                async with sessions() as db:
                    with pytest.raises(ValueError, match="another scope"):
                        await delete_lab_rating_data(db, adopted.lab.id)
                    await db.rollback()
                    assert (
                        await db.get(ProtocolRating, UUID(review["rating"]["id"]))
                        is not None
                    )
                async with sessions() as db:
                    await delete_lab_rating_data(db, original.lab.id)
                    await db.commit()
                    assert await db.get(ProtocolUse, UUID(use["id"])) is not None
                async with sessions() as db:
                    await delete_lab_rating_data(db, adopted.lab.id)
                    await db.commit()
                    assert await db.get(ProtocolUse, UUID(use["id"])) is None

    asyncio.run(scenario())


def test_project_use_sort_happens_before_pagination_and_linked_authors_are_separate():
    from app.routers.protocols import get_protocols

    async def scenario():
        async with database() as sessions:
            s = await seed_analysis(sessions)
            record = await add_record(sessions, s, 1, author=s.analyst)
            async with sessions() as db:
                empty = Protocol(
                    id=uuid4(),
                    project_id=s.project.id,
                    user_id=s.owner.id,
                    uid=f"unused_{uuid4().hex}",
                    name="Synthetic unused protocol",
                    latest_version="1.0.0",
                )
                db.add(empty)
                await db.flush()
                db.add(
                    ProtocolVersion(
                        protocol_id=empty.id,
                        version="1.0.0",
                        json_schema={},
                        fields={},
                        assigners={},
                        assigner_graph={},
                        meta_data={},
                    )
                )
                await db.execute(
                    update(ProtocolVersion)
                    .where(ProtocolVersion.id == s.version.id)
                    .values(
                        meta_data={
                            "authors": [{"airalogy_user_id": s.analyst.username}]
                        }
                    )
                )
                await db.commit()
            async with client(sessions) as h:
                use, _ = await submit_use(h, s, s.analyst, [record])
                await rate(h, s, s.analyst, use_id=use["id"], score=5)
                result = await get_summary(h, s, s.owner)
                assert result["rating_count"] == 0
                assert result["reviews"][0]["kind"] == "author"
            async with sessions() as db:
                first = await get_protocols(
                    db,
                    s.owner,
                    project_id=s.project.id,
                    sorted_by="confirmed_uses",
                    page=1,
                    page_size=1,
                )
                second = await get_protocols(
                    db,
                    s.owner,
                    project_id=s.project.id,
                    sorted_by="confirmed_uses",
                    page=2,
                    page_size=1,
                )
                assert first["total_count"] == 2
                assert str(first["protocols"][0]["id"]) == str(s.protocol.id)
                assert str(second["protocols"][0]["id"]) == str(empty.id)

    asyncio.run(scenario())
