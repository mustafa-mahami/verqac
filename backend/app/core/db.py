"""Database engine and per-request sessions.

Every request runs in one transaction. Before any query, the request sets two
transaction-local settings that the Row-Level Security policies read:

    app.user_id  the signed-in user (empty for anonymous endpoints)
    app.bypass   'on' only for the few system paths that must work before a
                 user is known (login, sign-up, refresh, invitation lookup)

RLS is a second line of defence: services still check permissions themselves.
"""
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def set_context(session: Session, user_id: UUID | None = None, bypass: bool = False) -> None:
    session.execute(
        text("SELECT set_config('app.user_id', :uid, true), set_config('app.bypass', :bp, true)"),
        {"uid": str(user_id) if user_id else "", "bp": "on" if bypass else "off"},
    )


@contextmanager
def session_scope(user_id: UUID | None = None, bypass: bool = False) -> Iterator[Session]:
    session = SessionLocal()
    try:
        with session.begin():
            set_context(session, user_id, bypass)
            yield session
    finally:
        session.close()
