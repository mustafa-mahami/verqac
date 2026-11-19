"""A short caption on an attachment (what the photo shows, like Odoo's image description).

Revision ID: 0024_attachment_caption
Revises: 0023_stage_locations
"""
from alembic import op

revision = "0024_attachment_caption"
down_revision = "0023_stage_locations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE attachments ADD COLUMN IF NOT EXISTS caption varchar(300)")


def downgrade() -> None:
    op.execute("ALTER TABLE attachments DROP COLUMN IF EXISTS caption")
