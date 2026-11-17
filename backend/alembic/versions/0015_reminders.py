"""Deadline reminders already sent.

Revision ID: 0015_reminders
Revises: 0014_checklists
"""
from alembic import op

from app.models.core import Base
import app.models.records  # noqa: F401 - registers the table

revision = "0015_reminders"
down_revision = "0014_checklists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables["record_reminders"]])
    op.execute("ALTER TABLE record_reminders ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY rr_system ON record_reminders FOR ALL USING (app_bypass()) WITH CHECK (app_bypass())")
    op.execute("GRANT SELECT, INSERT, DELETE ON record_reminders TO verqac_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS record_reminders")
