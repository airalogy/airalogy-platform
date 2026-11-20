"""Explicit snapshot or ongoing project coverage for delegated connections."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0097_external_project_coverage"
down_revision = "0096_external_project_ledger"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("external_grants", sa.Column("project_coverage", sa.String(12)))
    op.add_column(
        "external_grants", sa.Column("selected_project_ids", ARRAY(sa.Uuid()))
    )
    op.create_check_constraint(
        "ck_external_project_coverage",
        "external_grants",
        "(project_coverage IS NULL AND selected_project_ids IS NULL) OR (project_coverage IS NOT NULL AND organization_id IS NOT NULL AND ((project_coverage = 'selected' AND selected_project_ids IS NOT NULL AND cardinality(selected_project_ids) > 0) OR (project_coverage = 'accessible' AND selected_project_ids IS NULL)))",
    )
    op.add_column(
        "external_operations",
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE")
        ),
    )


def downgrade():
    op.execute("LOCK TABLE external_grants IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM external_grants WHERE project_coverage IS NOT NULL)"
        )
    ):
        raise RuntimeError(
            "Preserve multi-project authorizations and their operation history before downgrading"
        )
    op.drop_column("external_operations", "project_id")
    op.drop_constraint("ck_external_project_coverage", "external_grants")
    op.drop_column("external_grants", "selected_project_ids")
    op.drop_column("external_grants", "project_coverage")
