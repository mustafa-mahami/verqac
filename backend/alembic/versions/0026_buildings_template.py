"""The organizations' "Buildings" template gets the current default stages (19: excavation and foundations as
whole-project stages, revised weights) where it has only stages of the earlier default (a template with stages
the organization added itself is left alone). Projects keep their own stages.

Revision ID: 0026_buildings_template
Revises: 0025_signed_copy
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0026_buildings_template"
down_revision = "0025_signed_copy"
branch_labels = None
depends_on = None

OLD = ["Structure", "Block walls", "MEP first fix", "Plaster", "Insulation", "Tiles", "False ceiling / Gypsum",
       "Aluminum & Steel works", "Doors", "Paint", "MEP second / final fix", "Facade stone cladding",
       "Curtain wall & Alucobond", "Elevator", "Site & external works", "Fit-out (counters, partitions, joinery)",
       "Staircases (finishes)"]


def upgrade() -> None:
    from app.core.seed_structure import PROJECT_TYPES, topics_for
    _code, _ar, _en, _g, _u, stages, _units = next(t for t in PROJECT_TYPES if t[0] == "buildings")
    new = [{"name_ar": a, "name_en": e, "scope": sc, "weight": w, "topics": topics_for(e)} for a, e, sc, w in stages]
    db = op.get_bind()
    for tid, cur in db.execute(sa.text("SELECT id, stages FROM project_types WHERE code = 'buildings'")).all():
        cur = cur if isinstance(cur, list) else json.loads(cur or "[]")
        names = [s.get("name_en") for s in cur]
        if not names or not set(names) <= set(OLD):
            continue  # stages of its own: the organization made this template, it stays
        # keep the topics (and checklists) the organization has under the stages it had
        old_topics = {s["name_en"]: s.get("topics") for s in cur}
        rows = [{**s, "topics": old_topics.get(s["name_en"]) or s["topics"]} for s in new]
        db.execute(sa.text("UPDATE project_types SET stages = CAST(:s AS jsonb) WHERE id = :id"),
                   {"s": json.dumps(rows, ensure_ascii=False), "id": tid})


def downgrade() -> None:
    pass
