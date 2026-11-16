"""Record engine: workflows, record types, records, history, comments, files; the submittal type.

Revision ID: 0003_records
Revises: 0002_invitation_org_role
"""
from alembic import op

from app.core.seed_records import RECORD_TYPES, REVIEW_STATES, REVIEW_TRANSITIONS
from app.models.core import Base
from app.models.records import RECORD_TABLES

revision = "0003_records"
down_revision = "0002_invitation_org_role"
branch_labels = None
depends_on = None

APP_ROLE = "verqac_app"

SQL = """
-- unique number + revision inside a project and record type, ignoring case, edge spaces and cancelled records
CREATE UNIQUE INDEX records_number_rev_uniq ON records
  (project_id, record_type_id, upper(btrim(number)), rev_no) WHERE state_category <> 'cancelled';
CREATE UNIQUE INDEX records_group_rev_uniq ON records (revision_group_id, rev_no);

-- parties the user acts for: active memberships, plus parties of organizations the user administers
CREATE OR REPLACE FUNCTION my_party_ids() RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = public AS
$$
  SELECT party_id FROM project_members WHERE user_id = app_user_id() AND is_active
  UNION
  SELECT id FROM project_parties WHERE status = 'active' AND org_id IN (SELECT my_admin_org_ids())
$$;

-- configuration tables: readable by everyone signed in, written only by migrations for now
ALTER TABLE workflows ENABLE ROW LEVEL SECURITY;
CREATE POLICY wf_select ON workflows FOR SELECT USING (true);
ALTER TABLE workflow_states ENABLE ROW LEVEL SECURITY;
CREATE POLICY wfs_select ON workflow_states FOR SELECT USING (true);
ALTER TABLE workflow_transitions ENABLE ROW LEVEL SECURITY;
CREATE POLICY wft_select ON workflow_transitions FOR SELECT USING (true);
ALTER TABLE record_types ENABLE ROW LEVEL SECURITY;
CREATE POLICY rt_select ON record_types FOR SELECT USING (true);

-- a draft is visible only to the party that wrote it (design doc section 2)
ALTER TABLE records ENABLE ROW LEVEL SECURITY;
CREATE POLICY rec_select ON records FOR SELECT USING (
  app_bypass() OR (project_id IN (SELECT my_project_ids())
                   AND (state_category <> 'draft' OR from_party_id IN (SELECT my_party_ids()))));
CREATE POLICY rec_insert ON records FOR INSERT WITH CHECK (
  app_bypass() OR (project_id IN (SELECT my_project_ids()) AND from_party_id IN (SELECT my_party_ids())));
CREATE POLICY rec_update ON records FOR UPDATE USING (
  app_bypass() OR (project_id IN (SELECT my_project_ids())
                   AND (state_category <> 'draft' OR from_party_id IN (SELECT my_party_ids()))));

-- children follow their record (the subquery is itself filtered by the records policy)
ALTER TABLE submittal_details ENABLE ROW LEVEL SECURITY;
CREATE POLICY sd_all ON submittal_details FOR ALL
  USING (app_bypass() OR record_id IN (SELECT id FROM records))
  WITH CHECK (app_bypass() OR record_id IN (SELECT id FROM records));
ALTER TABLE record_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY re_select ON record_events FOR SELECT USING (app_bypass() OR record_id IN (SELECT id FROM records));
CREATE POLICY re_insert ON record_events FOR INSERT WITH CHECK (app_bypass() OR record_id IN (SELECT id FROM records));
ALTER TABLE attachments ENABLE ROW LEVEL SECURITY;
CREATE POLICY att_all ON attachments FOR ALL
  USING (app_bypass() OR record_id IN (SELECT id FROM records))
  WITH CHECK (app_bypass() OR record_id IN (SELECT id FROM records));

-- internal comments stay inside the author's party
ALTER TABLE record_comments ENABLE ROW LEVEL SECURITY;
CREATE POLICY rc_select ON record_comments FOR SELECT USING (
  app_bypass() OR (record_id IN (SELECT id FROM records)
                   AND (visibility = 'shared' OR party_id IN (SELECT my_party_ids()))));
CREATE POLICY rc_insert ON record_comments FOR INSERT WITH CHECK (
  app_bypass() OR (record_id IN (SELECT id FROM records) AND party_id IN (SELECT my_party_ids())));

ALTER TABLE files ENABLE ROW LEVEL SECURITY;
CREATE POLICY files_all ON files FOR ALL
  USING (app_bypass() OR project_id IN (SELECT my_project_ids()))
  WITH CHECK (app_bypass() OR project_id IN (SELECT my_project_ids()));

ALTER TABLE numbering_counters ENABLE ROW LEVEL SECURITY;
CREATE POLICY nc_all ON numbering_counters FOR ALL
  USING (app_bypass() OR project_id IN (SELECT my_project_ids()))
  WITH CHECK (app_bypass() OR project_id IN (SELECT my_project_ids()));
"""


def _q(s: str) -> str:
    return s.replace("'", "''")


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables[t] for t in RECORD_TABLES])
    op.execute(SQL)

    for t in ("workflows", "workflow_states", "workflow_transitions", "record_types"):
        op.execute(f"GRANT SELECT ON {t} TO {APP_ROLE}")
    for t in ("records", "submittal_details", "numbering_counters", "attachments", "files"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO {APP_ROLE}")
    # history and comments are append-only for the application
    for t in ("record_events", "record_comments"):
        op.execute(f"GRANT SELECT, INSERT ON {t} TO {APP_ROLE}")
    op.execute(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT EXECUTE ON FUNCTION my_party_ids() TO {APP_ROLE}")

    op.execute("INSERT INTO workflows (code, name_ar, name_en) VALUES ('review', 'مراجعة واعتماد', 'Review and approval')")
    wf = "(SELECT id FROM workflows WHERE org_id IS NULL AND code = 'review')"
    for i, (code, ar, en, cat, color, initial) in enumerate(REVIEW_STATES):
        op.execute("INSERT INTO workflow_states (workflow_id, code, name_ar, name_en, category, color, is_initial, sort) "
                   f"VALUES ({wf}, '{code}', '{_q(ar)}', '{_q(en)}', '{cat}', '{color}', {initial}, {(i + 1) * 10})")
    for i, (frm, to, action, ar, en, perm, effect, comment, style) in enumerate(REVIEW_TRANSITIONS):
        st = "(SELECT id FROM workflow_states WHERE workflow_id = {wf} AND code = '{c}')"
        op.execute(
            "INSERT INTO workflow_transitions (workflow_id, from_state_id, to_state_id, action, name_ar, name_en, "
            "permission, effect, requires_comment, style, sort) VALUES "
            f"({wf}, {st.format(wf=wf, c=frm)}, {st.format(wf=wf, c=to)}, '{action}', '{_q(ar)}', '{_q(en)}', "
            f"'{perm}', '{effect}', {comment}, '{style}', {(i + 1) * 10})"
        )
    for code, prefix, ar, en, wcode, days, sort in RECORD_TYPES:
        op.execute("INSERT INTO record_types (code, prefix, name_ar, name_en, workflow_id, review_days, sort) "
                   f"SELECT '{code}', '{prefix}', '{_q(ar)}', '{_q(en)}', id, {days}, {sort} FROM workflows "
                   f"WHERE org_id IS NULL AND code = '{wcode}'")


def downgrade() -> None:
    for t in reversed(RECORD_TABLES):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS my_party_ids()")
