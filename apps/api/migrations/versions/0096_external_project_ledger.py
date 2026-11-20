"""Target delegated grants to exactly one project or organization."""

import sqlalchemy as sa
from alembic import op

revision = "0096_external_project_ledger"
down_revision = "0095_invitation_display_name"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "external_grants",
        sa.Column(
            "organization_id", sa.Uuid(), sa.ForeignKey("labs.id", ondelete="CASCADE")
        ),
    )
    op.alter_column("external_grants", "project_id", nullable=True)
    op.create_check_constraint(
        "ck_external_grant_target",
        "external_grants",
        "num_nonnulls(project_id, organization_id) = 1",
    )
    op.create_table(
        "external_project_receipts",
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("request_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("contract_number", sa.String(128)),
        sa.UniqueConstraint(
            "organization_id", "contract_number", name="uq_external_project_contract"
        ),
    )


def downgrade():
    op.execute(
        "LOCK TABLE external_grants, external_project_receipts IN ACCESS EXCLUSIVE MODE"
    )
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM external_project_receipts) OR EXISTS (SELECT 1 FROM external_grants WHERE organization_id IS NOT NULL OR scopes::jsonb ?| ARRAY['cash:read','cash:create'])"
        )
    ):
        raise RuntimeError(
            "Preserve delegated project and cash authorizations and receipts before downgrading"
        )
    op.drop_table("external_project_receipts")
    op.drop_constraint("ck_external_grant_target", "external_grants")
    op.alter_column("external_grants", "project_id", nullable=False)
    op.drop_column("external_grants", "organization_id")
