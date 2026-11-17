"""Optional project contacts and action details; preserve existing identities."""

import sqlalchemy as sa
from alembic import op

revision = "0088_project_people"
down_revision = "0087_project_meetings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "project_people",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "project_id",
            sa.UUID(),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("organization", sa.String(255), nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("account_history", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_by_user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("create_digest", sa.String(64), nullable=False),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_person_user"),
    )
    op.create_index("ix_project_people_project_id", "project_people", ["project_id"])
    op.add_column(
        "project_work",
        sa.Column(
            "assignee_person_id",
            sa.UUID(),
            sa.ForeignKey("project_people.id", ondelete="RESTRICT"),
        ),
    )
    op.create_index(
        "ix_project_work_assignee_person_id", "project_work", ["assignee_person_id"]
    )
    for name in ["collaborator_person_ids", "people_snapshot"]:
        op.add_column(
            "project_work",
            sa.Column(name, sa.JSON(), nullable=False, server_default="[]"),
        )
    op.add_column(
        "project_work",
        sa.Column("deadline_note", sa.String(1000), nullable=False, server_default=""),
    )
    op.add_column(
        "meeting_participants",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "meeting_participants",
        sa.Column(
            "person_id",
            sa.UUID(),
            sa.ForeignKey("project_people.id", ondelete="RESTRICT"),
        ),
    )
    op.create_index(
        "ix_meeting_participants_person_id", "meeting_participants", ["person_id"]
    )
    op.create_table(
        "meeting_action_batches",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "meeting_id",
            sa.UUID(),
            sa.ForeignKey("meetings.document_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "actor_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("digest", sa.String(64), nullable=False),
    )
    op.create_index(
        "ix_meeting_action_batches_meeting_id", "meeting_action_batches", ["meeting_id"]
    )


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM project_people) OR EXISTS (SELECT 1 FROM meeting_action_batches) OR EXISTS (SELECT 1 FROM project_work WHERE deadline_note <> '') OR EXISTS (SELECT 1 FROM meeting_participants WHERE position <> 0)"
            )
        )
        .scalar()
    ):
        raise RuntimeError(
            "People or action details exist; use a compatible recovery build"
        )
    op.drop_column("meeting_participants", "position")
    op.drop_column("meeting_participants", "person_id")
    for column in [
        "assignee_person_id",
        "collaborator_person_ids",
        "people_snapshot",
        "deadline_note",
    ]:
        op.drop_column("project_work", column)
    op.drop_table("project_people")
    op.drop_table("meeting_action_batches")
