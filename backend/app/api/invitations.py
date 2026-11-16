"""Opening and accepting an invitation link.

The person may be new (creates an account, and for a project party also an organization)
or already registered (must be signed in with the invited e-mail). These paths run with
the system session because the invitee cannot see the project or organization yet; every
check below is explicit and the acceptance is audited.
"""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import _issue
from app.core.audit import audit
from app.core.deps import RequestMeta, _bearer, request_meta, system_db
from app.core.security import decode_access_token, hash_password, hash_token
from app.core.seed import DEFAULT_DISCIPLINES
from app.core.seed_structure import seed_project_types
from app.models.core import (Discipline, Invitation, Organization, OrgMember, Project, ProjectMember, ProjectParty,
                             Role, User)
from app.schemas.core import AcceptIn, InvitationInfo, OrgOut, ProjectOut, RoleOut, TokenOut

router = APIRouter(prefix="/invitations", tags=["invitations"])


def _load(db: Session, token: str) -> Invitation:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invitation_not_found")
    return inv


def _status(inv: Invitation, db: Session) -> str:
    if inv.accepted_at is not None:
        return "accepted"
    if inv.expires_at <= datetime.now(UTC):
        return "expired"
    if inv.kind == "project_party":
        party = db.get(ProjectParty, inv.party_id)
        if party is None or party.status != "invited":  # someone else already joined as this party
            return "expired"
    return "valid"


@router.get("/{token}", response_model=InvitationInfo)
def get_invitation(token: str, db: Session = Depends(system_db, scope="function")):
    inv = _load(db, token)
    inviter = db.get(User, inv.created_by)
    project = db.get(Project, inv.project_id) if inv.project_id else None
    org = db.get(Organization, inv.org_id or (project.owner_org_id if project else None))
    party = db.get(ProjectParty, inv.party_id) if inv.party_id else None
    role = db.get(Role, inv.role_id) if inv.role_id else None
    exists = bool(db.scalar(select(User.id).where(func.lower(User.email) == inv.email)))
    if inv.kind == "org_member" and inv.project_id and project is None:
        project = db.get(Project, inv.project_id)
    return InvitationInfo(
        kind=inv.kind, email=inv.email, status=_status(inv, db), user_exists=exists,
        inviter_name_ar=inviter.full_name_ar, inviter_name_en=inviter.full_name_en,
        org=OrgOut.model_validate(org) if org else None,
        project=ProjectOut.model_validate(project) if project else None,
        party_kind=party.kind if party else None, party_placeholder=party.placeholder_name if party else None,
        role=RoleOut.model_validate(role) if role else None,
    )


def _signed_in_user(db: Session, creds: HTTPAuthorizationCredentials | None) -> User | None:
    uid = decode_access_token(creds.credentials) if creds else None
    return db.get(User, uid) if uid else None


def _new_org(db: Session, kind: str, name_ar: str, name_en: str, locale: str, admin: User) -> Organization:
    org = Organization(kind=kind, name_ar=name_ar, name_en=name_en, default_locale=locale)
    db.add(org)
    db.flush()
    db.add(OrgMember(org_id=org.id, user_id=admin.id, org_role="admin"))
    for i, (code, ar, en) in enumerate(DEFAULT_DISCIPLINES):
        db.add(Discipline(org_id=org.id, code=code, name_ar=ar, name_en=en, sort=(i + 1) * 10))
    seed_project_types(db, org.id)
    return org


