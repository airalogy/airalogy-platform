"""Capture exact instants for new Record and Protocol activity without retiming history."""

import sqlalchemy as sa
from alembic import op

revision = "0090_activity_instants"
down_revision = "0089_organization_ai"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("records", "protocol_versions"):
        # A fresh 0001 bootstrap includes current ORM columns. Existing installs do not.
        op.add_column(
            table,
            sa.Column("created_at_utc", sa.DateTime(timezone=True)),
            if_not_exists=True,
        )


def downgrade():
    for table in ("records", "protocol_versions"):
        if op.get_bind().scalar(
            sa.text(
                f"SELECT EXISTS (SELECT 1 FROM {table} WHERE created_at_utc IS NOT NULL)"
            )
        ):
            raise RuntimeError(
                "Exact activity instants exist; use compatible application rollback or a verified backup"
            )
    for table in ("records", "protocol_versions"):
        op.drop_column(table, "created_at_utc")
