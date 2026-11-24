"""Organization reading and opt-in publication of reviewed content."""

import sqlalchemy as sa
from alembic import op

revision = "0098_workspace_publications"
down_revision = "0097_external_project_coverage"
branch_labels = None
depends_on = None


def upgrade():
    schema = sa.inspect(op.get_bind())
    if "external_publication_enabled" not in {
        c["name"] for c in schema.get_columns("labs")
    }:
        op.add_column(
            "labs",
            sa.Column(
                "external_publication_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    if "organization_readable" not in {
        c["name"] for c in schema.get_columns("projects")
    }:
        op.add_column(
            "projects",
            sa.Column(
                "organization_readable",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
    # Old community-style public flags must not expose a company workspace.
    # Only narrow existing visibility, and only in the configured single organization.
    from app.config import config

    if config.is_single_organization:
        op.get_bind().execute(
            sa.text(
                "UPDATE projects SET type=1, organization_readable=true WHERE type=2 "
                "AND lab_id IN (SELECT id FROM labs WHERE uid=:uid)"
            ),
            {"uid": config.SINGLE_LAB_UID},
        )
    op.create_table(
        "workspace_publications",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Uuid(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "version_id",
            sa.Uuid(),
            sa.ForeignKey("protocol_versions.id", ondelete="CASCADE"),
        ),
        sa.Column("audience", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("materials", sa.JSON(), nullable=False),
        sa.Column("publisher_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.CheckConstraint(
            "audience IN ('organization','public') AND (version_id IS NOT NULL OR audience='public')",
            name="ck_publication_audience",
        ),
    )
    op.create_index(
        "uq_published_project",
        "workspace_publications",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("version_id IS NULL"),
    )
    op.create_index(
        "uq_published_version_audience",
        "workspace_publications",
        ["version_id", "audience"],
        unique=True,
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM workspace_publications) OR EXISTS (SELECT 1 FROM projects WHERE organization_readable) OR EXISTS (SELECT 1 FROM labs WHERE external_publication_enabled)"
        )
    ):
        raise RuntimeError(
            "Withdraw publications and disable organization sharing before downgrade"
        )
    op.drop_table("workspace_publications")
    op.drop_column("projects", "organization_readable")
    op.drop_column("labs", "external_publication_enabled")
