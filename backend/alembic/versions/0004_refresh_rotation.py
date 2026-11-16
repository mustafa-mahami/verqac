"""Refresh tokens remember when they were rotated, for the reuse grace window.

Revision ID: 0004_refresh_rotation
Revises: 0003_records
"""
from alembic import op

revision = "0004_refresh_rotation"
down_revision = "0003_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS rotated_at timestamptz")


def downgrade() -> None:
    op.execute("ALTER TABLE refresh_tokens DROP COLUMN IF EXISTS rotated_at")
