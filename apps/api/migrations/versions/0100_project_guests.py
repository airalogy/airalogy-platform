"""Separate external project access from organization membership."""

import sqlalchemy as sa
from alembic import op

revision = "0100_project_guests"
down_revision = "0099_organization_ai_services"
branch_labels = None
depends_on = None


def upgrade():
    # On fresh installations revision 0001 builds users from the current model.
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS project_guest BOOLEAN NOT NULL DEFAULT false"
    )
    op.add_column(
        "account_tokens",
        sa.Column(
            "project_id", sa.UUID, sa.ForeignKey("projects.id", ondelete="CASCADE")
        ),
    )
    op.add_column("account_tokens", sa.Column("access_until", sa.DateTime))
    op.create_table(
        "project_guests",
        sa.Column(
            "user_id",
            sa.UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "project_id",
            sa.UUID,
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.Integer, nullable=False),
        sa.Column("access_until", sa.DateTime),
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM users WHERE project_guest) "
            "OR EXISTS (SELECT 1 FROM project_guests) "
            "OR EXISTS (SELECT 1 FROM account_tokens WHERE token_type = 'project_invitation')"
        )
    ):
        raise RuntimeError(
            "Restore the pre-migration backup before removing guest isolation"
        )
    op.drop_table("project_guests")
    op.drop_column("account_tokens", "access_until")
    op.drop_column("account_tokens", "project_id")
    op.drop_column("users", "project_guest")
