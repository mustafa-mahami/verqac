"""Project team: parties (contractor, consultant, owner) and the people of each party."""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select

from app.core.access import ProjectAccess, project_access, require
from app.core.audit import audit, diff
from app.core.deps import Ctx, ctx
from app.core.invites import create_invite
from app.models.core import (Discipline, Invitation, Organization, OrgMember, ProjectMember, ProjectParty, Role,
                             User)
from app.schemas.core import (InviteOut, MemberIn, MemberOut, MemberPatch, OrgOut, PartyIn, PartyInviteIn,
                              PendingInvite, ProjectOut, RoleOut, TeamInviteIn, TeamOut, TeamParty, UserOut)

router = APIRouter(prefix="/projects/{project_id}", tags=["team"])

# role given to the person who accepts a party invitation
PARTY_LEAD_ROLE = {"consultant": "consultant_pm", "owner": "owner_rep", "contractor": "contractor_pm"}


def _platform_role(c: Ctx, code: str) -> Role:
    return c.db.scalar(select(Role).where(Role.org_id.is_(None), Role.code == code))


def _party(c: Ctx, a: ProjectAccess, party_id: UUID) -> ProjectParty:
    party = c.db.get(ProjectParty, party_id)
    if party is None or party.project_id != a.project.id or party.status == "removed":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return party


def _audit(c: Ctx, a: ProjectAccess, entity: str, action: str, entity_id, changes: dict) -> None:
    audit(c.db, entity=entity, action=action, entity_id=entity_id, actor=c.user.id, org_id=a.project.owner_org_id,
          project_id=a.project.id, changes=changes, ip=c.meta.ip, user_agent=c.meta.user_agent)


def _invite_party(c: Ctx, a: ProjectAccess, bg: BackgroundTasks, party: ProjectParty, email: str) -> InviteOut:
    role = _platform_role(c, PARTY_LEAD_ROLE[party.kind])
    kind_ar = {"consultant": "استشاري", "owner": "مالك"}[party.kind]
    out = create_invite(
        c.db, bg, kind="project_party", email=email, inviter=c.user, project_id=a.project.id, party_id=party.id,
        role_id=role.id, subject_ar=f"مشروع «{a.project.name_ar}» بصفة {kind_ar}",
        subject_en=f"project \"{a.project.name_en}\" as {party.kind}",
    )
    _audit(c, a, "project_party", "invite", party.id, {"email": out.email, "kind": party.kind})
    return out


@router.get("/team", response_model=TeamOut)
def get_team(project_id: UUID, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    now = datetime.now(UTC)
    rows = c.db.execute(
        select(ProjectParty, Organization).outerjoin(Organization, Organization.id == ProjectParty.org_id)
        .where(ProjectParty.project_id == project_id, ProjectParty.status != "removed")
        .order_by(ProjectParty.created_at)
    ).all()
    pending = {}
    if a.can_manage_project:
        for inv in c.db.scalars(select(Invitation).where(
                Invitation.project_id == project_id, Invitation.kind == "project_party",
                Invitation.accepted_at.is_(None), Invitation.expires_at > now).order_by(Invitation.created_at)):
            pending[inv.party_id] = PendingInvite(email=inv.email, expires_at=inv.expires_at)
    parties = [
        TeamParty(id=p.id, kind=p.kind, status=p.status, placeholder_name=p.placeholder_name,
                  org=OrgOut.model_validate(o) if o else None, can_manage_team=a.can_manage_party_team(p),
                  pending_invite=pending.get(p.id) if p.status == "invited" else None)
        for p, o in rows
    ]
    mrows = c.db.execute(
        select(ProjectMember, User, Role).join(User, User.id == ProjectMember.user_id)
        .join(Role, Role.id == ProjectMember.role_id)
        .where(ProjectMember.project_id == project_id).order_by(Role.sort, User.full_name_en)
    ).all()
    members = [MemberOut(id=m.id, user=UserOut.model_validate(u), party_id=m.party_id, role=RoleOut.model_validate(r),
                         discipline_ids=m.discipline_ids, is_active=m.is_active) for m, u, r in mrows]
    return TeamOut(project=ProjectOut.model_validate(a.project), can_manage_project=a.can_manage_project,
                   my_party_id=a.member.party_id if a.member else None, parties=parties, members=members)


@router.post("/parties", response_model=InviteOut | None, status_code=201)
def add_party(project_id: UUID, body: PartyIn, bg: BackgroundTasks, c: Ctx = Depends(ctx)):
    """Add the consultant or the owner to an existing project, optionally inviting them right away."""
    a = project_access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    exists = c.db.scalar(select(ProjectParty.id).where(ProjectParty.project_id == project_id,
                                                       ProjectParty.kind == body.kind,
                                                       ProjectParty.status != "removed"))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "party_exists")
    party = ProjectParty(project_id=project_id, kind=body.kind, placeholder_name=body.placeholder_name,
                         status="invited")
    c.db.add(party)
    c.db.flush()
    _audit(c, a, "project_party", "add", party.id, {"kind": body.kind, "name": body.placeholder_name})
    return _invite_party(c, a, bg, party, body.email) if body.email else None


