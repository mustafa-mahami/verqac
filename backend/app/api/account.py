"""The signed-in user's own account, and password reset links (self-service by e-mail, or made by an org admin)."""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.access import require
from app.core.audit import audit
from app.core.config import get_settings
from app.core.db import session_scope
from app.core.deps import Ctx, RequestMeta, ctx, request_meta, system_db
from app.core.mailer import mail_enabled, send_mail
from app.core.security import hash_password, hash_token, new_opaque_token, verify_password
from app.models.core import OrgMember, PasswordReset, RefreshToken, User
from app.schemas.core import UserOut

router = APIRouter(tags=["account"])
SELF_HOURS, ADMIN_HOURS = 1, 24


class AccountIn(BaseModel):
    full_name_ar: str = Field(min_length=2, max_length=200)
    full_name_en: str = Field(min_length=2, max_length=200)
    locale: Literal["ar", "en"] = "ar"


class PasswordChangeIn(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=10, max_length=128)


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    password: str = Field(min_length=10, max_length=128)


class ResetInfo(BaseModel):
    email: str


class ResetLinkOut(BaseModel):
    link: str
    expires_at: datetime
    emailed: bool


def _revoke_sessions(db: Session, user_id: uuid.UUID) -> None:
    db.execute(update(RefreshToken).where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
               .values(revoked_at=func.now()))


def _new_link(user_id: uuid.UUID, hours: int, created_by: uuid.UUID | None) -> tuple[str, datetime]:
    token, token_hash = new_opaque_token()
    expires = datetime.now(UTC) + timedelta(hours=hours)
    with session_scope(bypass=True) as db:
        # an older unused link stops working when a new one is made
        db.execute(update(PasswordReset).where(PasswordReset.user_id == user_id, PasswordReset.used_at.is_(None))
                   .values(used_at=func.now()))
        db.add(PasswordReset(user_id=user_id, token_hash=token_hash, expires_at=expires, created_by=created_by))
    return f"{get_settings().app_url.rstrip('/')}/reset/{token}", expires


def _mail(user: User, link: str, hours: int) -> None:
    ar = user.locale != "en"
    subject = "Verqac — تعيين كلمة سر جديدة" if ar else "Verqac — set a new password"
    text = (f"مرحباً {user.full_name_ar}،\n\nلتعيين كلمة سر جديدة لحسابك في Verqac افتح هذا الرابط خلال {hours} ساعة:\n{link}\n\n"
            "إذا لم تطلب ذلك فتجاهل هذه الرسالة؛ كلمة سرك الحالية لا تتغيّر.") if ar else (
            f"Hello {user.full_name_en},\n\nTo set a new password for your Verqac account, open this link within {hours} hour(s):\n"
            f"{link}\n\nIf you did not ask for this, ignore this message; your current password stays as it is.")
    send_mail(user.email, subject, text)


# ----------------------------------------------------------------------------- own account
@router.patch("/auth/me", response_model=UserOut)
def update_me(body: AccountIn, c: Ctx = Depends(ctx)):
    u = c.user
    before = {"full_name_ar": u.full_name_ar, "full_name_en": u.full_name_en, "locale": u.locale}
    u.full_name_ar, u.full_name_en, u.locale = body.full_name_ar.strip(), body.full_name_en.strip(), body.locale
    audit(c.db, entity="user", action="update", entity_id=u.id, actor=u.id,
          changes={k: [v, getattr(u, k)] for k, v in before.items() if v != getattr(u, k)},
          ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return UserOut.model_validate(u)


@router.post("/auth/password", status_code=204)
def change_password(body: PasswordChangeIn, c: Ctx = Depends(ctx)):
    """Change the password; other devices are signed out (this one keeps its session until it refreshes)."""
    if not verify_password(body.current_password, c.user.password_hash):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "wrong_password")
    c.user.password_hash = hash_password(body.new_password)
    with session_scope(bypass=True) as db:
        _revoke_sessions(db, c.user.id)
    audit(c.db, entity="user", action="password_change", entity_id=c.user.id, actor=c.user.id,
          ip=c.meta.ip, user_agent=c.meta.user_agent)


# ----------------------------------------------------------------------------- reset links
@router.post("/auth/forgot", status_code=202)
def forgot(body: ForgotIn, bg: BackgroundTasks, db: Session = Depends(system_db, scope="function")):
    """Always the same answer, so it does not reveal who has an account."""
    user = db.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is not None and mail_enabled():
        link, _ = _new_link(user.id, SELF_HOURS, None)
        bg.add_task(_mail, user, link, SELF_HOURS)
    return {"mail_enabled": mail_enabled()}


def _valid_reset(db: Session, token: str) -> PasswordReset:
    r = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == hash_token(token)))
    if r is None or r.used_at is not None or r.expires_at < datetime.now(UTC):
        raise HTTPException(status.HTTP_410_GONE, "reset_expired")
    return r


@router.get("/auth/reset/{token}", response_model=ResetInfo)
def reset_info(token: str, db: Session = Depends(system_db, scope="function")):
    r = _valid_reset(db, token)
    return ResetInfo(email=db.get(User, r.user_id).email)


@router.post("/auth/reset/{token}", status_code=204)
def reset(token: str, body: ResetIn, db: Session = Depends(system_db, scope="function"),
          meta: RequestMeta = Depends(request_meta)):
    r = _valid_reset(db, token)
    user = db.get(User, r.user_id)
    user.password_hash = hash_password(body.password)
    r.used_at = datetime.now(UTC)
    _revoke_sessions(db, user.id)
    audit(db, entity="user", action="password_reset", entity_id=user.id, actor=user.id,
          changes={"by_admin": str(r.created_by) if r.created_by else None}, ip=meta.ip, user_agent=meta.user_agent)


@router.post("/orgs/{org_id}/members/{user_id}/reset-link", response_model=ResetLinkOut)
def admin_reset_link(org_id: uuid.UUID, user_id: uuid.UUID, bg: BackgroundTasks, c: Ctx = Depends(ctx)):
    """An org admin makes a one-time link for a member of the organization (to send by WhatsApp, say)."""
    role = c.db.scalar(select(OrgMember.org_role).where(OrgMember.org_id == org_id, OrgMember.user_id == c.user.id,
                                                        OrgMember.is_active))
    require(role == "admin", "org_admin_required")
    require(c.db.scalar(select(OrgMember.id).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id))
            is not None, "not_a_member")
    user = c.db.get(User, user_id)
    link, expires = _new_link(user_id, ADMIN_HOURS, c.user.id)
    emailed = mail_enabled()
    if emailed:
        bg.add_task(_mail, user, link, ADMIN_HOURS)
    audit(c.db, entity="user", action="reset_link", entity_id=user_id, actor=c.user.id, org_id=org_id,
          ip=c.meta.ip, user_agent=c.meta.user_agent)
    return ResetLinkOut(link=link, expires_at=expires, emailed=emailed)
