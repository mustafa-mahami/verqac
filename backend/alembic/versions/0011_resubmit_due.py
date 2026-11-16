"""Resubmission period: when an answer asks for a new revision, the author has a deadline for it.

Revision ID: 0011_resubmit_due
Revises: 0010_password_resets
"""
from alembic import op

revision = "0011_resubmit_due"
down_revision = "0010_password_resets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS resubmit_due_at timestamptz")
    op.execute("ALTER TABLE records ADD COLUMN IF NOT EXISTS resubmitted_at timestamptz")
    # answers given before this change: the next revision, if submitted, already closed them
    op.execute("""
        UPDATE records r SET resubmitted_at = n.submitted_at
        FROM records n
        WHERE n.revision_group_id = r.revision_group_id AND n.rev_no = r.rev_no + 1 AND n.submitted_at IS NOT NULL
          AND r.state_category IN ('revise_and_resubmit', 'rejected')
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE records DROP COLUMN IF EXISTS resubmitted_at")
    op.execute("ALTER TABLE records DROP COLUMN IF EXISTS resubmit_due_at")
