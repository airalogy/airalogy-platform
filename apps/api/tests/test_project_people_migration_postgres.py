"""Rehearse the actual meeting-to-people migration without rewriting source data."""

import asyncio
import os
from importlib import import_module
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.skipif(
    not os.getenv("RESOURCE_TEST_DATABASE_URL"), reason="Isolated PostgreSQL required"
)


def test_people_migration_preserves_meetings_work_and_blocks_lossy_recovery():
    async def run():
        engine = create_async_engine(os.environ["RESOURCE_TEST_DATABASE_URL"])
        try:
            async with engine.connect() as connection:
                transaction = await connection.begin()
                try:
                    schema = "people_migration_" + uuid4().hex
                    await connection.execute(text(f"CREATE SCHEMA {schema}"))
                    await connection.execute(
                        text(f"SET LOCAL search_path TO {schema}, public")
                    )
                    for table in ["users", "projects", "research_documents"]:
                        await connection.execute(
                            text(f"CREATE TABLE {table} (id uuid PRIMARY KEY)")
                        )
                    await connection.execute(
                        text(
                            "CREATE TABLE project_work (task_id uuid PRIMARY KEY, original_note text NOT NULL)"
                        )
                    )

                    async def migrate(module, direction):
                        def apply(sync):
                            with Operations.context(MigrationContext.configure(sync)):
                                getattr(
                                    import_module("migrations.versions." + module),
                                    direction,
                                )()

                        await connection.run_sync(apply)

                    await migrate("0087_project_meetings", "upgrade")
                    person, project, meeting, task = [uuid4() for _ in range(4)]
                    for table, value in [
                        ("users", person),
                        ("projects", project),
                        ("research_documents", meeting),
                    ]:
                        await connection.execute(
                            text(f"INSERT INTO {table} VALUES (:id)"), {"id": value}
                        )
                    await connection.execute(
                        text(
                            "INSERT INTO project_work VALUES (:id, 'Synthetic existing source')"
                        ),
                        {"id": task},
                    )
                    await connection.execute(
                        text(
                            "INSERT INTO meetings VALUES (:id, 'held', 'selected', NULL, 'date', 'Asia/Shanghai', 'synthetic')"
                        ),
                        {"id": meeting},
                    )
                    await connection.execute(
                        text(
                            "INSERT INTO meeting_participants (id, meeting_id, name, organization, attendance) VALUES (:id, :meeting, 'Synthetic attendee', '', 'attended')"
                        ),
                        {"id": uuid4(), "meeting": meeting},
                    )
                    await migrate("0088_project_people", "upgrade")
                    assert (
                        await connection.scalar(
                            text("SELECT original_note FROM project_work")
                        )
                        == "Synthetic existing source"
                    )
                    assert (
                        await connection.scalar(
                            text("SELECT name FROM meeting_participants")
                        )
                        == "Synthetic attendee"
                    )
                    assert (
                        await connection.scalar(
                            text("SELECT count(*) FROM project_people")
                        )
                        == 0
                    )
                    assert (
                        await connection.scalar(
                            text("SELECT deadline_note FROM project_work")
                        )
                        == ""
                    )
                    # Empty new features can be rolled back, then upgraded again.
                    await migrate("0088_project_people", "downgrade")
                    await migrate("0088_project_people", "upgrade")
                    await connection.execute(
                        text(
                            "UPDATE project_work SET deadline_note = 'Before the next meeting'"
                        )
                    )
                    with pytest.raises(RuntimeError, match="compatible recovery"):
                        await migrate("0088_project_people", "downgrade")
                    assert (
                        await connection.scalar(
                            text("SELECT document_id FROM meetings")
                        )
                        == meeting
                    )
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    asyncio.run(run())
