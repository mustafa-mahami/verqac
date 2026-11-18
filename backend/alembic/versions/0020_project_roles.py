"""Roles added in a project: project_id and base_code on roles; project members may write their project's roles.

Revision ID: 0020_project_roles
Revises: 0019_daily_reports
"""
from alembic import op

revision = "0020_project_roles"
down_revision = "0019_daily_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE roles ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE")
    op.execute("ALTER TABLE roles ADD COLUMN IF NOT EXISTS base_code varchar(40)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_roles_project_id ON roles (project_id)")
    # who in the project may change them is checked by the API (each party its own roles)
    op.execute("CREATE POLICY roles_project_write ON roles FOR ALL "
               "USING (project_id IS NOT NULL AND project_id IN (SELECT my_project_ids())) "
               "WITH CHECK (project_id IS NOT NULL AND project_id IN (SELECT my_project_ids()))")
    op.execute("CREATE POLICY rp_project_write ON role_permissions FOR ALL "
               "USING (role_id IN (SELECT id FROM roles WHERE project_id IS NOT NULL AND project_id IN (SELECT my_project_ids()))) "
               "WITH CHECK (role_id IN (SELECT id FROM roles WHERE project_id IS NOT NULL AND project_id IN (SELECT my_project_ids())))")


def downgrade() -> None:
    op.execute("DROP POLICY rp_project_write ON role_permissions")
    op.execute("DROP POLICY roles_project_write ON roles")
    op.execute("DELETE FROM roles WHERE project_id IS NOT NULL")
    op.execute("DROP INDEX ix_roles_project_id")
    op.execute("ALTER TABLE roles DROP COLUMN base_code")
    op.execute("ALTER TABLE roles DROP COLUMN project_id")
