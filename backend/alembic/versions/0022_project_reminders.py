"""Project reminders (a working day without a daily report): each goes out once.

Revision ID: 0022_project_reminders
Revises: 0021_programme
"""
from alembic import op

import app.models.records  # noqa: F401 - registers the table
from app.models.core import Base

revision = "0022_project_reminders"
down_revision = "0021_programme"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables["project_reminders"]])
    op.execute("ALTER TABLE project_reminders ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY pr_system ON project_reminders FOR ALL USING (app_bypass()) WITH CHECK (app_bypass())")
    op.execute("GRANT SELECT, INSERT, DELETE ON project_reminders TO verqac_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS project_reminders")
