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


def test_workspace_migration_upgrade_downgrade_and_cascade_preserve_assets():
    async def exercise():
        engine = create_async_engine(os.environ["RESOURCE_TEST_DATABASE_URL"])
        migration = import_module("migrations.versions.0081_project_visits")
        try:
            async with engine.connect() as conn:
                transaction = await conn.begin()
                try:
                    schema = "workspace_migration_" + uuid4().hex
                    await conn.execute(text(f"CREATE SCHEMA {schema}"))
                    await conn.execute(
                        text(f"SET LOCAL search_path TO {schema}, public")
                    )
                    for table in ("users", "projects"):
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
                    user_id, project_id = uuid4(), uuid4()
                    await conn.execute(
                        text("INSERT INTO users VALUES (:id)"), {"id": user_id}
                    )
                    await conn.execute(
                        text("INSERT INTO projects VALUES (:id)"), {"id": project_id}
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO project_visits (user_id,project_id,target) VALUES (:u,:p,'{}')"
                        ),
                        {"u": user_id, "p": project_id},
                    )
                    await run("downgrade")
                    assert await conn.scalar(text("SELECT count(*) FROM projects")) == 1
                    await run("upgrade")
                    await conn.execute(
                        text(
                            "INSERT INTO project_visits (user_id,project_id,target) VALUES (:u,:p,'{}')"
                        ),
                        {"u": user_id, "p": project_id},
                    )
                    await conn.execute(
                        text("DELETE FROM users WHERE id=:id"), {"id": user_id}
                    )
                    assert (
                        await conn.scalar(text("SELECT count(*) FROM project_visits"))
                        == 0
                    )
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
