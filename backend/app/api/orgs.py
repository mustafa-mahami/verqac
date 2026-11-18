"""Organization users: the admin invites colleagues; employees never self-register."""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select, update

from app.core.audit import audit
from app.core.db import session_scope
from app.core.roles import role_out
from app.core.deps import Ctx, ctx
from app.core.invites import create_invite
from app.models.core import (Invitation, Organization, OrgMember, Project, ProjectMember, ProjectParty,
                             RefreshToken, Role, User)
from app.core.workcal import org_calendar
from app.schemas.core import OrgCalendar
from app.schemas.core import (InviteOut, MemberProject, OrgInviteIn, OrgMemberOut, OrgMemberPatch, PendingInvite,
                              UserOut)

router = APIRouter(prefix="/orgs/{org_id}", tags=["organization"])


def _membership(c: Ctx, org_id: UUID) -> OrgMember:
    m = c.db.scalar(select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == c.user.id,
                                            OrgMember.is_active))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return m


@router.get("/members", response_model=list[OrgMemberOut])
def list_members(org_id: UUID, c: Ctx = Depends(ctx)):
    me = _membership(c, org_id)
    rows = c.db.execute(select(User, OrgMember).join(OrgMember, OrgMember.user_id == User.id)
                        .where(OrgMember.org_id == org_id)
                        .order_by(OrgMember.is_active.desc(), OrgMember.org_role, User.full_name_en)).all()
    projects: dict = {}
    if me.org_role == "admin":  # where each colleague works, as far as this organization's parties go
        for pm, prj, role in c.db.execute(
                select(ProjectMember, Project, Role).join(Project, Project.id == ProjectMember.project_id)
                .join(ProjectParty, ProjectParty.id == ProjectMember.party_id).join(Role, Role.id == ProjectMember.role_id)
                .where(ProjectParty.org_id == org_id).order_by(Project.code)):
            projects.setdefault(pm.user_id, []).append(MemberProject(
                project_id=prj.id, code=prj.code, name_ar=prj.name_ar, name_en=prj.name_en,
                role=role_out(prj, role), is_active=pm.is_active))
    return [OrgMemberOut(user=UserOut.model_validate(u), org_role=m.org_role, is_active=m.is_active,
                         projects=projects.get(u.id, [])) for u, m in rows]


@router.patch("/members/{user_id}", response_model=list[OrgMemberOut])
def update_member(org_id: UUID, user_id: UUID, body: OrgMemberPatch, c: Ctx = Depends(ctx)):
    """Suspend / reactivate a colleague, or change admin rights. Suspending closes every project of this
    organization for that person and ends their sessions; their records and answers stay in the history."""
    if _membership(c, org_id).org_role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org_admin_required")
    if user_id == c.user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot_change_self")
    m = c.db.scalar(select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.user_id == user_id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    changes = {}
    if body.org_role is not None and body.org_role != m.org_role:
        changes["org_role"] = [m.org_role, body.org_role]
        m.org_role = body.org_role
    if body.is_active is not None and body.is_active != m.is_active:
        changes["is_active"] = [m.is_active, body.is_active]
        m.is_active = body.is_active
        if not body.is_active:
            party_ids = select(ProjectParty.id).where(ProjectParty.org_id == org_id)
            c.db.execute(update(ProjectMember).where(ProjectMember.user_id == user_id,
                                                     ProjectMember.party_id.in_(party_ids)).values(is_active=False))
            still_active = c.db.scalar(select(func.count()).select_from(OrgMember).where(
                OrgMember.user_id == user_id, OrgMember.is_active, OrgMember.org_id != org_id))
            if not still_active:  # sessions belong to the person, not to one organization
                with session_scope(bypass=True) as side:
                    side.execute(update(RefreshToken).where(RefreshToken.user_id == user_id,
                                                            RefreshToken.revoked_at.is_(None))
                                 .values(revoked_at=datetime.now(UTC)))
    if changes:
        audit(c.db, entity="org_member", action="update", entity_id=user_id, actor=c.user.id, org_id=org_id,
              changes=changes, ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return list_members(org_id, c)


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


@router.get("/calendar", response_model=OrgCalendar)
def get_calendar(org_id: UUID, c: Ctx = Depends(ctx)):
    """Weekly days off and official holidays: reply periods skip them in this organization's projects."""
    _membership(c, org_id)
    return OrgCalendar(**org_calendar(c.db.get(Organization, org_id)))


@router.put("/calendar", response_model=OrgCalendar)
def put_calendar(org_id: UUID, body: OrgCalendar, c: Ctx = Depends(ctx)):
    from app.api.projects import _check_weekend, _holidays  # local import: projects imports a lot
    if _membership(c, org_id).org_role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org_admin_required")
    _check_weekend(body.weekend)
    org = c.db.get(Organization, org_id)
    new = {"weekend": body.weekend, "holidays": _holidays(body.holidays)}
    org.settings = {**(org.settings or {}), "calendar": new}
    audit(c.db, entity="org", action="calendar", entity_id=org_id, actor=c.user.id, org_id=org_id,
          changes={"weekend": body.weekend, "holidays": len(new["holidays"])}, ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return OrgCalendar(**new)
