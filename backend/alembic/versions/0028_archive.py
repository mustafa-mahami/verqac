"""The project archive (letters, minutes, tender and contract documents, reports): workflow, record type, and the
consultant roles' right to file documents.

Revision ID: 0028_archive
Revises: 0027_payments
"""
from alembic import op

from app.core.seed_records import ARCHIVE_STATES, ARCHIVE_TRANSITIONS, DOCUMENT_PERMS, DOCUMENT_TYPE

revision = "0028_archive"
down_revision = "0027_payments"
branch_labels = None
depends_on = None


def _q(s: str) -> str:
    return s.replace("'", "''")


def upgrade() -> None:
    op.execute("INSERT INTO workflows (code, name_ar, name_en) VALUES ('archive', 'أرشيف', 'Archive')")
    wf = "(SELECT id FROM workflows WHERE org_id IS NULL AND code = 'archive')"
    for i, (sc, sar, sen, cat, color, initial) in enumerate(ARCHIVE_STATES):
        op.execute("INSERT INTO workflow_states (workflow_id, code, name_ar, name_en, category, color, is_initial, sort) "
                   f"VALUES ({wf}, '{sc}', '{_q(sar)}', '{_q(sen)}', '{cat}', '{color}', {initial}, {(i + 1) * 10})")
    st = "(SELECT id FROM workflow_states WHERE workflow_id = {wf} AND code = '{c}')"
    for i, (frm, to, action, tar, ten, perm, effect, comment, style) in enumerate(ARCHIVE_TRANSITIONS):
        op.execute(
            "INSERT INTO workflow_transitions (workflow_id, from_state_id, to_state_id, action, name_ar, name_en, "
            "permission, effect, requires_comment, style, sort) VALUES "
            f"({wf}, {st.format(wf=wf, c=frm)}, {st.format(wf=wf, c=to)}, '{action}', '{_q(tar)}', '{_q(ten)}', "
            f"'{perm}', '{effect}', {comment}, '{style}', {(i + 1) * 10})")
    code, prefix, ar, en, wcode, creator, responder, revisions, sort = DOCUMENT_TYPE
    op.execute("INSERT INTO record_types (code, prefix, name_ar, name_en, workflow_id, review_days, has_revisions, "
               "creator_party, responder_party, sort) "
               f"SELECT '{code}', '{prefix}', '{_q(ar)}', '{_q(en)}', id, 0, {revisions}, '{creator}', '{responder}', {sort} "
               f"FROM workflows WHERE org_id IS NULL AND code = '{wcode}'")
    for role, actions, scope in DOCUMENT_PERMS:
        for action in actions:
            op.execute("INSERT INTO role_permissions (role_id, record_type, action, scope) "
                       f"SELECT id, 'document', '{action}', '{scope}' FROM roles r "
                       f"WHERE (r.code = '{role}' OR r.base_code = '{role}') "
                       "AND NOT EXISTS (SELECT 1 FROM role_permissions p WHERE p.role_id = r.id "
                       f"AND p.record_type = 'document' AND p.action = '{action}')")


def downgrade() -> None:
    op.execute("DELETE FROM role_permissions WHERE record_type = 'document'")
    op.execute("DELETE FROM records WHERE record_type_id IN (SELECT id FROM record_types WHERE org_id IS NULL AND code = 'document')")
    op.execute("DELETE FROM numbering_counters WHERE record_type_id IN (SELECT id FROM record_types WHERE org_id IS NULL AND code = 'document')")
    op.execute("DELETE FROM record_types WHERE org_id IS NULL AND code = 'document'")
    op.execute("DELETE FROM workflow_transitions WHERE workflow_id IN (SELECT id FROM workflows WHERE code = 'archive')")
    op.execute("DELETE FROM workflow_states WHERE workflow_id IN (SELECT id FROM workflows WHERE code = 'archive')")
    op.execute("DELETE FROM workflows WHERE org_id IS NULL AND code = 'archive'")
