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


def test_template_migration_empty_downgrade_and_loss_protection():
    async def exercise():
        engine = create_async_engine(os.environ["RESOURCE_TEST_DATABASE_URL"])
        migration = import_module("migrations.versions.0080_document_templates")
        try:
            async with engine.connect() as conn:
                transaction = await conn.begin()
                try:
                    schema = "template_migration_" + uuid4().hex
                    await conn.execute(text(f"CREATE SCHEMA {schema}"))
                    await conn.execute(
                        text(f"SET LOCAL search_path TO {schema}, public")
                    )
                    for table in ("users", "labs", "projects"):
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
                    user_id, template_id = uuid4(), uuid4()
                    await conn.execute(
                        text("INSERT INTO users VALUES (:id)"), {"id": user_id}
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO document_templates (id,scope_type,owner_user_id,title,description,kind,body,revision,source,create_digest,created_by_user_id) VALUES (:id,'personal',:user,'Synthetic','','document','',1,'{}',:digest,:user)"
                        ),
                        {"id": template_id, "user": user_id, "digest": "0" * 64},
                    )
                    with pytest.raises(RuntimeError, match="export and recover"):
                        await run("downgrade")
                    assert (
                        await conn.scalar(
                            text("SELECT count(*) FROM document_templates")
                        )
                        == 1
                    )
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
