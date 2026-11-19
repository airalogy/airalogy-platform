"""Keep bounded personal preference suggestions and the most recent undo receipt."""

import sqlalchemy as sa
from alembic import op

revision = "0093_aira_memory_interaction"
down_revision = "0092_merge_project_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("aira_memories", sa.Column("interaction", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("aira_memories", "interaction")
