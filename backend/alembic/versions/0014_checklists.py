"""Inspection checklists: per topic (templates and projects) and per inspection request.

Existing templates and project topics that match a default topic get its checklist.

Revision ID: 0014_checklists
Revises: 0013_inspections
"""
import json

import sqlalchemy as sa
from alembic import op

from app.core.seed_structure import checklist_for

revision = "0014_checklists"
down_revision = "0013_inspections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE project_stage_topics ADD COLUMN IF NOT EXISTS checklist jsonb NOT NULL DEFAULT '[]'")
    op.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS checklist jsonb")
    db = op.get_bind()
    for tid, name in db.execute(sa.text("SELECT id, name_en FROM project_stage_topics WHERE checklist = '[]'")):
        if items := checklist_for(name):
            db.execute(sa.text("UPDATE project_stage_topics SET checklist = CAST(:c AS jsonb) WHERE id = :i"),
                       {"c": json.dumps(items, ensure_ascii=False), "i": tid})
    for pid, stages in db.execute(sa.text("SELECT id, stages FROM project_types")):
        changed = False
        for s in stages or []:
            for tp in s.get("topics", []):
                if "checklist" not in tp:
                    tp["checklist"] = checklist_for(tp.get("name_en", ""))
                    changed = True
        if changed:
            db.execute(sa.text("UPDATE project_types SET stages = CAST(:s AS jsonb) WHERE id = :i"),
                       {"s": json.dumps(stages, ensure_ascii=False), "i": pid})


def downgrade() -> None:
    op.execute("ALTER TABLE records DROP COLUMN IF EXISTS checklist")
    op.execute("ALTER TABLE project_stage_topics DROP COLUMN IF EXISTS checklist")
