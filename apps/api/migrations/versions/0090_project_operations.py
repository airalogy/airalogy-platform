"""Opt-in commercial project accounting. No existing project or grant is enrolled."""

import sqlalchemy as sa
from alembic import op

revision = "0090_project_operations"
down_revision = "0089_organization_ai"
branch_labels = None
depends_on = None


def ref(name, target, **kwargs):
    return sa.Column(name, sa.UUID(), sa.ForeignKey(target), **kwargs)


def upgrade():
    op.create_table(
        "operations_organizations",
        ref("organization_id", "labs.id", primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "operations_books",
        ref("project_id", "projects.id", primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "operations_grants",
        ref("project_id", "operations_books.project_id", primary_key=True),
        ref("user_id", "users.id", primary_key=True),
        sa.Column("role", sa.String(12), nullable=False),
    )
    op.create_table(
        "operations_entries",
        sa.Column("id", sa.UUID(), primary_key=True),
        ref("project_id", "operations_books.project_id", nullable=False, index=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        ref("created_by", "users.id", nullable=False),
        ref("verified_by", "users.id"),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "operations_events",
        sa.Column("id", sa.UUID(), primary_key=True),
        ref("project_id", "operations_books.project_id", nullable=False, index=True),
        ref("entry_id", "operations_entries.id", nullable=False, index=True),
        sa.Column("request_id", sa.UUID(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        ref("actor_id", "users.id", nullable=False),
        sa.Column(
            "at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("before", sa.JSON()),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.UniqueConstraint("project_id", "request_id", name="uq_operations_request"),
    )
    op.create_table(
        "operations_proofs",
        ref("file_id", "research_files.id", primary_key=True),
        ref("project_id", "operations_books.project_id", nullable=False, index=True),
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS(SELECT 1 FROM operations_organizations)")
    ):
        raise RuntimeError(
            "Saved operations settings or ledgers require a recovery plan"
        )
    for name in ("proofs", "events", "entries", "grants", "books", "organizations"):
        op.drop_table("operations_" + name)
