"""Project meetings reuse document/task identities; additive, no content rewrite."""

import sqlalchemy as sa
from alembic import op

revision = "0087_project_meetings"
down_revision = "0086_project_work"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meetings",
        sa.Column(
            "document_id",
            sa.UUID(),
            sa.ForeignKey("research_documents.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("time_precision", sa.String(16), nullable=False),
        sa.Column("time_zone", sa.String(64), nullable=False),
        sa.Column("create_digest", sa.String(64), nullable=False),
        sa.CheckConstraint(
            "status IN ('held','planned','cancelled')", name="ck_meeting_status"
        ),
        sa.CheckConstraint(
            "visibility IN ('project','selected')", name="ck_meeting_visibility"
        ),
        sa.CheckConstraint(
            "time_precision IN ('date','datetime')", name="ck_meeting_precision"
        ),
    )
    op.create_table(
        "meeting_participants",
        sa.Column(
            "id",
            sa.UUID(),
            primary_key=True,
            server_default=sa.text("uuid_generate_v7()"),
        ),
        sa.Column(
            "meeting_id",
            sa.UUID(),
            sa.ForeignKey("meetings.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("organization", sa.String(255), nullable=False),
        sa.Column("attendance", sa.String(16), nullable=False),
        sa.UniqueConstraint(
            "meeting_id", "user_id", name="uq_meeting_participant_user"
        ),
    )
    op.create_index(
        "ix_meeting_participants_meeting_id", "meeting_participants", ["meeting_id"]
    )
    op.create_index(
        "ix_meeting_participants_user_id", "meeting_participants", ["user_id"]
    )
    op.create_table(
        "meeting_access",
        sa.Column(
            "meeting_id",
            sa.UUID(),
            sa.ForeignKey("meetings.document_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("role", sa.String(16), nullable=False),
    )
    op.create_table(
        "meeting_comments",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "meeting_id",
            sa.UUID(),
            sa.ForeignKey("meetings.document_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_meeting_comments_meeting_id", "meeting_comments", ["meeting_id"]
    )
    op.create_table(
        "meeting_work_links",
        sa.Column(
            "meeting_id",
            sa.UUID(),
            sa.ForeignKey("meetings.document_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "task_id",
            sa.UUID(),
            sa.ForeignKey("project_work.task_id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("relation", sa.String(16), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=False),
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
    )


def downgrade():
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM meetings)"))
        .scalar()
    ):
        raise RuntimeError(
            "Meetings exist; use a meeting-aware recovery build, not a destructive downgrade"
        )
    for table in [
        "meeting_work_links",
        "meeting_comments",
        "meeting_access",
        "meeting_participants",
        "meetings",
    ]:
        op.drop_table(table)
