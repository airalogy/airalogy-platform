"""Regression for mixed log instants, legacy clocks and the Record diary calendar."""

import asyncio
import os
import time
from datetime import UTC, date, datetime
from importlib import import_module
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.config import config
from app.models.activity_time import activity_instant
from app.models.record import Record
from app.models.research_log import ResearchLogScope
from app.routers import research_log, users
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.test_record_analysis_postgres import database, seed_analysis

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"), reason="Isolated PostgreSQL required"
)


def make_record(seed, number, **values):
    return Record(
        id=uuid4(),
        protocol_id=seed.protocol.id,
        protocol_version="1.0.0",
        user_id=seed.owner.id,
        number=number,
        data={},
        hash="synthetic",
        **values,
    )


@pytest.mark.parametrize("writer_zone", ["Asia/Shanghai", "UTC"])
def test_mixed_pagination_and_new_writes(writer_zone, monkeypatch):
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            async with sessions() as db:
                await db.execute(text("SET LOCAL TIME ZONE 'UTC'"))
                assert seed.version.created_at_utc is not None
                before = datetime.now(UTC)
                records = [make_record(seed, n) for n in range(1, 13)]
                db.add_all(records)
                await db.flush()
                after = datetime.now(UTC)
                assert all(before <= r.created_at_utc <= after for r in records)
                assert all(
                    r.created_at == r.created_at_utc.astimezone().replace(tzinfo=None)
                    for r in records
                )
                scope = {
                    "scope_type": ResearchLogScope.PROJECT,
                    "project_id": seed.project.id,
                }
                draft = research_log.ResearchLogEntryDraft(
                    **scope,
                    lab_id=seed.lab.id,
                    kind="progress",
                    title="Synthetic latest log",
                )
                entry = await research_log.create_research_log_entry(
                    draft, seed.owner, db
                )

                async def page(n):
                    return await research_log.get_research_log_timeline(
                        seed.owner, db, **scope, page=n, page_size=10
                    )

                first, second = await page(1), await page(2)
                assert first["items"][0]["id"] == entry["id"]
                items = first["items"] + second["items"]
                assert len(items) == first["total_count"] == 14
                assert len({item["id"] for item in items}) == len(items)
                assert [item["occurred_at"] for item in items] == sorted(
                    [item["occurred_at"] for item in items], reverse=True
                )
                assert (await page(1))["items"][0]["id"] == entry["id"]

    with monkeypatch.context() as patch:
        patch.setenv("TZ", writer_zone)
        time.tzset()
        try:
            asyncio.run(run())
        finally:
            patch.undo()
            time.tzset()


def test_legacy_midnight_matches_heatmap_calendar_and_detail(monkeypatch):
    monkeypatch.setattr(config, "LEGACY_ACTIVITY_TIME_ZONE", "Asia/Shanghai")

    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            async with sessions() as db:
                await db.execute(text("SET LOCAL TIME ZONE 'America/Los_Angeles'"))
                earlier = make_record(
                    seed, 1, created_at=datetime.fromisoformat("2024-05-01T23:59")
                )
                later = make_record(
                    seed, 2, created_at=datetime.fromisoformat("2024-05-02T00:01")
                )
                db.add_all([earlier, later])
                await db.flush()
                assert later.created_at_utc is None
                expected = datetime(2024, 5, 1, 16, 1, tzinfo=UTC)
                assert (
                    await db.scalar(
                        select(activity_instant(Record)).where(Record.id == later.id)
                    )
                    == expected
                )
                for zone, day, count in [
                    ("Asia/Shanghai", date(2024, 5, 2), 1),
                    ("UTC", date(2024, 5, 1), 2),
                ]:
                    window = {"time_zone": zone, "date_from": day, "date_to": day}
                    scope = dict(
                        scope_type=ResearchLogScope.PROJECT,
                        project_id=seed.project.id,
                        source="record",
                        **window,
                    )
                    heat = await research_log.research_activity_summary(
                        seed.owner, db, **scope
                    )
                    detail = await research_log.get_research_log_timeline(
                        seed.owner, db, **scope, page=1, page_size=10
                    )
                    opts = {
                        "target_user_id": seed.owner.id,
                        "current_user": seed.owner,
                        "db_session": db,
                        "params": users.UserRecordQueryParams(**window),
                    }
                    calendar = await users.get_visible_user_record_summary(**opts)
                    events = await users.get_visible_user_record_events(
                        **opts, limit=10
                    )
                    history = await users.get_visible_user_record_history(
                        **opts, page=1, page_size=10
                    )
                    assert (
                        heat["summary"]
                        == calendar["summary"]
                        == [{"date": day.isoformat(), "count": count}]
                    )
                    assert (
                        len(events["events"])
                        == history["total_count"]
                        == detail["total_count"]
                        == count
                    )
                    assert (
                        events["events"][-1]["metadata"][
                            "record_current_version_submission_time"
                        ]
                        == expected
                    )
                    assert (
                        history["records"][0]["metadata"][
                            "record_current_version_submission_time"
                        ]
                        == expected
                    )

                monkeypatch.setattr(config, "LEGACY_ACTIVITY_TIME_ZONE", None)
                # Unconfigured older rows keep the previous session interpretation.
                previous = await db.scalar(
                    text("SELECT created_at::timestamptz FROM records WHERE id=:id"),
                    {"id": later.id},
                )
                assert (
                    await db.scalar(
                        select(activity_instant(Record)).where(Record.id == later.id)
                    )
                    == previous
                )

    asyncio.run(run())


