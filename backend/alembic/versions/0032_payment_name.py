"""A payment application is called a financial claim (مطالبة مالية), apart from the money received against it.

Revision ID: 0032_payment_name
Revises: 0031_archive_on
"""
from alembic import op

revision = "0032_payment_name"
down_revision = "0031_archive_on"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE record_types SET name_ar = 'مطالبة مالية' WHERE code = 'payment' AND org_id IS NULL AND name_ar = 'دفعة'")
    op.execute("UPDATE workflows SET name_ar = 'مطالبة مالية' WHERE code = 'payment' AND name_ar = 'دفعة'")
    op.execute("UPDATE workflow_transitions SET name_ar = 'اعتماد المطالبة' WHERE action = 'certify' AND name_ar = 'اعتماد الدفعة'")


def downgrade() -> None:
    op.execute("UPDATE record_types SET name_ar = 'دفعة' WHERE code = 'payment' AND org_id IS NULL AND name_ar = 'مطالبة مالية'")
