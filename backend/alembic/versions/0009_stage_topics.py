"""Subjects (topics) under each project stage; records point at one. Existing templates and project stages
named like the default building stages receive the default subjects.

Revision ID: 0009_stage_topics
Revises: 0008_project_structure
"""
from alembic import op
from sqlalchemy import text

from app.core.seed_structure import topics_for
from app.models.core import Base
from app.models.structure import TOPIC_TABLES

revision = "0009_stage_topics"
down_revision = "0008_project_structure"
branch_labels = None
depends_on = None

APP_ROLE = "verqac_app"

SQL = """
ALTER TABLE records ADD COLUMN IF NOT EXISTS topic_id uuid;
ALTER TABLE records ADD CONSTRAINT records_topic_fk FOREIGN KEY (topic_id) REFERENCES project_stage_topics(id);
ALTER TABLE project_stage_topics ENABLE ROW LEVEL SECURITY;
CREATE POLICY pst_all ON project_stage_topics FOR ALL
  USING (app_bypass() OR project_id IN (SELECT my_project_ids()))
  WITH CHECK (app_bypass() OR project_id IN (SELECT my_project_ids()));
"""


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, tables=[Base.metadata.tables[t] for t in TOPIC_TABLES])
    op.execute(SQL)
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON project_stage_topics TO {APP_ROLE}")
    import json
    for tid, stages in bind.execute(text("SELECT id, stages FROM project_types")).all():
        changed = False
        for s in stages:
            if not s.get("topics"):
                s["topics"] = topics_for(s.get("name_en", ""))
                changed = changed or bool(s["topics"])
        if changed:
            bind.execute(text("UPDATE project_types SET stages = CAST(:s AS jsonb) WHERE id = :i"),
                         {"s": json.dumps(stages, ensure_ascii=False), "i": tid})
    for sid, pid, name_en in bind.execute(text("SELECT id, project_id, name_en FROM project_stages")).all():
        for i, t in enumerate(topics_for(name_en)):
            bind.execute(text("INSERT INTO project_stage_topics (project_id, stage_id, name_ar, name_en, sort) "
                              "VALUES (:p, :s, :a, :e, :o)"),
                         {"p": pid, "s": sid, "a": t["name_ar"], "e": t["name_en"], "o": (i + 1) * 10})


def downgrade() -> None:
    op.execute("ALTER TABLE records DROP CONSTRAINT IF EXISTS records_topic_fk")
    op.execute("ALTER TABLE records DROP COLUMN IF EXISTS topic_id")
    op.execute("DROP TABLE IF EXISTS project_stage_topics CASCADE")
