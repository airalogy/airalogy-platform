"""Versioned Protocol ratings and explicitly confirmed execution receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0083_protocol_rating"
down_revision = "0082_external_research"
branch_labels = None
depends_on = None


def identity():
    return sa.Column(
        "id", sa.UUID(), primary_key=True, server_default=sa.text("uuid_generate_v7()")
    )


def common():
    return [
        sa.Column(
            "protocol_version_id",
            sa.UUID(),
            sa.ForeignKey("protocol_versions.id"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("public", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade():
    op.create_table(
        "protocol_uses",
        identity(),
        *common(),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column(
            "research_run_id", sa.UUID(), sa.ForeignKey("research_protocol_runs.id")
        ),
        sa.Column("is_real", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.UniqueConstraint("user_id", "request_key", name="uq_protocol_use_request"),
        sa.UniqueConstraint("research_run_id", name="uq_protocol_use_run"),
        sa.CheckConstraint(
            "outcome IN ('as_planned','adjusted','stopped','unknown')",
            name="ck_protocol_use_outcome",
        ),
    )
    op.create_table(
        "protocol_use_records",
        sa.Column("record_id", sa.UUID(), primary_key=True),
        sa.Column("record_version", sa.Integer(), nullable=False),
        sa.Column(
            "use_id", sa.UUID(), sa.ForeignKey("protocol_uses.id"), nullable=False
        ),
    )
    op.create_index(
        "ix_protocol_use_records_use_id", "protocol_use_records", ["use_id"]
    )
    op.create_table(
        "protocol_ratings",
        identity(),
        *common(),
        sa.Column("use_id", sa.UUID(), sa.ForeignKey("protocol_uses.id")),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("conditions", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "protocol_version_id", "user_id", name="uq_protocol_rating_user_version"
        ),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_protocol_rating_score"),
    )
    for table in ("protocol_uses", "protocol_ratings"):
        for column in ("protocol_version_id", "user_id"):
            op.create_index(f"ix_{table}_{column}", table, [column])
    op.create_table(
        "protocol_rating_revisions",
        identity(),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("object_id", sa.UUID(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("kind", "object_id", "revision", name="uq_rating_revision"),
    )
    op.create_index(
        "ix_protocol_rating_revisions_object_id",
        "protocol_rating_revisions",
        ["object_id"],
    )


def downgrade():
    for table in (
        "protocol_rating_revisions",
        "protocol_ratings",
        "protocol_use_records",
        "protocol_uses",
    ):
        op.drop_table(table)
