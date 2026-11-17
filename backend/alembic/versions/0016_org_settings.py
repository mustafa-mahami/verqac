"""Organization settings (its working calendar: weekly days off and official holidays).

Revision ID: 0016_org_settings
Revises: 0015_reminders
"""
from alembic import op

revision = "0016_org_settings"
down_revision = "0015_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organizations ADD COLUMN IF NOT EXISTS settings jsonb NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE organizations DROP COLUMN IF EXISTS settings")
