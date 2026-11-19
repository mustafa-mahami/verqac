"""Attachment kind 'signed': the paper copy signed by hand, scanned or photographed (any time after the answer).

Revision ID: 0025_signed_copy
Revises: 0024_attachment_caption
"""
from alembic import op

revision = "0025_signed_copy"
down_revision = "0024_attachment_caption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE attachments DROP CONSTRAINT IF EXISTS kind_valid")
    op.execute("ALTER TABLE attachments ADD CONSTRAINT kind_valid CHECK (kind IN ('submission', 'response', 'photo', 'signed', 'other'))")


def downgrade() -> None:
    op.execute("ALTER TABLE attachments DROP CONSTRAINT IF EXISTS kind_valid")
    op.execute("ALTER TABLE attachments ADD CONSTRAINT kind_valid CHECK (kind IN ('submission', 'response', 'photo', 'other'))")
