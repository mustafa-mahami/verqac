"""Laboratory tests: templates (per organization), concrete classes (per project), results (per test record),
the "test" record type and its workflow.

Revision ID: 0018_lab_tests
Revises: 0017_more_types
"""
import json

import sqlalchemy as sa
from alembic import op

import app.models.lab  # noqa: F401 - registers the tables
from app.core.lab import default_templates
from app.core.seed_records import TEST_STATES, TEST_TRANSITIONS, TEST_TYPE
from app.models.core import Base

revision = "0018_lab_tests"
down_revision = "0017_more_types"
branch_labels = None
depends_on = None


def _q(s: str) -> str:
    return s.replace("'", "''")


def upgrade() -> None:
    db = op.get_bind()
    Base.metadata.create_all(bind=db, tables=[Base.metadata.tables[t] for t in ("lab_templates", "concrete_classes", "lab_results")])
    op.execute("ALTER TABLE lab_templates ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY lt_org ON lab_templates FOR ALL USING (app_bypass() OR org_id IN (SELECT my_org_ids())) "
               "WITH CHECK (app_bypass() OR org_id IN (SELECT my_admin_org_ids()))")
    op.execute("ALTER TABLE concrete_classes ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY cc_project ON concrete_classes FOR ALL USING (app_bypass() OR project_id IN (SELECT my_project_ids())) "
               "WITH CHECK (app_bypass() OR project_id IN (SELECT my_project_ids()))")
    op.execute("ALTER TABLE lab_results ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY lr_record ON lab_results FOR ALL USING (app_bypass() OR record_id IN (SELECT id FROM records)) "
               "WITH CHECK (app_bypass() OR record_id IN (SELECT id FROM records))")
    for t in ("lab_templates", "concrete_classes", "lab_results"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO verqac_app")

    # workflow and record type
    op.execute("INSERT INTO workflows (code, name_ar, name_en) VALUES ('lab_test', 'فحص مخبري', 'Laboratory test')")
    wf = "(SELECT id FROM workflows WHERE org_id IS NULL AND code = 'lab_test')"
    for i, (sc, ar, en, cat, color, initial) in enumerate(TEST_STATES):
        op.execute("INSERT INTO workflow_states (workflow_id, code, name_ar, name_en, category, color, is_initial, sort) "
                   f"VALUES ({wf}, '{sc}', '{_q(ar)}', '{_q(en)}', '{cat}', '{color}', {initial}, {(i + 1) * 10})")
    st = "(SELECT id FROM workflow_states WHERE workflow_id = {wf} AND code = '{c}')"
    for i, (frm, to, action, ar, en, perm, effect, comment, style) in enumerate(TEST_TRANSITIONS):
        op.execute("INSERT INTO workflow_transitions (workflow_id, from_state_id, to_state_id, action, name_ar, name_en, "
                   "permission, effect, requires_comment, style, sort) VALUES "
                   f"({wf}, {st.format(wf=wf, c=frm)}, {st.format(wf=wf, c=to)}, '{action}', '{_q(ar)}', '{_q(en)}', "
                   f"'{perm}', '{effect}', {comment}, '{style}', {(i + 1) * 10})")
    code, prefix, ar, en, wcode, creator, responder, revisions, sort = TEST_TYPE
    op.execute("INSERT INTO record_types (code, prefix, name_ar, name_en, workflow_id, review_days, has_revisions, "
               "creator_party, responder_party, sort) "
               f"SELECT '{code}', '{prefix}', '{_q(ar)}', '{_q(en)}', id, 0, {revisions}, '{creator}', '{responder}', {sort} "
               f"FROM workflows WHERE org_id IS NULL AND code = '{wcode}'")

    # default templates for every organization
    tpl = default_templates()
    for (org_id,) in db.execute(sa.text("SELECT id FROM organizations")):
        for i, t in enumerate(tpl):
            db.execute(sa.text("INSERT INTO lab_templates (id, org_id, code, name_ar, name_en, material, standard, acceptance, "
                               "samples, lines, sort) VALUES (gen_random_uuid(), :o, :code, :ar, :en, :m, :std, :acc, :smp, "
                               "CAST(:lines AS jsonb), :sort)"),
                       {"o": org_id, "code": t["code"], "ar": t["name_ar"], "en": t["name_en"], "m": t["material"],
                        "std": t["standard"], "acc": t["acceptance"], "smp": t["samples"] or None,
                        "lines": json.dumps(t["lines"], ensure_ascii=False), "sort": (i + 1) * 10})


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lab_results")
    op.execute("DROP TABLE IF EXISTS concrete_classes")
    op.execute("DROP TABLE IF EXISTS lab_templates")
    op.execute("DELETE FROM numbering_counters WHERE record_type_id IN (SELECT id FROM record_types WHERE org_id IS NULL AND code IN ('test'))")
    op.execute("DELETE FROM record_types WHERE org_id IS NULL AND code = 'test'")
    op.execute("DELETE FROM workflow_transitions WHERE workflow_id IN (SELECT id FROM workflows WHERE code = 'lab_test')")
    op.execute("DELETE FROM workflow_states WHERE workflow_id IN (SELECT id FROM workflows WHERE code = 'lab_test')")
    op.execute("DELETE FROM workflows WHERE org_id IS NULL AND code = 'lab_test'")
