"""Project team: parties (contractor, consultant, owner) and the people of each party."""
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import func, select, update

from app.core.access import ProjectAccess, project_access, require
from app.core.audit import audit, diff
from app.core.db import session_scope
from app.core.deps import Ctx, ctx
from app.core.invites import create_invite
from app.core.roles import is_hidden, overrides, role_out
from app.models.core import (Discipline, Invitation, Organization, OrgMember, Project, ProjectMember, ProjectParty, Role,
                             RolePermission, User)
from app.schemas.core import (InviteOut, MemberIn, MemberOut, MemberPatch, OrgOut, PartyIn, PartyInviteIn,
                              PendingInvite, ProjectOut, ProjectRoleIn, ProjectRoleOut, ProjectRolePatch, TeamInviteIn, TeamOut,
                              TeamParty, UserOut)

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
        .where(ProjectMember.project_id == project_id,
               # people of the imported history who never joined: their names stay on the records, not in the team
               ~(User.email.like("%@import.verqac.invalid") & ProjectMember.is_active.is_(False)))
        .order_by(Role.sort, User.full_name_en)
    ).all()
    members = [MemberOut(id=m.id, user=UserOut.model_validate(u), party_id=m.party_id, role=role_out(a.project, r),
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


def _check_role_and_disciplines(c: Ctx, party: ProjectParty, role_id: UUID | None, discipline_ids: list[UUID] | None,
                                current: UUID | None = None):
    if role_id is not None:
        role = c.db.get(Role, role_id)
        platform = role is not None and role.org_id is None and role.project_id is None
        own = role is not None and role.project_id == party.project_id and role.org_id == party.org_id
        if role is None or role.party_kind != party.kind or not (platform or own):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "role_not_for_party")
        if role_id != current and is_hidden(c.db.get(Project, party.project_id), role):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "role_hidden")
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
                     role=role_out(a.project, role), discipline_ids=member.discipline_ids, is_active=True)


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
    _check_role_and_disciplines(c, party, body.role_id, body.discipline_ids, current=member.role_id)

    before = {"role_id": member.role_id, "discipline_ids": list(member.discipline_ids), "is_active": member.is_active}
    if body.role_id is not None:
        member.role_id = body.role_id
    if body.discipline_ids is not None:
        member.discipline_ids = body.discipline_ids
    if body.is_active is not None:
        member.is_active = body.is_active
    after = {"role_id": member.role_id, "discipline_ids": list(member.discipline_ids), "is_active": member.is_active}
    user = c.db.get(User, member.user_id)
    names = {f: v.strip() for f in ("full_name_ar", "full_name_en")
             if (v := getattr(body, f)) is not None and v.strip() != getattr(user, f)}
    if names:
        # a person's name is theirs across the platform: only a colleague of the same organization corrects it
        same_org = c.db.scalar(select(OrgMember.user_id).where(OrgMember.org_id == party.org_id,
                                                               OrgMember.user_id == user.id))
        require(same_org is not None, "not_same_org")
        before.update({f: getattr(user, f) for f in names})
        after.update(names)
        with session_scope(bypass=True) as side:  # users may only update themselves under RLS
            side.execute(update(User).where(User.id == user.id).values(**names))
        c.db.expire(user)
    c.db.flush()
    _audit(c, a, "project_member", "update", member.id, diff(before, after))
    role = c.db.get(Role, member.role_id)
    return MemberOut(id=member.id, user=UserOut.model_validate(user), party_id=party.id,
                     role=role_out(a.project, role), discipline_ids=member.discipline_ids,
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


# ---- roles of the project: each party names its own roles on top of the platform roles of that party


def _role_party(c: Ctx, a: ProjectAccess, kind: str) -> ProjectParty | None:
    """The party of this kind whose roles the user manages (his own party), or None."""
    if a.party is None or a.party.kind != kind or not a.can_manage_party_team(a.party):
        return None
    return a.party


def _project_role(c: Ctx, a: ProjectAccess, role_id: UUID) -> tuple[Role, ProjectParty]:
    role = c.db.get(Role, role_id)
    if role is None or not ((role.org_id is None and role.project_id is None) or role.project_id == a.project.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    party = _role_party(c, a, role.party_kind)
    if party is None or (role.project_id is not None and role.org_id != party.org_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
    return role, party


def _in_use(c: Ctx, project_id: UUID) -> dict[UUID, int]:
    return dict(c.db.execute(select(ProjectMember.role_id, func.count()).where(
        ProjectMember.project_id == project_id, ProjectMember.is_active).group_by(ProjectMember.role_id)).all())


def _role_row(c: Ctx, a: ProjectAccess, r: Role, used: dict) -> ProjectRoleOut:
    party = _role_party(c, a, r.party_kind)
    can = party is not None and (r.project_id is None or r.org_id == party.org_id)
    return ProjectRoleOut(**role_out(a.project, r).model_dump(), custom=r.project_id is not None,
                          hidden=is_hidden(a.project, r), members=used.get(r.id, 0), can_edit=can)


@router.get("/roles", response_model=list[ProjectRoleOut])
def list_project_roles(project_id: UUID, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    used = _in_use(c, project_id)
    roles = c.db.scalars(select(Role).where(
        ((Role.org_id.is_(None)) & (Role.project_id.is_(None))) | (Role.project_id == project_id))
        .order_by(Role.sort, Role.name_en)).all()
    return [_role_row(c, a, r, used) for r in roles]


@router.post("/roles", response_model=ProjectRoleOut, status_code=status.HTTP_201_CREATED)
def add_project_role(project_id: UUID, body: ProjectRoleIn, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    base = c.db.get(Role, body.base_role_id)
    if base is None or base.org_id is not None or base.project_id is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "role_not_for_party")
    party = _role_party(c, a, base.party_kind)  # same party only: the base decides the party
    if party is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "forbidden")
    from uuid import uuid4
    role = Role(org_id=party.org_id, project_id=project_id, code=f"p_{uuid4().hex[:12]}", base_code=base.code,
                name_ar=body.name_ar.strip(), name_en=body.name_en.strip(), party_kind=base.party_kind,
                manage_project=base.manage_project, manage_team=base.manage_team, act_on_behalf=base.act_on_behalf,
                view_dashboards=base.view_dashboards, sort=base.sort)
    c.db.add(role)
    c.db.flush()
    for rp in c.db.scalars(select(RolePermission).where(RolePermission.role_id == base.id)):
        c.db.add(RolePermission(role_id=role.id, record_type=rp.record_type, action=rp.action, scope=rp.scope))
    _audit(c, a, "role", "create", role.id, {"name_ar": role.name_ar, "name_en": role.name_en, "base": base.code})
    c.db.flush()
    return _role_row(c, a, role, {})


@router.patch("/roles/{role_id}", response_model=ProjectRoleOut)
def edit_project_role(project_id: UUID, role_id: UUID, body: ProjectRolePatch, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    role, _ = _project_role(c, a, role_id)
    changes = {}
    settings = dict(a.project.settings or {})
    over = {k: dict(v) for k, v in overrides(a.project).items()}
    o = over.setdefault(role.code, {})
    for f in ("name_ar", "name_en"):
        v = getattr(body, f)
        if v is None:
            continue
        v = v.strip()
        if role.project_id is not None:  # a project role is renamed in place
            if v != getattr(role, f):
                changes[f] = [getattr(role, f), v]
                setattr(role, f, v)
        else:  # a platform role is renamed for this project only; its own name clears the override
            old = o.get(f) or getattr(role, f)
            if v != old:
                changes[f] = [old, v]
            o.pop(f, None) if v == getattr(role, f) else o.__setitem__(f, v)
    if body.hidden is not None and body.hidden != bool(o.get("hidden")):
        changes["hidden"] = [bool(o.get("hidden")), body.hidden]
        o["hidden"] = body.hidden
    if not o.get("hidden"):
        o.pop("hidden", None)
    if not o:
        over.pop(role.code, None)
    settings["roles"] = over
    a.project.settings = settings
    if changes:
        _audit(c, a, "role", "update", role.id, changes)
    c.db.flush()
    return _role_row(c, a, role, _in_use(c, project_id))


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project_role(project_id: UUID, role_id: UUID, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    role, _ = _project_role(c, a, role_id)
    if role.project_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "role_is_base")  # platform roles are hidden, not deleted
    if c.db.scalar(select(func.count()).select_from(ProjectMember).where(ProjectMember.role_id == role.id)) or \
            c.db.scalar(select(func.count()).select_from(Invitation).where(Invitation.role_id == role.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "role_in_use")
    _audit(c, a, "role", "delete", role.id, {"name_ar": role.name_ar, "name_en": role.name_en})
    c.db.delete(role)
