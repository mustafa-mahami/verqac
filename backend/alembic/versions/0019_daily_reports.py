"""Daily reports and progress: workflow, record type, daily_reports, progress_cells, progress_snapshots.

Revision ID: 0019_daily_reports
Revises: 0018_lab_tests
"""
from alembic import op

import app.models.daily  # noqa: F401 - registers the tables
from app.core.seed_records import DAILY_STATES, DAILY_TRANSITIONS, DAILY_TYPE
from app.models.core import Base

revision = "0019_daily_reports"
down_revision = "0018_lab_tests"
branch_labels = None
depends_on = None


def _q(s: str) -> str:
    return s.replace("'", "''")


def upgrade() -> None:
    db = op.get_bind()
    Base.metadata.create_all(bind=db, tables=[Base.metadata.tables[t] for t in ("daily_reports", "progress_cells", "progress_snapshots")])
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS progress_cells_uniq ON progress_cells "
               "(project_id, stage_id, COALESCE(location_id, '00000000-0000-0000-0000-000000000000'::uuid))")
    op.execute("ALTER TABLE daily_reports ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY dr_record ON daily_reports FOR ALL USING (app_bypass() OR record_id IN (SELECT id FROM records)) "
               "WITH CHECK (app_bypass() OR record_id IN (SELECT id FROM records))")
    for t in ("progress_cells", "progress_snapshots"):
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {t}_project ON {t} FOR ALL USING (app_bypass() OR project_id IN (SELECT my_project_ids())) "
                   "WITH CHECK (app_bypass() OR project_id IN (SELECT my_project_ids()))")
    for t in ("daily_reports", "progress_cells", "progress_snapshots"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO verqac_app")

    op.execute("INSERT INTO workflows (code, name_ar, name_en) VALUES ('daily_report', 'تقرير يومي', 'Daily report')")
    wf = "(SELECT id FROM workflows WHERE org_id IS NULL AND code = 'daily_report')"
    for i, (sc, ar, en, cat, color, initial) in enumerate(DAILY_STATES):
        op.execute("INSERT INTO workflow_states (workflow_id, code, name_ar, name_en, category, color, is_initial, sort) "
                   f"VALUES ({wf}, '{sc}', '{_q(ar)}', '{_q(en)}', '{cat}', '{color}', {initial}, {(i + 1) * 10})")
    st = "(SELECT id FROM workflow_states WHERE workflow_id = {wf} AND code = '{c}')"
    for i, (frm, to, action, ar, en, perm, effect, comment, style) in enumerate(DAILY_TRANSITIONS):
        op.execute("INSERT INTO workflow_transitions (workflow_id, from_state_id, to_state_id, action, name_ar, name_en, "
                   "permission, effect, requires_comment, style, sort) VALUES "
                   f"({wf}, {st.format(wf=wf, c=frm)}, {st.format(wf=wf, c=to)}, '{action}', '{_q(ar)}', '{_q(en)}', "
                   f"'{perm}', '{effect}', {comment}, '{style}', {(i + 1) * 10})")
    code, prefix, ar, en, wcode, creator, responder, revisions, sort = DAILY_TYPE
    op.execute("INSERT INTO record_types (code, prefix, name_ar, name_en, workflow_id, review_days, has_revisions, "
               "creator_party, responder_party, sort) "
               f"SELECT '{code}', '{prefix}', '{_q(ar)}', '{_q(en)}', id, 0, {revisions}, '{creator}', '{responder}', {sort} "
               f"FROM workflows WHERE org_id IS NULL AND code = '{wcode}'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS progress_snapshots")
    op.execute("DROP TABLE IF EXISTS progress_cells")
    op.execute("DROP TABLE IF EXISTS daily_reports")
    op.execute("DELETE FROM numbering_counters WHERE record_type_id IN (SELECT id FROM record_types WHERE org_id IS NULL AND code = 'daily_report')")
    op.execute("DELETE FROM record_types WHERE org_id IS NULL AND code = 'daily_report'")
    op.execute("DELETE FROM workflow_transitions WHERE workflow_id IN (SELECT id FROM workflows WHERE code = 'daily_report')")
    op.execute("DELETE FROM workflow_states WHERE workflow_id IN (SELECT id FROM workflows WHERE code = 'daily_report')")
    op.execute("DELETE FROM workflows WHERE org_id IS NULL AND code = 'daily_report'")
