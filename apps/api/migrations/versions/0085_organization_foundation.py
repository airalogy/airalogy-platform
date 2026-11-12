"""Organization type without changing identities, ownership, grants or public IDs."""

import sqlalchemy as sa
from alembic import op

revision = "0085_organization_foundation"
down_revision = "0084_aira_memory"
branch_labels = None
depends_on = None


def upgrade():
    # Initial-schema installation uses current model metadata; upgrades must also
    # work against the historical Lab schema without this column/constraint.
    inspector = sa.inspect(op.get_bind())
    if "organization_type" not in {c["name"] for c in inspector.get_columns("labs")}:
        op.add_column(
            "labs",
            sa.Column(
                "organization_type",
                sa.String(),
                nullable=False,
                server_default="laboratory",
            ),
        )
    if "ck_labs_organization_type" not in {
        c["name"] for c in inspector.get_check_constraints("labs")
    }:
        op.create_check_constraint(
            "ck_labs_organization_type",
            "labs",
            "organization_type IN ('laboratory', 'company', 'institution', 'other')",
        )


def downgrade():
    # Stop instead of discarding an operator's newly configured organization type.
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM labs WHERE organization_type <> 'laboratory')"
            )
        )
        .scalar()
    ):
        raise RuntimeError(
            "Organization types exist; restore the verified backup or explicitly reconcile types before downgrading"
        )
    op.drop_constraint("ck_labs_organization_type", "labs", type_="check")
    op.drop_column("labs", "organization_type")
