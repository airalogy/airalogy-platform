"""Exercise additive migration without touching any existing data schema."""

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


def test_project_work_migration_preserves_task_identity_and_refuses_loss():
    async def exercise():
        engine = create_async_engine(os.environ["RESOURCE_TEST_DATABASE_URL"])
        migration = import_module("migrations.versions.0086_project_work")
        try:
            async with engine.connect() as conn:
                transaction = await conn.begin()
                try:
                    schema = "work_migration_" + uuid4().hex
                    await conn.execute(text(f"CREATE SCHEMA {schema}"))
                    await conn.execute(
                        text(f"SET LOCAL search_path TO {schema}, public")
                    )
                    for table in ("users", "research_tasks"):
                        await conn.execute(
                            text(f"CREATE TABLE {table} (id uuid PRIMARY KEY)")
                        )

                    async def run(direction):
                        def apply(sync):
                            with Operations.context(MigrationContext.configure(sync)):
                                getattr(migration, direction)()

                        await conn.run_sync(apply)

                    await run("upgrade")
                    await run("downgrade")
                    await run("upgrade")
                    identity = uuid4()
                    await conn.execute(
                        text("INSERT INTO research_tasks VALUES (:id)"),
                        {"id": identity},
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO project_work (task_id,kind,priority,collaborator_ids,blocker,next_step,dependency_ids,evidence,create_digest) VALUES (:id,'task','normal','[]','','','[]','[]','synthetic')"
                        ),
                        {"id": identity},
                    )
                    with pytest.raises(RuntimeError, match="R&D work exists"):
                        await run("downgrade")
                    assert (
                        await conn.scalar(text("SELECT task_id FROM project_work"))
                        == identity
                    )
                    assert (
                        await conn.scalar(text("SELECT id FROM research_tasks"))
                        == identity
                    )
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
