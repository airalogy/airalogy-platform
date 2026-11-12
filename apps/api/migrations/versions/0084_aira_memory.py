"""Private Aira communication preferences and content-free audit metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0084_aira_memory"
down_revision = "0083_protocol_rating"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "aira_memories",
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("preferences", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_table(
        "aira_memory_events",
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("keys", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("user_id", "request_id", name="uq_aira_memory_request"),
    )


def downgrade():
    op.drop_table("aira_memory_events")
    op.drop_table("aira_memories")
