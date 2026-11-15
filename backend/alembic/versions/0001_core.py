"""Core tables, Row-Level Security, grants and platform roles.

Revision ID: 0001_core
Revises:
"""
from alembic import op

from app.core.seed import PLATFORM_ROLES
from app.models.core import Base

revision = "0001_core"
down_revision = None
branch_labels = None
depends_on = None

APP_ROLE = "verqac_app"

TABLES = [
    "organizations", "users", "org_members", "disciplines", "roles", "role_permissions",
    "projects", "project_parties", "project_members", "invitations", "refresh_tokens", "audit_log",
]

HELPERS = """
CREATE OR REPLACE FUNCTION app_user_id() RETURNS uuid LANGUAGE sql STABLE AS
$$ SELECT nullif(current_setting('app.user_id', true), '')::uuid $$;

CREATE OR REPLACE FUNCTION app_bypass() RETURNS boolean LANGUAGE sql STABLE AS
$$ SELECT coalesce(current_setting('app.bypass', true), '') = 'on' $$;

-- SECURITY DEFINER: run as the owner, so they read the tables without RLS (no recursion).
CREATE OR REPLACE FUNCTION my_org_ids() RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS
$$ SELECT org_id FROM org_members WHERE user_id = app_user_id() $$;

CREATE OR REPLACE FUNCTION my_admin_org_ids() RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS
$$ SELECT org_id FROM org_members WHERE user_id = app_user_id() AND org_role = 'admin' $$;

-- A project is visible to its active members, and to the admins of the owner org
-- and of any active party org. Draft-level and discipline rules live in the services.
CREATE OR REPLACE FUNCTION my_project_ids() RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS
$$
  SELECT project_id FROM project_members WHERE user_id = app_user_id() AND is_active
  UNION
  SELECT id FROM projects WHERE owner_org_id IN (SELECT my_admin_org_ids())
  UNION
  SELECT project_id FROM project_parties
   WHERE status = 'active' AND org_id IN (SELECT my_admin_org_ids())
$$;

CREATE OR REPLACE FUNCTION my_visible_org_ids() RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS
$$
  SELECT my_org_ids()
  UNION
  SELECT org_id FROM project_parties WHERE org_id IS NOT NULL AND project_id IN (SELECT my_project_ids())
  UNION
  SELECT owner_org_id FROM projects WHERE id IN (SELECT my_project_ids())
$$;

CREATE OR REPLACE FUNCTION my_visible_user_ids() RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS
$$
  SELECT app_user_id()
  UNION
  SELECT user_id FROM org_members WHERE org_id IN (SELECT my_org_ids())
  UNION
  SELECT user_id FROM project_members WHERE project_id IN (SELECT my_project_ids())
$$;
"""

