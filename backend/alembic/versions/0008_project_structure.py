"""Project structure: project types with templates, project stages and locations; records get a stage
and locations; existing organizations get the default project types.

Revision ID: 0008_project_structure
Revises: 0007_required_by
"""
from alembic import op
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.seed_structure import default_types
from app.models.core import Base
from app.models.structure import STRUCTURE_TABLES

revision = "0008_project_structure"
down_revision = "0007_required_by"
branch_labels = None
depends_on = None

APP_ROLE = "verqac_app"

SQL = """
ALTER TABLE projects ADD COLUMN IF NOT EXISTS project_type_id uuid;
ALTER TABLE projects ADD CONSTRAINT projects_project_type_fk FOREIGN KEY (project_type_id) REFERENCES project_types(id);
ALTER TABLE records ADD COLUMN IF NOT EXISTS stage_id uuid;
ALTER TABLE records ADD COLUMN IF NOT EXISTS all_locations boolean NOT NULL DEFAULT false;
ALTER TABLE records ADD COLUMN IF NOT EXISTS location_ids uuid[];
ALTER TABLE records ADD CONSTRAINT records_stage_fk FOREIGN KEY (stage_id) REFERENCES project_stages(id);
CREATE INDEX IF NOT EXISTS ix_records_stage ON records (stage_id);

-- an organization's project types: its members read them, its admins change them
ALTER TABLE project_types ENABLE ROW LEVEL SECURITY;
CREATE POLICY pt_select ON project_types FOR SELECT USING (app_bypass() OR org_id IN (SELECT my_org_ids()));
CREATE POLICY pt_write ON project_types FOR ALL
  USING (app_bypass() OR org_id IN (SELECT my_admin_org_ids()))
  WITH CHECK (app_bypass() OR org_id IN (SELECT my_admin_org_ids()));

-- a project's stages and locations: every party of the project reads them (the API decides who edits)
ALTER TABLE project_stages ENABLE ROW LEVEL SECURITY;
CREATE POLICY ps_all ON project_stages FOR ALL
  USING (app_bypass() OR project_id IN (SELECT my_project_ids()))
  WITH CHECK (app_bypass() OR project_id IN (SELECT my_project_ids()));
ALTER TABLE project_locations ENABLE ROW LEVEL SECURITY;
CREATE POLICY pl_all ON project_locations FOR ALL
  USING (app_bypass() OR project_id IN (SELECT my_project_ids()))
  WITH CHECK (app_bypass() OR project_id IN (SELECT my_project_ids()));
"""


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables[t] for t in STRUCTURE_TABLES])
    op.execute(SQL)
    for t in STRUCTURE_TABLES:
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO {APP_ROLE}")
    db = Session(bind=op.get_bind())
    for (org_id,) in db.execute(text("SELECT id FROM organizations")).all():
        db.add_all(default_types(org_id))
    db.flush()


def downgrade() -> None:
    op.execute("ALTER TABLE records DROP CONSTRAINT IF EXISTS records_stage_fk")
    op.execute("ALTER TABLE records DROP COLUMN IF EXISTS location_ids, DROP COLUMN IF EXISTS all_locations, "
               "DROP COLUMN IF EXISTS stage_id")
    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_project_type_fk")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS project_type_id")
    for t in reversed(STRUCTURE_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
