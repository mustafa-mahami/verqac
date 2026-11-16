"""Web Push subscriptions (browser notifications while Verqac is closed).

Revision ID: 0012_push_subscriptions
Revises: 0011_resubmit_due
"""
from alembic import op

from app.models.core import Base

revision = "0012_push_subscriptions"
down_revision = "0011_resubmit_due"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables["push_subscriptions"]])
    op.execute("ALTER TABLE push_subscriptions ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY ps_own ON push_subscriptions FOR ALL "
               "USING (app_bypass() OR user_id = app_user_id()) WITH CHECK (app_bypass() OR user_id = app_user_id())")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON push_subscriptions TO verqac_app")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS push_subscriptions")