POLICIES = """
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
CREATE POLICY org_select ON organizations FOR SELECT USING (app_bypass() OR id IN (SELECT my_visible_org_ids()));
CREATE POLICY org_insert ON organizations FOR INSERT WITH CHECK (app_bypass());
CREATE POLICY org_update ON organizations FOR UPDATE USING (app_bypass() OR id IN (SELECT my_admin_org_ids()));

ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY users_select ON users FOR SELECT USING (app_bypass() OR id IN (SELECT my_visible_user_ids()));
CREATE POLICY users_insert ON users FOR INSERT WITH CHECK (app_bypass() OR app_user_id() IS NOT NULL);
CREATE POLICY users_update ON users FOR UPDATE USING (app_bypass() OR id = app_user_id());

ALTER TABLE org_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY om_select ON org_members FOR SELECT USING (app_bypass() OR org_id IN (SELECT my_org_ids()));
CREATE POLICY om_write ON org_members FOR ALL
  USING (app_bypass() OR org_id IN (SELECT my_admin_org_ids()))
  WITH CHECK (app_bypass() OR org_id IN (SELECT my_admin_org_ids()));

ALTER TABLE disciplines ENABLE ROW LEVEL SECURITY;
CREATE POLICY disc_select ON disciplines FOR SELECT USING (app_bypass() OR org_id IN (SELECT my_visible_org_ids()));
CREATE POLICY disc_write ON disciplines FOR ALL
  USING (app_bypass() OR org_id IN (SELECT my_admin_org_ids()))
  WITH CHECK (app_bypass() OR org_id IN (SELECT my_admin_org_ids()));

ALTER TABLE roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY roles_select ON roles FOR SELECT USING (app_bypass() OR org_id IS NULL OR org_id IN (SELECT my_visible_org_ids()));
CREATE POLICY roles_write ON roles FOR ALL
  USING (app_bypass() OR org_id IN (SELECT my_admin_org_ids()))
  WITH CHECK (app_bypass() OR org_id IN (SELECT my_admin_org_ids()));

ALTER TABLE role_permissions ENABLE ROW LEVEL SECURITY;
CREATE POLICY rp_select ON role_permissions FOR SELECT USING (app_bypass() OR role_id IN (SELECT id FROM roles));
CREATE POLICY rp_write ON role_permissions FOR ALL
  USING (app_bypass() OR role_id IN (SELECT id FROM roles WHERE org_id IN (SELECT my_admin_org_ids())))
  WITH CHECK (app_bypass() OR role_id IN (SELECT id FROM roles WHERE org_id IN (SELECT my_admin_org_ids())));

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
-- owner_org_id test on the row itself: an INSERT ... RETURNING must see its own new row.
CREATE POLICY prj_select ON projects FOR SELECT
  USING (app_bypass() OR id IN (SELECT my_project_ids()) OR owner_org_id IN (SELECT my_admin_org_ids()));
CREATE POLICY prj_insert ON projects FOR INSERT WITH CHECK (app_bypass() OR owner_org_id IN (SELECT my_admin_org_ids()));
CREATE POLICY prj_update ON projects FOR UPDATE USING (app_bypass() OR id IN (SELECT my_project_ids()));

ALTER TABLE project_parties ENABLE ROW LEVEL SECURITY;
CREATE POLICY pp_all ON project_parties FOR ALL
  USING (app_bypass() OR project_id IN (SELECT my_project_ids()))
  WITH CHECK (app_bypass() OR project_id IN (SELECT my_project_ids()));

ALTER TABLE project_members ENABLE ROW LEVEL SECURITY;
CREATE POLICY pm_all ON project_members FOR ALL
  USING (app_bypass() OR project_id IN (SELECT my_project_ids()))
  WITH CHECK (app_bypass() OR project_id IN (SELECT my_project_ids()));

ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;
CREATE POLICY inv_all ON invitations FOR ALL
  USING (app_bypass() OR project_id IN (SELECT my_project_ids()) OR org_id IN (SELECT my_admin_org_ids()))
  WITH CHECK (app_bypass() OR project_id IN (SELECT my_project_ids()) OR org_id IN (SELECT my_admin_org_ids()));

ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY;
CREATE POLICY rt_all ON refresh_tokens FOR ALL
  USING (app_bypass() OR user_id = app_user_id())
  WITH CHECK (app_bypass() OR user_id = app_user_id());

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
CREATE POLICY audit_select ON audit_log FOR SELECT
  USING (app_bypass() OR org_id IN (SELECT my_admin_org_ids()) OR project_id IN (SELECT my_project_ids()));
CREATE POLICY audit_insert ON audit_log FOR INSERT WITH CHECK (true);
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    Base.metadata.create_all(bind=op.get_bind())
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower ON users (lower(email))")
    op.execute(HELPERS)
    op.execute(POLICIES)

    # The application role: no ownership, no DDL, audit log is append-only.
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    for t in TABLES:
        if t == "audit_log":
            op.execute(f"GRANT SELECT, INSERT ON audit_log TO {APP_ROLE}")
        else:
            op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {APP_ROLE}")

    for i, (code, party, name_ar, name_en, flags, perms) in enumerate(PLATFORM_ROLES):
        cols = {"manage_project": False, "manage_team": False, "act_on_behalf": False, **flags}
        op.execute(
            "INSERT INTO roles (code, party_kind, name_ar, name_en, manage_project, manage_team, act_on_behalf, sort) "
            f"VALUES ('{code}', '{party}', '{name_ar}', '{name_en.replace(chr(39), chr(39) * 2)}', "
            f"{cols['manage_project']}, {cols['manage_team']}, {cols['act_on_behalf']}, {(i + 1) * 10})"
        )
        for record_type, actions, scope in perms:
            for action in actions:
                op.execute(
                    "INSERT INTO role_permissions (role_id, record_type, action, scope) "
                    f"SELECT id, '{record_type}', '{action}', '{scope}' FROM roles "
                    f"WHERE org_id IS NULL AND code = '{code}'"
                )


def downgrade() -> None:
    for t in reversed(TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    for f in ("my_visible_user_ids", "my_visible_org_ids", "my_project_ids", "my_admin_org_ids",
              "my_org_ids", "app_bypass", "app_user_id"):
        op.execute(f"DROP FUNCTION IF EXISTS {f}()")
