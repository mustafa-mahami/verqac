"""Stages limited to some floors (project_stages.location_ids; empty = all floors); records can be deleted by
system jobs only (the Odoo import replaces a project's records), never by a user.

Revision ID: 0023_stage_locations
Revises: 0022_project_reminders
"""
from alembic import op

revision = "0023_stage_locations"
down_revision = "0022_project_reminders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE project_stages ADD COLUMN IF NOT EXISTS location_ids uuid[]")
    op.execute("DROP POLICY IF EXISTS rec_system_delete ON records")
    op.execute("CREATE POLICY rec_system_delete ON records FOR DELETE USING (app_bypass())")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS rec_system_delete ON records")
    op.execute("ALTER TABLE project_stages DROP COLUMN IF EXISTS location_ids")
