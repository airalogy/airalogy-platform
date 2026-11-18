"""Organization-controlled AI. Existing instances inherit their previous setup."""

import sqlalchemy as sa
from alembic import op

revision = "0089_organization_ai"
down_revision = "0088_project_people"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "organization_ai",
        sa.Column(
            "organization_id",
            sa.UUID(),
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("encrypted_key", sa.String(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
    )


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM organization_ai)"))
        .scalar()
    ):
        raise RuntimeError("Cannot discard saved organization AI settings")
    op.drop_table("organization_ai")
