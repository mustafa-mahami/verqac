"""Organization user suspension, invitations straight into a project team, record assignment,
in-app notifications.

Revision ID: 0005_users_inbox_notifications
Revises: 0004_refresh_rotation
"""
from alembic import op

revision = "0005_users_inbox_notifications"
down_revision = "0004_refresh_rotation"
branch_labels = None
depends_on = None

APP_ROLE = "verqac_app"


def upgrade() -> None:
    op.execute("ALTER TABLE org_members ADD COLUMN IF NOT EXISTS is_active boolean NOT NULL DEFAULT true")
    op.execute("ALTER TABLE invitations ADD COLUMN IF NOT EXISTS discipline_ids uuid[]")
    op.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS assigned_to uuid REFERENCES users(id)")
    op.execute("""
CREATE TABLE IF NOT EXISTS notifications (
  id bigserial PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  project_id uuid REFERENCES projects(id) ON DELETE CASCADE,
  record_id uuid REFERENCES records(id) ON DELETE CASCADE,
  event varchar(40) NOT NULL,
  title_ar varchar(300) NOT NULL,
  title_en varchar(300) NOT NULL,
  body text,
  created_at timestamptz NOT NULL DEFAULT now(),
  read_at timestamptz
);
CREATE INDEX IF NOT EXISTS notifications_user_unread ON notifications (user_id, read_at, created_at DESC);

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
-- everyone reads and marks only their own; anyone acting on a record may notify others
CREATE POLICY ntf_select ON notifications FOR SELECT USING (app_bypass() OR user_id = app_user_id());
CREATE POLICY ntf_update ON notifications FOR UPDATE USING (app_bypass() OR user_id = app_user_id());
CREATE POLICY ntf_insert ON notifications FOR INSERT WITH CHECK (app_user_id() IS NOT NULL OR app_bypass());

-- a suspended membership no longer opens anything
CREATE OR REPLACE FUNCTION my_org_ids() RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS
$$ SELECT org_id FROM org_members WHERE user_id = app_user_id() AND is_active $$;
CREATE OR REPLACE FUNCTION my_admin_org_ids() RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS
$$ SELECT org_id FROM org_members WHERE user_id = app_user_id() AND org_role = 'admin' AND is_active $$;
""")
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON notifications TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON SEQUENCE notifications_id_seq TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notifications")
    op.execute("ALTER TABLE records DROP COLUMN IF EXISTS assigned_to")
    op.execute("ALTER TABLE invitations DROP COLUMN IF EXISTS discipline_ids")
    op.execute("ALTER TABLE org_members DROP COLUMN IF EXISTS is_active")
