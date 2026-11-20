"""Keep the intended organization display name separate from the invitation note."""

import sqlalchemy as sa
from alembic import op

revision = "0095_invitation_display_name"
down_revision = "0094_meeting_conversations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "account_tokens", sa.Column("invitation_display_name", sa.String(255))
    )


def downgrade():
    op.execute("LOCK TABLE account_tokens IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM account_tokens "
            "WHERE invitation_display_name IS NOT NULL)"
        )
    ):
        raise RuntimeError("Preserve invitation display names before downgrading")
    op.drop_column("account_tokens", "invitation_display_name")
