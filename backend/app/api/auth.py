from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.audit import audit
from app.core.config import get_settings
from app.core.db import session_scope
from app.core.deps import Ctx, RequestMeta, ctx, request_meta, system_db
from app.core.security import create_access_token, hash_password, hash_token, new_opaque_token, verify_password
from app.core.seed import DEFAULT_DISCIPLINES
from app.models.core import Discipline, Organization, OrgMember, RefreshToken, User
from app.schemas.core import LoginIn, MembershipOut, MeOut, OrgOut, RegisterOrgIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])

# Same answer for "no such user" and "wrong password", so the API does not reveal who is registered.
INVALID = "invalid_credentials"


def _issue(db: Session, user: User, response: Response, meta: RequestMeta) -> TokenOut:
    s = get_settings()
    token, token_hash = new_opaque_token()
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=s.refresh_token_days),
        user_agent=meta.user_agent,
    ))
    response.set_cookie(
        s.refresh_cookie_name, token,
        max_age=s.refresh_token_days * 86400, httponly=True, secure=s.cookie_secure,
        samesite="strict", path="/api/v1/auth",
    )
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/register-org", response_model=TokenOut, status_code=201)
def register_org(body: RegisterOrgIn, response: Response, db: Session = Depends(system_db),
                 meta: RequestMeta = Depends(request_meta)):
    """The organization admin registers the organization once, then adds the users."""
    email = body.email.lower()
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "email_taken")

    org = Organization(kind=body.org_kind, name_ar=body.org_name_ar, name_en=body.org_name_en,
                       default_locale=body.locale)
    user = User(email=email, password_hash=hash_password(body.password), full_name_ar=body.full_name_ar,
                full_name_en=body.full_name_en, locale=body.locale, last_login_at=datetime.now(UTC))
    db.add_all([org, user])
    db.flush()
    db.add(OrgMember(org_id=org.id, user_id=user.id, org_role="admin"))
    for i, (code, ar, en) in enumerate(DEFAULT_DISCIPLINES):
        db.add(Discipline(org_id=org.id, code=code, name_ar=ar, name_en=en, sort=(i + 1) * 10))
    audit(db, entity="organization", action="register", entity_id=org.id, actor=user.id, org_id=org.id,
          changes={"name_en": org.name_en, "kind": org.kind}, ip=meta.ip, user_agent=meta.user_agent)
    return _issue(db, user, response, meta)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, response: Response, db: Session = Depends(system_db),
          meta: RequestMeta = Depends(request_meta)):
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not verify_password(body.password, user.password_hash):
        # own transaction: the request transaction rolls back with the 401
        with session_scope(bypass=True) as side:
            audit(side, entity="user", action="login_failed", changes={"email": body.email.lower()},
                  ip=meta.ip, user_agent=meta.user_agent)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account_inactive")
    user.last_login_at = datetime.now(UTC)
    audit(db, entity="user", action="login", entity_id=user.id, actor=user.id, ip=meta.ip, user_agent=meta.user_agent)
    return _issue(db, user, response, meta)


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, db: Session = Depends(system_db),
            meta: RequestMeta = Depends(request_meta)):
    """Rotates the refresh token: the old one is revoked, a new one is set."""
    token = request.cookies.get(get_settings().refresh_cookie_name)
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(token))) if token else None
    now = datetime.now(UTC)
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        if row is not None and row.revoked_at is not None:
            # a revoked token used again = possible theft: revoke every session of that user,
            # in its own transaction so the 401 below does not roll it back
            with session_scope(bypass=True) as side:
                side.execute(update(RefreshToken).where(RefreshToken.user_id == row.user_id,
                                                        RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
                audit(side, entity="user", action="refresh_token_reuse", entity_id=row.user_id,
                      ip=meta.ip, user_agent=meta.user_agent)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not_authenticated")
    row.revoked_at = now
    return _issue(db, user, response, meta)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(system_db)):
    s = get_settings()
    token = request.cookies.get(s.refresh_cookie_name)
    if token:
        db.execute(update(RefreshToken).where(RefreshToken.token_hash == hash_token(token))
                   .values(revoked_at=datetime.now(UTC)))
    response.delete_cookie(s.refresh_cookie_name, path="/api/v1/auth")


@router.get("/me", response_model=MeOut)
def me(c: Ctx = Depends(ctx)):
    rows = c.db.execute(
        select(Organization, OrgMember.org_role).join(OrgMember, OrgMember.org_id == Organization.id)
        .where(OrgMember.user_id == c.user.id).order_by(Organization.name_en)
    ).all()
    return MeOut(user=UserOut.model_validate(c.user),
                 orgs=[MembershipOut(org=OrgOut.model_validate(o), org_role=r) for o, r in rows])
