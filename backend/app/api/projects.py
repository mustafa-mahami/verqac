from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.access import project_access, require
from app.core.audit import audit, diff
from app.core.deps import Ctx, ctx
from app.core.kinds import new_code, submittal_kinds
from app.core.mailer import mail_enabled
from app.core.notify import channels, mahami_enabled
from app.models.core import Organization, OrgMember, Project, ProjectMember, ProjectParty, Role
from app.models.records import Record, RecordType, SubmittalDetails
from app.schemas.core import (OrgOut, PartyOut, ProjectIn, ProjectListItem, ProjectOut, ProjectSettingsIn, SubmittalKind,
                              ProjectSettingsOut, ProjectStats, RoleOut, NotifyChannels)

router = APIRouter(prefix="/projects", tags=["projects"])

# the organization that creates the project takes part as this party, with this role
CREATOR_PARTY = {"contractor": ("contractor", "contractor_pm"), "consultant": ("consultant", "consultant_pm")}


def _parties(c: Ctx, project_ids: list[UUID]) -> dict[UUID, list[PartyOut]]:
    rows = c.db.execute(
        select(ProjectParty, Organization).outerjoin(Organization, Organization.id == ProjectParty.org_id)
        .where(ProjectParty.project_id.in_(project_ids), ProjectParty.status != "removed")
    ).all()
    out: dict[UUID, list[PartyOut]] = {}
    for p, o in rows:
        out.setdefault(p.project_id, []).append(PartyOut(
            id=p.id, kind=p.kind, status=p.status, placeholder_name=p.placeholder_name,
            org=OrgOut.model_validate(o) if o else None))
    return out


@router.get("", response_model=list[ProjectListItem])
def list_projects(c: Ctx = Depends(ctx)):
    """Every project the user can reach, across organizations, with the user's role in it."""
    rows = c.db.execute(
        select(Project, Role)
        .outerjoin(ProjectMember, (ProjectMember.project_id == Project.id) & (ProjectMember.user_id == c.user.id))
        .outerjoin(Role, Role.id == ProjectMember.role_id)
        .where(Project.is_archived.is_(False))
        .order_by(Project.created_at.desc())
    ).all()
    ids = [p.id for p, _ in rows]
    parties = _parties(c, ids)
    stats = _stats(c, ids)
    return [ProjectListItem(project=ProjectOut.model_validate(p), my_role=RoleOut.model_validate(r) if r else None,
                            parties=parties.get(p.id, []), stats=stats.get(p.id, ProjectStats()))
            for p, r in rows]


def _stats(c: Ctx, project_ids: list[UUID]) -> dict[UUID, ProjectStats]:
    """Counts over the records the user can see (RLS hides other parties' drafts)."""
    if not project_ids:
        return {}
    now = datetime.now(UTC)
    rows = c.db.execute(
        select(Record.project_id,
               func.count(func.distinct(Record.revision_group_id)),
               func.count().filter(Record.state_category == "submitted"),
               func.count().filter((Record.state_category == "submitted") & (Record.due_at < now)))
        .where(Record.project_id.in_(project_ids)).group_by(Record.project_id)
    ).all()
    return {pid: ProjectStats(records=n, open=o, overdue=od) for pid, n, o, od in rows}


