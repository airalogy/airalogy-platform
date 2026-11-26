"""Keep organization-specific guest names independently of project grants."""

import sqlalchemy as sa
from alembic import op
from app.config import config

revision = "0101_guest_directory_names"
down_revision = "0100_project_guests"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization_guest_profiles",
        sa.Column(
            "lab_id",
            sa.UUID,
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("display_name", sa.String(255)),
    )
    op.execute("""
        INSERT INTO organization_guest_profiles (lab_id, user_id)
        SELECT p.lab_id, g.user_id FROM project_guests g JOIN projects p ON p.id = g.project_id
        UNION
        SELECT lab_id, user_id FROM account_tokens
        WHERE token_type = 'project_invitation' AND invitation_outcome = 'claimed'
          AND lab_id IS NOT NULL AND user_id IS NOT NULL
        UNION
        SELECT l.id, u.id FROM users u CROSS JOIN labs l
        WHERE u.project_guest AND (SELECT count(*) FROM labs) = 1
    """)
    # A former employee converted without retained projects has no invitation
    # or grant history. In a configured single organization the deployment
    # identifies their organization even if an older database has other labs.
    if config.is_single_lab:
        op.get_bind().execute(
            sa.text("""
            INSERT INTO organization_guest_profiles (lab_id, user_id)
            SELECT l.id, u.id FROM users u JOIN labs l ON l.uid = :uid
            WHERE u.project_guest AND NOT EXISTS (
                SELECT 1 FROM organization_guest_profiles p WHERE p.user_id = u.id
            )
        """),
            {"uid": config.SINGLE_LAB_UID},
        )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM organization_guest_profiles WHERE display_name IS NOT NULL)"
        )
    ):
        raise RuntimeError("Restore a backup to preserve organization guest names")
    op.drop_table("organization_guest_profiles")
