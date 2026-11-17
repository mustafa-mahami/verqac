"""RFI, NCR and material inspection (MIR): workflows, record types and role permissions.

Adds the state category "responded" (answered, waiting for the issuer to verify: NCR).

Revision ID: 0017_more_types
Revises: 0016_org_settings
"""
from alembic import op

from app.core.seed_records import (MORE_TYPES, NCR_STATES, NCR_TRANSITIONS, RFI_STATES, RFI_TRANSITIONS)
from app.models.records import CATEGORIES

revision = "0017_more_types"
down_revision = "0016_org_settings"
branch_labels = None
depends_on = None

# role code, record type, actions, scope (platform roles; org copies of roles are not touched)
PERMS = [
    ("contractor_pm", "ncr", ("view", "respond", "export"), "project"),
    ("qa_engineer", "ncr", ("view", "respond", "export"), "disciplines"),
    ("site_engineer", "ncr", ("view", "respond"), "disciplines"),
    ("document_controller", "ncr", ("view", "respond", "export"), "project"),
    ("site_engineer", "material", ("view", "create", "edit", "submit"), "disciplines"),
]


def _q(s: str) -> str:
    return s.replace("'", "''")


def _workflow(code, ar, en, states, transitions):
    op.execute(f"INSERT INTO workflows (code, name_ar, name_en) VALUES ('{code}', '{_q(ar)}', '{_q(en)}')")
    wf = f"(SELECT id FROM workflows WHERE org_id IS NULL AND code = '{code}')"
    for i, (sc, sar, sen, cat, color, initial) in enumerate(states):
        op.execute("INSERT INTO workflow_states (workflow_id, code, name_ar, name_en, category, color, is_initial, sort) "
                   f"VALUES ({wf}, '{sc}', '{_q(sar)}', '{_q(sen)}', '{cat}', '{color}', {initial}, {(i + 1) * 10})")
    st = "(SELECT id FROM workflow_states WHERE workflow_id = {wf} AND code = '{c}')"
    for i, (frm, to, action, tar, ten, perm, effect, comment, style) in enumerate(transitions):
        op.execute(
            "INSERT INTO workflow_transitions (workflow_id, from_state_id, to_state_id, action, name_ar, name_en, "
            "permission, effect, requires_comment, style, sort) VALUES "
            f"({wf}, {st.format(wf=wf, c=frm)}, {st.format(wf=wf, c=to)}, '{action}', '{_q(tar)}', '{_q(ten)}', "
            f"'{perm}', '{effect}', {comment}, '{style}', {(i + 1) * 10})")


def upgrade() -> None:
    op.execute("ALTER TABLE workflow_states DROP CONSTRAINT IF EXISTS category_valid")
    op.execute(f"ALTER TABLE workflow_states ADD CONSTRAINT category_valid CHECK (category IN {CATEGORIES})")
    _workflow("rfi", "استيضاح", "Request for information", RFI_STATES, RFI_TRANSITIONS)
    _workflow("ncr", "عدم مطابقة", "Non-conformance", NCR_STATES, NCR_TRANSITIONS)
    for code, prefix, ar, en, wcode, creator, responder, revisions, sort in MORE_TYPES:
        op.execute("INSERT INTO record_types (code, prefix, name_ar, name_en, workflow_id, review_days, has_revisions, "
                   "creator_party, responder_party, sort) "
                   f"SELECT '{code}', '{prefix}', '{_q(ar)}', '{_q(en)}', id, 0, {revisions}, '{creator}', "
                   f"'{responder}', {sort} FROM workflows WHERE org_id IS NULL AND code = '{wcode}'")
    for role, rtype, actions, scope in PERMS:
        for action in actions:
            op.execute("INSERT INTO role_permissions (role_id, record_type, action, scope) "
                       f"SELECT id, '{rtype}', '{action}', '{scope}' FROM roles r WHERE org_id IS NULL AND code = '{role}' "
                       "AND NOT EXISTS (SELECT 1 FROM role_permissions p WHERE p.role_id = r.id "
                       f"AND p.record_type = '{rtype}' AND p.action = '{action}')")


def downgrade() -> None:
    op.execute("DELETE FROM numbering_counters WHERE record_type_id IN (SELECT id FROM record_types WHERE org_id IS NULL AND code IN ('material', 'rfi', 'ncr'))")
    op.execute("DELETE FROM record_types WHERE org_id IS NULL AND code IN ('material', 'rfi', 'ncr')")
    for code in ("rfi", "ncr"):
        op.execute(f"DELETE FROM workflow_transitions WHERE workflow_id IN (SELECT id FROM workflows WHERE code = '{code}')")
        op.execute(f"DELETE FROM workflow_states WHERE workflow_id IN (SELECT id FROM workflows WHERE code = '{code}')")
        op.execute(f"DELETE FROM workflows WHERE org_id IS NULL AND code = '{code}'")
