"""Account-owned meeting drafting conversations on this deployment."""

import sqlalchemy as sa
from alembic import op

revision = "0094_meeting_conversations"
down_revision = "0093_aira_memory_interaction"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meeting_conversations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=False
        ),
        sa.Column("meeting_id", sa.Uuid(), sa.ForeignKey("meetings.document_id")),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("turns", sa.JSON(), nullable=False),
        sa.Column("proposal", sa.JSON()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_meeting_conversations_user_id", "meeting_conversations", ["user_id"]
    )
    op.create_index(
        "ix_meeting_conversations_project_id", "meeting_conversations", ["project_id"]
    )


def downgrade():
    op.execute("LOCK TABLE meeting_conversations IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM meeting_conversations)")
    ):
        raise RuntimeError("Preserve saved meeting conversations before downgrading")
    op.drop_table("meeting_conversations")
