"""One-time password reset links.

Revision ID: 0010_password_resets
Revises: 0009_stage_topics
"""
from alembic import op

from app.models.core import Base

revision = "0010_password_resets"
down_revision = "0009_stage_topics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables["password_resets"]])
    # only system sessions (app.bypass) touch it: the token, not a signed-in user, is the key
    op.execute("ALTER TABLE password_resets ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY pr_system ON password_resets FOR ALL USING (app_bypass()) WITH CHECK (app_bypass())")
    op.execute("GRANT SELECT, INSERT, UPDATE ON password_resets TO verqac_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS password_resets")