@router.post("/{token}/accept", response_model=TokenOut)
def accept(token: str, body: AcceptIn, response: Response, db: Session = Depends(system_db, scope="function"),
           creds: HTTPAuthorizationCredentials | None = Depends(_bearer), meta: RequestMeta = Depends(request_meta)):
    inv = _load(db, token)
    if _status(inv, db) != "valid":
        raise HTTPException(status.HTTP_410_GONE, "invitation_invalid")

    # 1. who accepts
    user = _signed_in_user(db, creds)
    if user is not None:
        if user.email.lower() != inv.email:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "invitation_other_email")
    else:
        if db.scalar(select(User.id).where(func.lower(User.email) == inv.email)):
            raise HTTPException(status.HTTP_409_CONFLICT, "login_required")
        if not (body.full_name_ar and body.full_name_en and body.password):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "profile_required")
        user = User(email=inv.email, password_hash=hash_password(body.password), full_name_ar=body.full_name_ar,
                    full_name_en=body.full_name_en, locale=body.locale)
        db.add(user)
        db.flush()

    # 2. what the invitation grants
    changes: dict = {"kind": inv.kind}
    if inv.kind == "org_member":
        om = db.scalar(select(OrgMember).where(OrgMember.org_id == inv.org_id, OrgMember.user_id == user.id))
        if om is None:
            db.add(OrgMember(org_id=inv.org_id, user_id=user.id, org_role=inv.org_role or "member"))
        else:
            om.is_active = True  # a suspended colleague invited again comes back
        org_id, project_id = inv.org_id, None
        if inv.project_id and inv.party_id:  # invited from a project team: join it straight away
            party = db.get(ProjectParty, inv.party_id)
            if party is not None and party.status == "active" and party.org_id == inv.org_id:
                pm = db.scalar(select(ProjectMember).where(ProjectMember.project_id == inv.project_id,
                                                           ProjectMember.user_id == user.id))
                if pm is None:
                    db.add(ProjectMember(project_id=inv.project_id, user_id=user.id, party_id=party.id,
                                         role_id=inv.role_id, discipline_ids=inv.discipline_ids or []))
                else:
                    pm.is_active, pm.role_id, pm.discipline_ids = True, inv.role_id, inv.discipline_ids or []
                project_id = inv.project_id
    else:
        party = db.get(ProjectParty, inv.party_id)
        if body.org_id:
            org = db.get(Organization, body.org_id)
            is_admin = db.scalar(select(OrgMember.id).where(OrgMember.org_id == body.org_id,
                                                            OrgMember.user_id == user.id,
                                                            OrgMember.org_role == "admin"))
            if org is None or not is_admin:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "org_admin_required")
            if org.kind != party.kind:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "org_kind_mismatch")
        else:
            name_ar = body.org_name_ar or party.placeholder_name
            name_en = body.org_name_en
            if not (name_ar and name_en):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "org_name_required")
            org = _new_org(db, party.kind, name_ar, name_en, body.locale, user)
            changes["new_org"] = str(org.id)
        if db.scalar(select(ProjectParty.id).where(ProjectParty.project_id == party.project_id,
                                                   ProjectParty.org_id == org.id,
                                                   ProjectParty.status != "removed")):
            raise HTTPException(status.HTTP_409_CONFLICT, "org_already_party")
        party.org_id, party.status = org.id, "active"
        existing = db.scalar(select(ProjectMember).where(ProjectMember.project_id == party.project_id,
                                                         ProjectMember.user_id == user.id))
        if existing:
            raise HTTPException(status.HTTP_409_CONFLICT, "already_member")
        db.add(ProjectMember(project_id=party.project_id, user_id=user.id, party_id=party.id, role_id=inv.role_id))
        org_id, project_id = org.id, party.project_id
        changes["party"] = str(party.id)

    inv.accepted_at = datetime.now(UTC)
    user.last_login_at = inv.accepted_at
    audit(db, entity="invitation", action="accept", entity_id=inv.id, actor=user.id, org_id=org_id,
          project_id=project_id, changes=changes, ip=meta.ip, user_agent=meta.user_agent)
    return _issue(db, user, response, meta)


@router.get("/{token}/my-orgs", response_model=list[OrgOut])
def my_orgs_for_invite(token: str, db: Session = Depends(system_db, scope="function"),
                       creds: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    """For a signed-in invitee: the organizations of the right kind they administer and could join with."""
    inv = _load(db, token)
    user = _signed_in_user(db, creds)
    if user is None or user.email.lower() != inv.email or inv.kind != "project_party":
        return []
    kind = db.get(ProjectParty, inv.party_id).kind
    rows = db.scalars(select(Organization).join(OrgMember, OrgMember.org_id == Organization.id)
                      .where(OrgMember.user_id == user.id, OrgMember.org_role == "admin", Organization.kind == kind))
    return [OrgOut.model_validate(o) for o in rows]

