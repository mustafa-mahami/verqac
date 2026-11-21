"""System jobs only: removing the events of test accounts when their test answers are undone.

Revision ID: 0030_events_delete
Revises: 0029_users_delete
"""
from alembic import op

revision = "0030_events_delete"
down_revision = "0029_users_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT DELETE ON record_events TO verqac_app")
    op.execute("DROP POLICY IF EXISTS re_system_delete ON record_events")
    op.execute("CREATE POLICY re_system_delete ON record_events FOR DELETE USING (app_bypass())")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS re_system_delete ON record_events")
    op.execute("REVOKE DELETE ON record_events FROM verqac_app")
