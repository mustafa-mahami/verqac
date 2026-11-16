"""Index on approval stamps, for the public verification page (QR on the printed reply).

Revision ID: 0006_stamp_index
Revises: 0005_users_inbox_notifications
"""
from alembic import op

revision = "0006_stamp_index"
down_revision = "0005_users_inbox_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_record_events_stamp ON record_events (stamp) WHERE stamp IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_record_events_stamp")