@router.post("/parties/{party_id}/invite", response_model=InviteOut, status_code=201)
def invite_party(project_id: UUID, party_id: UUID, body: PartyInviteIn, bg: BackgroundTasks, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    party = _party(c, a, party_id)
    if party.status != "invited":
        raise HTTPException(status.HTTP_409_CONFLICT, "party_already_joined")
    return _invite_party(c, a, bg, party, body.email)


@router.delete("/parties/{party_id}", status_code=204)
def remove_party(project_id: UUID, party_id: UUID, c: Ctx = Depends(ctx)):
    """Only a party that has not joined yet can be removed; a joined party keeps its history."""
    a = project_access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    party = _party(c, a, party_id)
    if party.status != "invited":
        raise HTTPException(status.HTTP_409_CONFLICT, "party_already_joined")
    party.status = "removed"
    c.db.query(Invitation).filter(Invitation.party_id == party.id, Invitation.accepted_at.is_(None)) \
        .update({Invitation.expires_at: datetime.now(UTC)})
    _audit(c, a, "project_party", "remove", party.id, {"kind": party.kind})


def _check_role_and_disciplines(c: Ctx, party: ProjectParty, role_id: UUID | None, discipline_ids: list[UUID] | None):
    if role_id is not None:
        role = c.db.get(Role, role_id)
        if role is None or role.party_kind != party.kind or role.org_id not in (None, party.org_id):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "role_not_for_party")
    if discipline_ids:
        valid = set(c.db.scalars(select(Discipline.id).where(Discipline.org_id == party.org_id,
                                                             Discipline.id.in_(discipline_ids))))
        if valid != set(discipline_ids):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "discipline_not_in_org")


@router.post("/members", response_model=MemberOut, status_code=201)
def add_member(project_id: UUID, body: MemberIn, c: Ctx = Depends(ctx)):
    """Each party adds its own people: the user must belong to the party's organization."""
    a = project_access(c, project_id)
    party = _party(c, a, body.party_id)
    require(a.can_manage_party_team(party), "manage_team_required")
    if not c.db.scalar(select(OrgMember.id).where(OrgMember.org_id == party.org_id,
                                                  OrgMember.user_id == body.user_id)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "user_not_in_party_org")
    _check_role_and_disciplines(c, party, body.role_id, body.discipline_ids)

    member = c.db.scalar(select(ProjectMember).where(ProjectMember.project_id == project_id,
                                                     ProjectMember.user_id == body.user_id))
    if member and member.is_active:
        raise HTTPException(status.HTTP_409_CONFLICT, "already_member")
    if member:  # re-activate someone who left earlier, keeping the same membership row
        if member.party_id != party.id:
            raise HTTPException(status.HTTP_409_CONFLICT, "member_of_other_party")
        member.role_id, member.discipline_ids, member.is_active = body.role_id, body.discipline_ids, True
    else:
        member = ProjectMember(project_id=project_id, user_id=body.user_id, party_id=party.id,
                               role_id=body.role_id, discipline_ids=body.discipline_ids)
        c.db.add(member)
    c.db.flush()
    _audit(c, a, "project_member", "add", member.id,
           {"user_id": str(body.user_id), "role_id": str(body.role_id),
            "disciplines": [str(d) for d in body.discipline_ids]})
    user, role = c.db.get(User, body.user_id), c.db.get(Role, body.role_id)
    return MemberOut(id=member.id, user=UserOut.model_validate(user), party_id=party.id,
                     role=RoleOut.model_validate(role), discipline_ids=member.discipline_ids, is_active=True)


@router.patch("/members/{member_id}", response_model=MemberOut)
def update_member(project_id: UUID, member_id: UUID, body: MemberPatch, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    member = c.db.get(ProjectMember, member_id)
    if member is None or member.project_id != project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    party = _party(c, a, member.party_id)
    require(a.can_manage_party_team(party), "manage_team_required")
    if member.user_id == c.user.id and body.is_active is False:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot_remove_self")
    _check_role_and_disciplines(c, party, body.role_id, body.discipline_ids)

    before = {"role_id": member.role_id, "discipline_ids": list(member.discipline_ids), "is_active": member.is_active}
    if body.role_id is not None:
        member.role_id = body.role_id
    if body.discipline_ids is not None:
        member.discipline_ids = body.discipline_ids
    if body.is_active is not None:
        member.is_active = body.is_active
    after = {"role_id": member.role_id, "discipline_ids": list(member.discipline_ids), "is_active": member.is_active}
    c.db.flush()
    _audit(c, a, "project_member", "update", member.id, diff(before, after))
    user, role = c.db.get(User, member.user_id), c.db.get(Role, member.role_id)
    return MemberOut(id=member.id, user=UserOut.model_validate(user), party_id=party.id,
                     role=RoleOut.model_validate(role), discipline_ids=member.discipline_ids,
                     is_active=member.is_active)


@router.post("/parties/{party_id}/invite-member", response_model=InviteOut, status_code=201)
def invite_member(project_id: UUID, party_id: UUID, body: TeamInviteIn, bg: BackgroundTasks, c: Ctx = Depends(ctx)):
    """One step: the new colleague joins the party's organization and this project with role and disciplines."""
    a = project_access(c, project_id)
    party = _party(c, a, party_id)
    require(a.can_manage_party_team(party), "manage_team_required")
    _check_role_and_disciplines(c, party, body.role_id, body.discipline_ids)
    if c.db.scalar(select(User.id).join(OrgMember, OrgMember.user_id == User.id)
                   .where(OrgMember.org_id == party.org_id, func.lower(User.email) == body.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "already_org_member")
    org = c.db.get(Organization, party.org_id)
    out = create_invite(c.db, bg, kind="org_member", email=body.email, inviter=c.user, org_id=party.org_id,
                        project_id=project_id, party_id=party.id, role_id=body.role_id, org_role="member",
                        discipline_ids=body.discipline_ids,
                        subject_ar=f"«{org.name_ar}» ومشروع «{a.project.name_ar}»",
                        subject_en=f"\"{org.name_en}\" and the project \"{a.project.name_en}\"")
    _audit(c, a, "project_member", "invite", party.id, {"email": out.email, "role_id": str(body.role_id)})
    return out
