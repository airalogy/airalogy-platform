"""Real additive migration, retained identities, and non-destructive downgrade gate."""

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


def test_meeting_migration_preserves_existing_content_and_refuses_populated_downgrade():
    async def exercise():
        engine = create_async_engine(os.environ["RESOURCE_TEST_DATABASE_URL"])
        migration = import_module("migrations.versions.0087_project_meetings")
        try:
            async with engine.connect() as conn:
                transaction = await conn.begin()
                try:
                    schema = "meeting_migration_" + uuid4().hex
                    await conn.execute(text(f"CREATE SCHEMA {schema}"))
                    await conn.execute(
                        text(f"SET LOCAL search_path TO {schema}, public")
                    )
                    for table, key in [
                        ("users", "id"),
                        ("research_documents", "id"),
                        ("project_work", "task_id"),
                    ]:
                        await conn.execute(
                            text(f"CREATE TABLE {table} ({key} uuid PRIMARY KEY)")
                        )
                    doc = uuid4()
                    await conn.execute(
                        text("INSERT INTO research_documents VALUES (:id)"), {"id": doc}
                    )

                    async def migrate(direction):
                        def apply(sync):
                            with Operations.context(MigrationContext.configure(sync)):
                                getattr(migration, direction)()

                        await conn.run_sync(apply)

                    await migrate("upgrade")
                    await migrate("downgrade")
                    await migrate("upgrade")
                    assert (
                        await conn.scalar(text("SELECT id FROM research_documents"))
                        == doc
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO meetings VALUES (:id, 'held','selected',NULL,'date','Asia/Shanghai','synthetic')"
                        ),
                        {"id": doc},
                    )
                    with pytest.raises(RuntimeError, match="Meetings exist"):
                        await migrate("downgrade")
                    assert (
                        await conn.scalar(text("SELECT document_id FROM meetings"))
                        == doc
                    )
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
