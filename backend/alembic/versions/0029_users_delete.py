"""System jobs only: removing a test account, and moving the history of an imported placeholder account to the real
person's account (who did it, nothing else, may be changed in the append-only history).

Revision ID: 0029_users_delete
Revises: 0028_archive
"""
from alembic import op

revision = "0029_users_delete"
down_revision = "0028_archive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS users_system_delete ON users")
    op.execute("CREATE POLICY users_system_delete ON users FOR DELETE USING (app_bypass())")
    for table, cols, pol in (("record_events", "actor_id, on_behalf_of", "re_system_update"),
                             ("record_comments", "author_id", "rc_system_update")):
        op.execute(f"GRANT UPDATE ({cols}) ON {table} TO verqac_app")
        op.execute(f"DROP POLICY IF EXISTS {pol} ON {table}")
        op.execute(f"CREATE POLICY {pol} ON {table} FOR UPDATE USING (app_bypass()) WITH CHECK (app_bypass())")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS users_system_delete ON users")
    for table, cols, pol in (("record_events", "actor_id, on_behalf_of", "re_system_update"),
                             ("record_comments", "author_id", "rc_system_update")):
        op.execute(f"DROP POLICY IF EXISTS {pol} ON {table}")
        op.execute(f"REVOKE UPDATE ({cols}) ON {table} FROM verqac_app")
