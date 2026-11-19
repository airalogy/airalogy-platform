"""Track private invitation notes and distinguish claims from revocations."""

import sqlalchemy as sa
from alembic import op

revision = "0091_invitation_receipts"
down_revision = "0090_activity_instants"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("account_tokens", sa.Column("invitation_note", sa.String(120)))
    op.add_column("account_tokens", sa.Column("invitation_outcome", sa.String(8)))


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM account_tokens WHERE invitation_note IS NOT NULL "
            "OR invitation_outcome IS NOT NULL OR (token_type='invitation' AND email=''))"
        )
    ):
        raise RuntimeError(
            "Invitation history exists. Retain the schema or restore a verified backup."
        )
    op.drop_column("account_tokens", "invitation_outcome")
    op.drop_column("account_tokens", "invitation_note")
