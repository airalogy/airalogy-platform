"""Reusable, privately scoped research document templates."""

import sqlalchemy as sa
from alembic import op

revision = "0080_document_templates"
down_revision = "0079_research_documents"
branch_labels = None
depends_on = None


def upgrade():
    LOG_SCOPE_CHECK = (
        "(scope_type = 'personal' AND owner_user_id IS NOT NULL AND lab_id IS NULL AND project_id IS NULL) OR "
        "(scope_type = 'lab' AND owner_user_id IS NULL AND lab_id IS NOT NULL AND project_id IS NULL) OR "
        "(scope_type = 'project' AND owner_user_id IS NULL AND lab_id IS NOT NULL AND project_id IS NOT NULL)"
    )

    op.create_table(
        "document_templates",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column(
            "owner_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column(
            "lab_id",
            sa.UUID(),
            sa.ForeignKey("labs.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            index=True,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("description", sa.String(2000), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=False),
        sa.Column("create_digest", sa.String(64), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(LOG_SCOPE_CHECK, name="ck_document_template_scope"),
    )
    op.create_table(
        "document_template_revisions",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("uuid_generate_v7()"),
        ),
        sa.Column(
            "template_id",
            sa.UUID(),
            sa.ForeignKey("document_templates.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "template_id", "revision", name="uq_document_template_revision"
        ),
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM document_templates)")
    ):
        raise RuntimeError(
            "Document templates exist; export and recover before downgrade"
        )
    op.drop_table("document_template_revisions")
    op.drop_table("document_templates")
