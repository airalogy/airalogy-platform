"""Versioned external analysis snapshots and private result provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0082_external_research"
down_revision = "0081_project_visits"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "external_grants", sa.Column("audience", sa.String(2048), nullable=True)
    )
    op.create_table(
        "external_oauth_clients",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("redirect_uris", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_external_oauth_clients_user_id", "external_oauth_clients", ["user_id"]
    )
    op.add_column(
        "external_grants", sa.Column("oauth_client_id", sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        "fk_external_grant_oauth_client",
        "external_grants",
        "external_oauth_clients",
        ["oauth_client_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "external_oauth_codes",
        sa.Column("code_hash", sa.String(64), primary_key=True),
        sa.Column(
            "client_id",
            sa.UUID(),
            sa.ForeignKey("external_oauth_clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "grant_id",
            sa.UUID(),
            sa.ForeignKey("external_grants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("redirect_uri", sa.String(2048), nullable=False),
        sa.Column("challenge", sa.String(43), nullable=False),
        sa.Column("resource", sa.String(2048), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("external_operations", "protocol_id", nullable=True)
    op.alter_column("external_operations", "protocol_version_id", nullable=True)
    op.alter_column("external_operations", "kind", type_=sa.String(32))
    op.create_table(
        "external_snapshots",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "grant_id",
            sa.UUID(),
            sa.ForeignKey("external_grants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("request_key", sa.String(100), nullable=False),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("policy_revision", sa.Integer(), nullable=False),
        sa.Column("selection", sa.JSON(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "grant_id", "request_key", name="uq_external_snapshot_request"
        ),
    )
    for field in ("grant_id", "project_id", "user_id"):
        op.create_index(f"ix_external_snapshots_{field}", "external_snapshots", [field])
    op.create_table(
        "external_analysis_sources",
        sa.Column(
            "run_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "snapshot_id",
            sa.UUID(),
            sa.ForeignKey("external_snapshots.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "grant_id",
            sa.UUID(),
            sa.ForeignKey("external_grants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_external_analysis_sources_snapshot_id",
        "external_analysis_sources",
        ["snapshot_id"],
    )
    op.create_table(
        "external_analysis_files",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "run_id",
            sa.UUID(),
            sa.ForeignKey("analysis_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "blob_id",
            sa.UUID(),
            sa.ForeignKey("research_file_blobs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.UniqueConstraint("run_id", "filename", name="uq_external_analysis_filename"),
    )
    op.create_index(
        "ix_external_analysis_files_run_id", "external_analysis_files", ["run_id"]
    )

    op.execute("""
        CREATE FUNCTION guard_external_snapshot() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'External snapshots are immutable';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER external_snapshot_immutable BEFORE UPDATE ON external_snapshots
        FOR EACH ROW EXECUTE FUNCTION guard_external_snapshot();
    """)


def downgrade():
    # Confirmed analysis assets must be exported or removed explicitly first.
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM external_analysis_sources")):
        raise RuntimeError("Cannot downgrade while external analysis assets exist")
    # Removing audience binding must never turn an OAuth credential into a
    # broader legacy token. Existing manual grants are unaffected.
    op.execute(
        "UPDATE external_operations SET state = 'revoked', payload = '{}' WHERE grant_id IN (SELECT id FROM external_grants WHERE audience IS NOT NULL) AND state IN ('pending', 'approved')"
    )
    op.execute(
        "UPDATE external_grants SET revoked_at = now() WHERE audience IS NOT NULL AND revoked_at IS NULL"
    )
    op.drop_table("external_oauth_codes")
    op.drop_constraint(
        "fk_external_grant_oauth_client", "external_grants", type_="foreignkey"
    )
    op.drop_column("external_grants", "oauth_client_id")
    op.drop_table("external_oauth_clients")
    op.drop_column("external_grants", "audience")
    op.drop_table("external_analysis_files")
    op.drop_table("external_analysis_sources")
    op.drop_table("external_snapshots")
    op.execute("DROP FUNCTION guard_external_snapshot()")
    op.execute(
        "DELETE FROM external_operations WHERE kind NOT IN ('import', 'revision')"
    )
    op.alter_column("external_operations", "protocol_id", nullable=False)
    op.alter_column("external_operations", "protocol_version_id", nullable=False)
    op.alter_column("external_operations", "kind", type_=sa.String(20))
