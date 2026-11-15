"""Organization users: the admin invites colleagues; employees never self-register."""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select

from app.core.audit import audit
from app.core.deps import Ctx, ctx
from app.core.invites import create_invite
from app.models.core import Invitation, Organization, OrgMember, User
from app.schemas.core import InviteOut, OrgInviteIn, OrgMemberOut, PendingInvite, UserOut

router = APIRouter(prefix="/orgs/{org_id}", tags=["organization"])


def _membership(c: Ctx, org_id: UUID) -> OrgMember:
    m = c.db.scalar(select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == c.user.id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return m


@router.get("/members", response_model=list[OrgMemberOut])
def list_members(org_id: UUID, c: Ctx = Depends(ctx)):
    _membership(c, org_id)
    rows = c.db.execute(select(User, OrgMember.org_role).join(OrgMember, OrgMember.user_id == User.id)
                        .where(OrgMember.org_id == org_id).order_by(OrgMember.org_role, User.full_name_en)).all()
    return [OrgMemberOut(user=UserOut.model_validate(u), org_role=r) for u, r in rows]


@router.get("/invitations", response_model=list[PendingInvite])
def list_invitations(org_id: UUID, c: Ctx = Depends(ctx)):
    if _membership(c, org_id).org_role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org_admin_required")
    rows = c.db.scalars(select(Invitation).where(Invitation.org_id == org_id, Invitation.kind == "org_member",
                                                 Invitation.accepted_at.is_(None),
                                                 Invitation.expires_at > datetime.now(UTC))
                        .order_by(Invitation.created_at.desc()))
    return [PendingInvite(email=i.email, expires_at=i.expires_at) for i in rows]


@router.post("/invitations", response_model=InviteOut, status_code=201)
def invite_member(org_id: UUID, body: OrgInviteIn, bg: BackgroundTasks, c: Ctx = Depends(ctx)):
    if _membership(c, org_id).org_role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org_admin_required")
    already = c.db.scalar(select(OrgMember.id).join(User, User.id == OrgMember.user_id)
                          .where(OrgMember.org_id == org_id, func.lower(User.email) == body.email.lower()))
    if already:
        raise HTTPException(status.HTTP_409_CONFLICT, "already_org_member")
    org = c.db.get(Organization, org_id)
    out = create_invite(c.db, bg, kind="org_member", email=body.email, inviter=c.user, org_id=org_id,
                        org_role=body.org_role, subject_ar=f"جهة «{org.name_ar}»",
                        subject_en=f"the organization \"{org.name_en}\"")
    audit(c.db, entity="organization", action="invite_member", entity_id=org_id, actor=c.user.id, org_id=org_id,
          changes={"email": out.email, "org_role": body.org_role}, ip=c.meta.ip, user_agent=c.meta.user_agent)
    return out