def test_repeated_hour_and_tied_revisions_have_stable_pages():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            async with sessions() as db:
                zone = ZoneInfo("America/New_York")
                first_hour = datetime(2024, 11, 3, 1, 30, tzinfo=zone)
                second_hour = first_hour.replace(fold=1)
                records = [
                    make_record(seed, 1, version=1, created_at=first_hour),
                    make_record(seed, 1, version=2, created_at=second_hour),
                    make_record(seed, 1, version=10, created_at=second_hour),
                ]
                for record in records[1:]:
                    record.id = records[0].id
                db.add_all(records)
                await db.flush()
                assert records[0].created_at == records[1].created_at
                assert records[0].created_at_utc < records[1].created_at_utc
                versions = []
                for page in (1, 2, 3):
                    result = await research_log.get_research_log_timeline(
                        seed.owner,
                        db,
                        scope_type=ResearchLogScope.PERSONAL,
                        source="record",
                        date_from=first_hour.date(),
                        date_to=first_hour.date(),
                        time_zone=zone.key,
                        page=page,
                        page_size=1,
                    )
                    assert result["total_count"] == 3
                    versions.append(result["items"][0]["asset"]["version"])
                assert versions == ["10", "2", "1"]

    asyncio.run(run())


def test_core_and_bulk_writers_capture_the_same_instant_as_the_legacy_clock():
    async def run():
        async with database() as sessions:
            seed = await seed_analysis(sessions)
            async with sessions() as db:
                fields = {
                    "protocol_id": seed.protocol.id,
                    "protocol_version": "1.0.0",
                    "user_id": seed.owner.id,
                    "data": {},
                    "hash": "synthetic",
                }
                first = await Record.create(db, **fields, id=uuid4(), number=1)
                rows = (
                    (
                        await db.execute(
                            insert(Record).returning(Record),
                            [{**fields, "id": uuid4(), "number": i} for i in (2, 3)],
                        )
                    )
                    .scalars()
                    .all()
                )
                multi = (
                    await db.scalars(
                        insert(Record)
                        .values(
                            [{**fields, "id": uuid4(), "number": i} for i in (4, 5)]
                        )
                        .returning(Record)
                    )
                ).all()
                for row in [first, *rows, *multi]:
                    assert row.created_at == row.created_at_utc.astimezone().replace(
                        tzinfo=None
                    )
                legacy = datetime.fromisoformat("2020-01-01T08:00:00")
                imported = (
                    await db.scalars(
                        insert(Record)
                        .values(
                            [
                                {
                                    **fields,
                                    "id": uuid4(),
                                    "number": i,
                                    "created_at": legacy,
                                }
                                for i in (6, 7)
                            ]
                        )
                        .returning(Record)
                    )
                ).all()
                assert all(
                    r.created_at == legacy and r.created_at_utc is None
                    for r in imported
                )

    asyncio.run(run())


def test_existing_schema_upgrade_and_compatible_rollback():
    module = import_module("migrations.versions.0090_activity_instants")
    assert module.down_revision == "0089_organization_ai"

    async def run():
        engine = create_async_engine(os.environ["RESOURCE_TEST_DATABASE_URL"])
        try:
            async with engine.connect() as conn, conn.begin():
                schema = "activity_clock_" + uuid4().hex
                await conn.execute(text(f"CREATE SCHEMA {schema}"))
                await conn.execute(text(f"SET LOCAL search_path TO {schema}"))
                for table in ("records", "protocol_versions"):
                    await conn.execute(
                        text(f"CREATE TABLE {table} (created_at timestamp NOT NULL)")
                    )
                    await conn.execute(
                        text(f"INSERT INTO {table} VALUES ('2024-05-01 13:00')")
                    )

                def migrate(sync, action):
                    with Operations.context(MigrationContext.configure(sync)):
                        action()

                await conn.run_sync(migrate, module.upgrade)
                for table in ("records", "protocol_versions"):
                    row = (
                        await conn.execute(
                            text(f"SELECT created_at, created_at_utc FROM {table}")
                        )
                    ).one()
                    assert tuple(row) == (
                        datetime.fromisoformat("2024-05-01T13:00"),
                        None,
                    )
                await conn.run_sync(migrate, module.downgrade)
                await conn.run_sync(migrate, module.upgrade)
                await conn.execute(
                    text("INSERT INTO records VALUES (localtimestamp, now())")
                )
                with pytest.raises(
                    RuntimeError, match="compatible application rollback"
                ):
                    await conn.run_sync(migrate, module.downgrade)
                await conn.rollback()
        finally:
            await engine.dispose()

    asyncio.run(run())
