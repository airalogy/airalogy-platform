"""Lightweight R&D specialization; existing research task/event identities remain."""

import sqlalchemy as sa
from alembic import op

revision = "0086_project_work"
down_revision = "0085_organization_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_work",
        sa.Column(
            "task_id",
            sa.UUID(),
            sa.ForeignKey("research_tasks.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column(
            "assignee_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("collaborator_ids", sa.JSON(), nullable=False),
        sa.Column("planned_start", sa.Date()),
        sa.Column("planned_end", sa.Date()),
        sa.Column("blocker", sa.Text(), nullable=False),
        sa.Column("next_step", sa.Text(), nullable=False),
        sa.Column("dependency_ids", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("create_digest", sa.String(64), nullable=False),
    )
    op.create_index(
        "ix_project_work_assignee_user_id", "project_work", ["assignee_user_id"]
    )


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM project_work)"))
        .scalar()
    ):
        raise RuntimeError(
            "R&D work exists; restore a verified backup instead of losing its coordination history"
        )
    op.drop_table("project_work")
