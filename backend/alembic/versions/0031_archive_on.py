"""The archive (documents register) is on in every project that chose its record types before it existed.

Revision ID: 0031_archive_on
Revises: 0030_events_delete
"""
from alembic import op

revision = "0031_archive_on"
down_revision = "0030_events_delete"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE projects SET settings = jsonb_set(settings, '{types}', (settings->'types') || '["document"]'::jsonb)
        WHERE jsonb_typeof(settings->'types') = 'array' AND NOT (settings->'types') ? 'document'
    """)


def downgrade() -> None:
    pass
