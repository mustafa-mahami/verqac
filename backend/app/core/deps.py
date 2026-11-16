import ipaddress
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, set_context
from app.core.security import decode_access_token
from app.models.core import OrgMember, User

_bearer = HTTPBearer(auto_error=False)


@dataclass
class RequestMeta:
    ip: str | None
    user_agent: str | None


def request_meta(request: Request) -> RequestMeta:
    ua = request.headers.get("user-agent")
    # behind Nginx the client address comes in X-Real-IP
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else None)
    try:
        ip = str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        ip = None
    return RequestMeta(ip=ip, user_agent=ua[:300] if ua else None)


def system_db() -> Iterator[Session]:
    """Session for the few anonymous system paths (sign-up, login, refresh).

    Always use with Depends(..., scope="function"): the transaction must commit before
    the response is sent, or a fast client can call the next endpoint before its data exists.
    """
    session = SessionLocal()
    try:
        with session.begin():
            set_context(session, None, bypass=True)
            yield session
    finally:
        session.close()


@dataclass
class Ctx:
    db: Session
    user: User
    meta: RequestMeta


def _user_id(creds: HTTPAuthorizationCredentials | None) -> UUID:
    uid = decode_access_token(creds.credentials) if creds else None
    if uid is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    return uid


def user_db(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> Iterator[tuple[Session, UUID]]:
    uid = _user_id(creds)
    session = SessionLocal()
    try:
        with session.begin():
            set_context(session, uid)
            yield session, uid
    finally:
        session.close()


def ctx(dbu: tuple[Session, UUID] = Depends(user_db, scope="function"), meta: RequestMeta = Depends(request_meta)) -> Ctx:
    db, uid = dbu
    user = db.scalar(select(User).where(User.id == uid))
    if user is None or not user.is_active or not has_active_membership(db, uid):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    return Ctx(db=db, user=user, meta=meta)


def has_active_membership(db: Session, user_id: UUID) -> bool:
    """A person suspended by every organization they belong to cannot use the platform."""
    return bool(db.scalar(select(OrgMember.id).where(OrgMember.user_id == user_id, OrgMember.is_active).limit(1)))
