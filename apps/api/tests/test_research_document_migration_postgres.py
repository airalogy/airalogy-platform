"""Upgrade, empty rollback and protected rollback in an isolated SQL schema."""

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


def test_document_migration_and_loss_protected_recovery():
    async def exercise():
        engine = create_async_engine(os.environ["RESOURCE_TEST_DATABASE_URL"])
        migration = import_module("migrations.versions.0079_research_documents")
        try:
            async with engine.connect() as conn:
                transaction = await conn.begin()
                try:
                    schema = "document_migration_" + uuid4().hex
                    await conn.execute(text(f"CREATE SCHEMA {schema}"))
                    await conn.execute(
                        text(f"SET LOCAL search_path TO {schema}, public")
                    )
                    for table in (
                        "users",
                        "research_log_entries",
                        "research_files",
                        "knowledge_items",
                    ):
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
                        text("INSERT INTO research_log_entries VALUES (:id)"),
                        {"id": identity},
                    )
                    await conn.execute(
                        text(
                            "INSERT INTO research_documents VALUES (:id,'aimd.v1','draft','{}','[]','[]','','{}')"
                        ),
                        {"id": identity},
                    )
                    with pytest.raises(RuntimeError, match="export and recover"):
                        await run("downgrade")
                    assert (
                        await conn.scalar(
                            text("SELECT count(*) FROM research_documents")
                        )
                        == 1
                    )
                finally:
                    await transaction.rollback()
        finally:
            await engine.dispose()

    asyncio.run(exercise())
