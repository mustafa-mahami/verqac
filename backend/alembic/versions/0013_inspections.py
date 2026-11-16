"""Inspection requests: workflow, record type, and the record columns they use.

Revision ID: 0013_inspections
Revises: 0012_push_subscriptions
"""
from alembic import op

from app.core.seed_records import INSPECTION_STATES, INSPECTION_TRANSITIONS, INSPECTION_TYPE

revision = "0013_inspections"
down_revision = "0012_push_subscriptions"
branch_labels = None
depends_on = None


def _q(s: str) -> str:
    return s.replace("'", "''")


def upgrade() -> None:
    op.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS requested_for timestamptz")
    op.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS performed_at timestamptz")
    op.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS linked_ids uuid[]")
    op.execute("INSERT INTO workflows (code, name_ar, name_en) VALUES ('inspection', 'فحص ميداني', 'Site inspection')")
    wf = "(SELECT id FROM workflows WHERE org_id IS NULL AND code = 'inspection')"
    for i, (code, ar, en, cat, color, initial) in enumerate(INSPECTION_STATES):
        op.execute("INSERT INTO workflow_states (workflow_id, code, name_ar, name_en, category, color, is_initial, sort) "
                   f"VALUES ({wf}, '{code}', '{_q(ar)}', '{_q(en)}', '{cat}', '{color}', {initial}, {(i + 1) * 10})")
    st = "(SELECT id FROM workflow_states WHERE workflow_id = {wf} AND code = '{c}')"
    for i, (frm, to, action, ar, en, perm, effect, comment, style) in enumerate(INSPECTION_TRANSITIONS):
        op.execute(
            "INSERT INTO workflow_transitions (workflow_id, from_state_id, to_state_id, action, name_ar, name_en, "
            "permission, effect, requires_comment, style, sort) VALUES "
            f"({wf}, {st.format(wf=wf, c=frm)}, {st.format(wf=wf, c=to)}, '{action}', '{_q(ar)}', '{_q(en)}', "
            f"'{perm}', '{effect}', {comment}, '{style}', {(i + 1) * 10})")
    code, prefix, ar, en, wcode, days, sort = INSPECTION_TYPE
    op.execute("INSERT INTO record_types (code, prefix, name_ar, name_en, workflow_id, review_days, sort) "
               f"SELECT '{code}', '{prefix}', '{_q(ar)}', '{_q(en)}', id, {days}, {sort} FROM workflows "
               f"WHERE org_id IS NULL AND code = '{wcode}'")


def downgrade() -> None:
    op.execute("DELETE FROM record_types WHERE org_id IS NULL AND code = 'inspection'")
    op.execute("DELETE FROM workflow_transitions WHERE workflow_id IN (SELECT id FROM workflows WHERE code = 'inspection')")
    op.execute("DELETE FROM workflow_states WHERE workflow_id IN (SELECT id FROM workflows WHERE code = 'inspection')")
    op.execute("DELETE FROM workflows WHERE org_id IS NULL AND code = 'inspection'")
    op.execute("ALTER TABLE records DROP COLUMN IF EXISTS linked_ids, DROP COLUMN IF EXISTS performed_at, "
               "DROP COLUMN IF EXISTS requested_for")
