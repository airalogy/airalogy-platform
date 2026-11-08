"""Private per-user project navigation; no research content is copied."""

import sqlalchemy as sa
from alembic import op

revision = "0081_project_visits"
down_revision = "0080_document_templates"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_visits",
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "visited_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("target", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ix_project_visits_user_time", "project_visits", ["user_id", "visited_at"]
    )


def downgrade():
    # Navigation history is disposable; this never removes research assets.
    op.drop_table("project_visits")
