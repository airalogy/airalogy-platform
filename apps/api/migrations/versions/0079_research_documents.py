"""AIMD research documents, independent materials and immutable submissions."""

import sqlalchemy as sa
from alembic import op

revision = "0079_research_documents"
down_revision = "0078_external_agent_access"
branch_labels = None
depends_on = None
TABLE_NAMES = (
    "research_documents",
    "research_materials",
    "research_document_submissions",
    "research_document_derivations",
)


def upgrade():
    op.create_table(
        "research_documents",
        sa.Column(
            "id",
            sa.UUID(),
            sa.ForeignKey("research_log_entries.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("format_version", sa.String(32), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("record_data", sa.JSON(), nullable=False),
        sa.Column("file_ids", sa.JSON(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("collection", sa.String(255), nullable=False),
        sa.Column("origin", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "state IN ('draft', 'submitted')", name="ck_research_document_state"
        ),
    )
    op.create_table(
        "research_materials",
        sa.Column(
            "id",
            sa.UUID(),
            sa.ForeignKey("research_files.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("source_note", sa.String(4000), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True)),
        sa.Column("request_key", sa.UUID(), nullable=False, unique=True),
    )
    for table in ("research_document_submissions", "research_document_derivations"):
        extra = (
            [
                sa.Column("kind", sa.String(32), nullable=False),
                sa.Column(
                    "knowledge_id",
                    sa.UUID(),
                    sa.ForeignKey("knowledge_items.id", ondelete="RESTRICT"),
                ),
                sa.UniqueConstraint(
                    "document_id",
                    "source_revision",
                    "kind",
                    name="uq_document_derivation",
                ),
            ]
            if table.endswith("derivations")
            else [
                sa.UniqueConstraint(
                    "document_id",
                    "source_revision",
                    name="uq_document_submission_revision",
                )
            ]
        )
        op.create_table(
            table,
            sa.Column(
                "id",
                sa.UUID(),
                primary_key=True,
                server_default=sa.text("uuid_generate_v7()"),
            ),
            sa.Column(
                "document_id",
                sa.UUID(),
                sa.ForeignKey("research_documents.id", ondelete="RESTRICT"),
                nullable=False,
                index=True,
            ),
            sa.Column("source_revision", sa.Integer(), nullable=False),
            sa.Column("snapshot", sa.JSON(), nullable=False),
            sa.Column("digest", sa.String(64), nullable=False),
            sa.Column(
                "created_by_user_id",
                sa.UUID(),
                sa.ForeignKey("users.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            *extra,
        )
    op.execute("""
        CREATE FUNCTION protect_research_document_evidence() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'Research document evidence is immutable';
        END;
        $$ LANGUAGE plpgsql
    """)
    for table in ("research_document_submissions", "research_document_derivations"):
        op.execute(
            f"CREATE TRIGGER protect_document_evidence BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_research_document_evidence()"
        )


def downgrade():
    # A downgrade is allowed only before anyone has used the new capability.
    connection = op.get_bind()
    for table in TABLE_NAMES:
        if connection.execute(
            sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")
        ).scalar():
            raise RuntimeError(
                "Research documents/materials exist; export and recover them before downgrade"
            )
    for table in reversed(TABLE_NAMES):
        op.drop_table(table)
    op.execute("DROP FUNCTION protect_research_document_evidence()")