@router.post("", response_model=ProjectListItem, status_code=201)
def create_project(body: ProjectIn, c: Ctx = Depends(ctx)):
    membership = c.db.execute(
        select(OrgMember.org_role, Organization).join(Organization, Organization.id == OrgMember.org_id)
        .where(OrgMember.org_id == body.org_id, OrgMember.user_id == c.user.id)
    ).first()
    if membership is None or membership[0] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org_admin_required")
    org = membership[1]
    if org.kind not in CREATOR_PARTY:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "org_kind_cannot_create_projects")
    if c.db.scalar(select(Project.id).where(Project.owner_org_id == org.id,
                                            func.upper(Project.code) == body.code.upper())):
        raise HTTPException(status.HTTP_409_CONFLICT, "project_code_taken")

    fields = body.model_dump(exclude={"org_id", "consultant_name", "owner_name"})
    project = Project(owner_org_id=org.id, **fields)
    c.db.add(project)
    try:
        c.db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "project_code_taken") from None

    party_kind, role_code = CREATOR_PARTY[org.kind]
    own_party = ProjectParty(project_id=project.id, org_id=org.id, kind=party_kind, status="active")
    c.db.add(own_party)
    for kind, name in (("consultant", body.consultant_name), ("owner", body.owner_name)):
        if name and kind != party_kind:
            c.db.add(ProjectParty(project_id=project.id, kind=kind, placeholder_name=name, status="invited"))
    c.db.flush()

    role = c.db.scalar(select(Role).where(Role.org_id.is_(None), Role.code == role_code))
    c.db.add(ProjectMember(project_id=project.id, user_id=c.user.id, party_id=own_party.id, role_id=role.id))
    audit(c.db, entity="project", action="create", entity_id=project.id, actor=c.user.id, org_id=org.id,
          project_id=project.id, changes={"code": project.code, "name_en": project.name_en},
          ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return ProjectListItem(project=ProjectOut.model_validate(project), my_role=RoleOut.model_validate(role),
                           parties=_parties(c, [project.id]).get(project.id, []))


@router.get("/{project_id}", response_model=ProjectListItem)
def get_project(project_id: UUID, c: Ctx = Depends(ctx)):
    project = c.db.get(Project, project_id)
    if project is None:
        # RLS hides other organizations' projects: same answer as "does not exist"
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    role = c.db.scalar(select(Role).join(ProjectMember, ProjectMember.role_id == Role.id)
                       .where(ProjectMember.project_id == project_id, ProjectMember.user_id == c.user.id))
    return ProjectListItem(project=ProjectOut.model_validate(project),
                           my_role=RoleOut.model_validate(role) if role else None,
                           parties=_parties(c, [project_id]).get(project_id, []))


@router.get("/{project_id}/settings", response_model=ProjectSettingsOut)
def get_settings(project_id: UUID, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    saved = (a.project.settings or {}).get("review_days", {})
    days = {rt.code: int(saved.get(rt.code, rt.review_days))
            for rt in c.db.scalars(select(RecordType).where(RecordType.org_id.is_(None)).order_by(RecordType.sort))}
    return ProjectSettingsOut(review_days=days, notify=NotifyChannels(**channels(a.project)),
                              submittal_kinds=[SubmittalKind(**k) for k in submittal_kinds(a.project)],
                              email_available=mail_enabled(), mahami_available=mahami_enabled(),
                              can_edit=a.can_manage_project)


def _check_kinds(c: Ctx, project_id: UUID, old: list[dict], new: list[SubmittalKind]) -> list[dict]:
    """Clean the list, give new kinds a code, and refuse to delete a kind that records use (deactivate it instead)."""
    out, seen = [], set()
    for k in new:
        ar, en = k.name_ar.strip(), k.name_en.strip()
        if not ar or not en:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "kind_name_required")
        if ar in seen:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "kind_duplicate")
        seen.add(ar)
        out.append({"code": k.code or new_code(), "name_ar": ar, "name_en": en, "active": k.active})
    if len({k["code"] for k in out}) != len(out):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "kind_duplicate")
    if not any(k["active"] for k in out):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "kind_one_active")
    removed = {k["code"] for k in old} - {k["code"] for k in out}
    if removed and c.db.scalar(select(func.count()).select_from(SubmittalDetails)
                               .join(Record, Record.id == SubmittalDetails.record_id)
                               .where(Record.project_id == project_id, SubmittalDetails.submittal_kind.in_(removed))):
        raise HTTPException(status.HTTP_409_CONFLICT, "kind_in_use")
    return out


@router.put("/{project_id}/settings", response_model=ProjectSettingsOut)
def put_settings(project_id: UUID, body: ProjectSettingsIn, c: Ctx = Depends(ctx)):
    """Reply periods per record type (contract / QMP). New periods apply to records submitted afterwards."""
    a = project_access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    codes = set(c.db.scalars(select(RecordType.code).where(RecordType.org_id.is_(None))))
    for code, days in body.review_days.items():
        if code not in codes or not 1 <= days <= 365:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_review_days")
    settings = dict(a.project.settings or {})
    before = dict(settings.get("review_days", {}))
    settings["review_days"] = {**before, **body.review_days}
    changes = diff(before, settings["review_days"])
    if body.notify is not None:
        old = settings.get("notify", {})
        settings["notify"] = body.notify.model_dump()
        changes.update({f"notify_{k}": v for k, v in diff(old, settings["notify"]).items()})
    if body.submittal_kinds is not None:
        old = submittal_kinds(a.project)
        settings["submittal_kinds"] = _check_kinds(c, project_id, old, body.submittal_kinds)
        if settings["submittal_kinds"] != old:
            changes["submittal_kinds"] = [[k["name_ar"] for k in old], [k["name_ar"] for k in settings["submittal_kinds"]]]
    a.project.settings = settings  # new dict object so the JSONB change is saved
    audit(c.db, entity="project", action="settings", entity_id=project_id, actor=c.user.id,
          org_id=a.project.owner_org_id, project_id=project_id, changes=changes,
          ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return get_settings(project_id, c)
