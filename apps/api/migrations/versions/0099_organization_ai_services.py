"""Store organization model services; existing credentials remain valid in place."""

import sqlalchemy as sa
from alembic import op

revision = "0099_organization_ai_services"
down_revision = "0098_workspace_publications"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization_ai_services",
        sa.Column(
            "organization_id",
            sa.UUID,
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("id", sa.UUID, primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("provider", sa.String, nullable=False),
        sa.Column("base_url", sa.String, nullable=False),
        sa.Column("models", sa.JSON, nullable=False),
        sa.Column("encrypted_key", sa.String),
    )
    op.add_column("organization_ai", sa.Column("default_service_id", sa.UUID))
    op.create_foreign_key(
        "fk_ai_default_service",
        "organization_ai",
        "organization_ai_services",
        ["organization_id", "default_service_id"],
        ["organization_id", "id"],
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM organization_ai_services)")
    ):
        raise RuntimeError(
            "Restore a backup before discarding configured AI model services"
        )
    op.drop_constraint("fk_ai_default_service", "organization_ai", type_="foreignkey")
    op.drop_column("organization_ai", "default_service_id")
    op.drop_table("organization_ai_services")
