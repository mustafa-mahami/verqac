"""Time programme: record type "programme" (review workflow, revisions) and the programmes table.

Revision ID: 0021_programme
Revises: 0020_project_roles
"""
from alembic import op

import app.models.programme  # noqa: F401 - registers the table
from app.core.seed_records import PROGRAMME_TYPE
from app.models.core import Base

revision = "0021_programme"
down_revision = "0020_project_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    db = op.get_bind()
    Base.metadata.create_all(bind=db, tables=[Base.metadata.tables["programmes"]])
    op.execute("ALTER TABLE programmes ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY prg_record ON programmes FOR ALL USING (app_bypass() OR record_id IN (SELECT id FROM records)) "
               "WITH CHECK (app_bypass() OR record_id IN (SELECT id FROM records))")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON programmes TO verqac_app")
    code, prefix, ar, en, wcode, creator, responder, revisions, sort = PROGRAMME_TYPE
    op.execute("INSERT INTO record_types (code, prefix, name_ar, name_en, workflow_id, review_days, has_revisions, "
               "creator_party, responder_party, sort) "
               f"SELECT '{code}', '{prefix}', '{ar}', '{en}', id, 0, {revisions}, '{creator}', '{responder}', {sort} "
               f"FROM workflows WHERE org_id IS NULL AND code = '{wcode}'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS programmes")
    op.execute("DELETE FROM records WHERE record_type_id IN (SELECT id FROM record_types WHERE org_id IS NULL AND code = 'programme')")
    op.execute("DELETE FROM numbering_counters WHERE record_type_id IN (SELECT id FROM record_types WHERE org_id IS NULL AND code = 'programme')")
    op.execute("DELETE FROM record_types WHERE org_id IS NULL AND code = 'programme'")
