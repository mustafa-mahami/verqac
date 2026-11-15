"""Invitations carry the organization role (admin or member).

Revision ID: 0002_invitation_org_role
Revises: 0001_core
"""
from alembic import op

revision = "0002_invitation_org_role"
down_revision = "0001_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE invitations ADD COLUMN IF NOT EXISTS org_role varchar(10)")
    op.execute("ALTER TABLE invitations ADD CONSTRAINT invitations_org_role_valid "
               "CHECK (org_role IS NULL OR org_role IN ('admin', 'member'))")


def downgrade() -> None:
    op.execute("ALTER TABLE invitations DROP COLUMN IF EXISTS org_role")
