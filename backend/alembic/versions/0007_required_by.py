"""Records: the latest date the author needs an answer by (supply schedule), with a short reason.

Revision ID: 0007_required_by
Revises: 0006_stamp_index
"""
from alembic import op

revision = "0007_required_by"
down_revision = "0006_stamp_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS required_by date")
    op.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS required_by_note varchar(300)")


def downgrade() -> None:
    op.execute("ALTER TABLE records DROP COLUMN IF EXISTS required_by_note")
    op.execute("ALTER TABLE records DROP COLUMN IF EXISTS required_by")
