"""Add private meeting sources, organization minutes and scoped follow-up."""

import sqlalchemy as sa
from alembic import op

revision = "0102_meeting_workspace"
down_revision = "0101_guest_directory_names"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meeting_spaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("lab_id", sa.Uuid(), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column(
            "project_meeting_id",
            sa.Uuid(),
            sa.ForeignKey("meetings.document_id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_format", sa.String(length=12), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
    )
    op.create_index("ix_meeting_spaces_lab_id", "meeting_spaces", ["lab_id"])
    op.create_table(
        "meeting_space_projects",
        sa.Column(
            "meeting_id",
            sa.Uuid(),
            sa.ForeignKey("meeting_spaces.id"),
            primary_key=True,
        ),
        sa.Column(
            "project_id", sa.Uuid(), sa.ForeignKey("projects.id"), primary_key=True
        ),
    )
    op.create_table(
        "meeting_space_people",
        sa.Column(
            "meeting_id",
            sa.Uuid(),
            sa.ForeignKey("meeting_spaces.id"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
    )
    op.create_table(
        "meeting_minutes_editions",
        sa.Column(
            "meeting_id",
            sa.Uuid(),
            sa.ForeignKey("meeting_spaces.id"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("body_format", sa.String(length=12), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "meeting_minutes_shares",
        sa.Column(
            "meeting_id",
            sa.Uuid(),
            sa.ForeignKey("meeting_spaces.id"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "meeting_transcripts",
        sa.Column(
            "meeting_id",
            sa.Uuid(),
            sa.ForeignKey("meeting_spaces.id"),
            primary_key=True,
        ),
        sa.Column("original", sa.LargeBinary(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("cues", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
    )
    op.create_table(
        "meeting_audio",
        sa.Column(
            "meeting_id",
            sa.Uuid(),
            sa.ForeignKey("meeting_spaces.id"),
            primary_key=True,
        ),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("mime", sa.String(length=128), nullable=False),
        sa.Column("backend", sa.String(length=64), nullable=False),
    )
    op.create_table(
        "meeting_follow_ups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "meeting_id", sa.Uuid(), sa.ForeignKey("meeting_spaces.id"), nullable=False
        ),
        sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column(
            "project_work_id",
            sa.Uuid(),
            sa.ForeignKey("project_work.task_id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("assignee_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("audience", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("due", sa.Date(), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
    )
    op.create_index(
        "ix_meeting_follow_ups_assignee_id", "meeting_follow_ups", ["assignee_id"]
    )
    op.create_index(
        "ix_meeting_follow_ups_meeting_id", "meeting_follow_ups", ["meeting_id"]
    )
    op.create_table(
        "meeting_follow_up_readers",
        sa.Column(
            "task_id",
            sa.Uuid(),
            sa.ForeignKey("meeting_follow_ups.id"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), primary_key=True),
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM meeting_spaces)")):
        raise RuntimeError("Preserve meeting data before downgrade")
    op.drop_table("meeting_follow_up_readers")
    op.drop_table("meeting_follow_ups")
    op.drop_table("meeting_audio")
    op.drop_table("meeting_transcripts")
    op.drop_table("meeting_minutes_shares")
    op.drop_table("meeting_minutes_editions")
    op.drop_table("meeting_space_people")
    op.drop_table("meeting_space_projects")
    op.drop_table("meeting_spaces")
