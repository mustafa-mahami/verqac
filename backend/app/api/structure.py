"""Project types (per organization, with templates) and each project's stages and locations."""
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select

from app.core.access import project_access, require
from app.core.audit import audit
from app.core.db import session_scope
from app.core.deps import Ctx, ctx
from app.models.core import OrgMember, Project
from app.models.records import Record
from app.models.structure import ProjectLocation, ProjectStage, ProjectStageTopic, ProjectType
from app.schemas.structure import (
    ApplyTypeIn, GroupIO, Labels, ProjectTypeIO, StageIO, StructureOut, TopicIO, TypeRef, UnitIO,
)

router = APIRouter(tags=["structure"])


def _bad(code: str):
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, code)


def _names(x) -> tuple[str, str]:
    ar, en = x.name_ar.strip(), x.name_en.strip()
    if not ar or not en:
        _bad("name_required")
    return ar, en


def _check_weights(items) -> None:
    active = [x for x in items if getattr(x, "is_active", True)]
    if active and abs(sum((Decimal(x.weight) for x in active), Decimal(0)) - 100) > Decimal("0.01"):
        _bad("weights_must_total_100")


# ----------------------------------------------------------------------------- project types
def _type_out(t: ProjectType) -> ProjectTypeIO:
    return ProjectTypeIO(id=t.id, name_ar=t.name_ar, name_en=t.name_en, group_label_ar=t.group_label_ar,
                         group_label_en=t.group_label_en, unit_label_ar=t.unit_label_ar,
                         unit_label_en=t.unit_label_en, stages=t.stages, units=t.units, is_active=t.is_active)


@router.get("/orgs/{org_id}/project-types", response_model=list[ProjectTypeIO])
def list_types(org_id: uuid.UUID, c: Ctx = Depends(ctx)):
    return [_type_out(t) for t in c.db.scalars(select(ProjectType).where(ProjectType.org_id == org_id)
                                                .order_by(ProjectType.sort))]


@router.put("/orgs/{org_id}/project-types", response_model=list[ProjectTypeIO])
def save_types(org_id: uuid.UUID, body: list[ProjectTypeIO], c: Ctx = Depends(ctx)):
    """The whole list, in order. A type used by projects cannot be deleted (switch it off instead)."""
    role = c.db.scalar(select(OrgMember.org_role).where(OrgMember.org_id == org_id, OrgMember.user_id == c.user.id,
                                                        OrgMember.is_active))
    require(role == "admin", "org_admin_required")
    old = {t.id: t for t in c.db.scalars(select(ProjectType).where(ProjectType.org_id == org_id))}
    seen: set[str] = set()
    for i, x in enumerate(body):
        ar, en = _names(x)
        if ar in seen:
            _bad("type_duplicate")
        seen.add(ar)
        for s in x.stages:
            _names(s)
            for tp in s.topics:
                _names(tp)
        for u in x.units:
            _names(u)
        _check_weights(x.stages)
        labels = [v.strip() for v in (x.group_label_ar, x.group_label_en, x.unit_label_ar, x.unit_label_en)]
        if not all(labels):
            _bad("labels_required")
        t = old.pop(x.id, None) if x.id else None
        if t is None:
            if x.id:
                _bad("not_found")
            t = ProjectType(org_id=org_id, code="t_" + uuid.uuid4().hex[:8])
            c.db.add(t)
        t.name_ar, t.name_en = ar, en
        t.group_label_ar, t.group_label_en, t.unit_label_ar, t.unit_label_en = labels
        t.stages = [{**s.model_dump(mode="json"), "name_ar": s.name_ar.strip(), "name_en": s.name_en.strip(),
                     "weight": float(s.weight),
                     "topics": [{"name_ar": tp.name_ar.strip(), "name_en": tp.name_en.strip(),
                                 "checklist": _items(tp.checklist)} for tp in s.topics]}
                    for s in x.stages]
        t.units = [{"name_ar": u.name_ar.strip(), "name_en": u.name_en.strip()} for u in x.units]
        t.is_active, t.sort = x.is_active, (i + 1) * 10
    if old:
        with session_scope(bypass=True) as s:
            if s.scalar(select(func.count()).select_from(Project).where(Project.project_type_id.in_(old.keys()))):
                raise HTTPException(status.HTTP_409_CONFLICT, "type_in_use")
        for t in old.values():
            c.db.delete(t)
    audit(c.db, entity="org", action="project_types", entity_id=org_id, actor=c.user.id, org_id=org_id,
          changes={"types": [x.name_ar for x in body]}, ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return list_types(org_id, c)


def _items(items) -> list[dict]:
    """Checklist lines, trimmed; the English text falls back to the Arabic one."""
    out = []
    for x in items:
        ar, en = x.ar.strip(), x.en.strip()
        if ar or en:
            out.append({"ar": ar or en, "en": en or ar})
    return out


# ----------------------------------------------------------------------------- project structure
def labels_of(project: Project) -> Labels:
    return Labels(**(project.settings or {}).get("structure_labels", {}))


def _used_ids(project_id: uuid.UUID) -> tuple[set, set, set]:
    """Stages, locations and topics that records point at (every party's records, so the check is not filtered)."""
    with session_scope(bypass=True) as s:
        stages = set(s.scalars(select(Record.stage_id).where(Record.project_id == project_id,
                                                             Record.stage_id.is_not(None))))
        topics = set(s.scalars(select(Record.topic_id).where(Record.project_id == project_id,
                                                             Record.topic_id.is_not(None))))
        locs: set = set()
        for ids in s.scalars(select(Record.location_ids).where(Record.project_id == project_id,
                                                               Record.location_ids.is_not(None))):
            locs.update(ids)
    return stages, locs, topics


def progress_stages(project_id: uuid.UUID) -> set:
    """Stages that approved daily reports gave a %: changing their scope would move or drop that progress."""
    from app.models.daily import DailyReport
    with session_scope(bypass=True) as s:
        out = set()
        for works in s.scalars(select(DailyReport.works).join(Record, Record.id == DailyReport.record_id)
                               .where(DailyReport.project_id == project_id,
                                      Record.state_category.in_(("approved", "approved_as_noted")))):
            out.update(uuid.UUID(str(w["stage_id"])) for w in works if w.get("stage_id") and w.get("progress") is not None)
    return out


def structure_of(c: Ctx, project: Project, can_edit: bool) -> StructureOut:
    used_stages, used_locs, used_topics = _used_ids(project.id)
    locked = progress_stages(project.id)
    topics: dict = {}
    for tp in c.db.scalars(select(ProjectStageTopic).where(ProjectStageTopic.project_id == project.id)
                           .order_by(ProjectStageTopic.sort)):
        topics.setdefault(tp.stage_id, []).append(
            TopicIO(id=tp.id, name_ar=tp.name_ar, name_en=tp.name_en, is_active=tp.is_active, used=tp.id in used_topics,
                    checklist=tp.checklist or []))
    stages = [StageIO(id=s.id, name_ar=s.name_ar, name_en=s.name_en, scope=s.scope, weight=s.weight,
                      is_active=s.is_active, used=s.id in used_stages or s.id in locked or any(t.used for t in topics.get(s.id, [])),
                      scope_locked=s.id in locked, location_ids=s.location_ids or None, topics=topics.get(s.id, []))
              for s in c.db.scalars(select(ProjectStage).where(ProjectStage.project_id == project.id)
                                    .order_by(ProjectStage.sort))]
    rows = c.db.scalars(select(ProjectLocation).where(ProjectLocation.project_id == project.id)
                        .order_by(ProjectLocation.sort)).all()
    groups = []
    for g in (r for r in rows if r.kind == "group"):
        units = [UnitIO(id=u.id, name_ar=u.name_ar, name_en=u.name_en, is_active=u.is_active, used=u.id in used_locs)
                 for u in rows if u.parent_id == g.id]
        groups.append(GroupIO(id=g.id, name_ar=g.name_ar, name_en=g.name_en, is_active=g.is_active,
                              used=g.id in used_locs or any(u.used for u in units), units=units))
    ptype = None
    if project.project_type_id:
        snap = (project.settings or {}).get("project_type", {})
        ptype = TypeRef(id=project.project_type_id, name_ar=snap.get("name_ar", ""), name_en=snap.get("name_en", ""))
    types = []
    if can_edit:
        types = [TypeRef(id=t.id, name_ar=t.name_ar, name_en=t.name_en) for t in c.db.scalars(
            select(ProjectType).where(ProjectType.org_id == project.owner_org_id, ProjectType.is_active)
            .order_by(ProjectType.sort))]
    return StructureOut(project_type=ptype, labels=labels_of(project), stages=stages, locations=groups,
                        can_edit=can_edit, types=types,
                        checklists=bool((project.settings or {}).get("checklists", False)))


@router.post("/projects/{project_id}/save-as-type")
def save_as_type(project_id: uuid.UUID, c: Ctx = Depends(ctx)):
    """The project's stages (active ones: names, scope, weights, topics with their checklists) become the template
    of its project type, for the organization's next projects. Projects made before keep their own stages."""
    a = project_access(c, project_id)
    p = a.project
    role = c.db.scalar(select(OrgMember.org_role).where(OrgMember.org_id == p.owner_org_id, OrgMember.user_id == c.user.id,
                                                        OrgMember.is_active))
    require(role == "admin", "org_admin_required")
    t = c.db.get(ProjectType, p.project_type_id) if p.project_type_id else None
    if t is None or t.org_id != p.owner_org_id:
        _bad("no_project_type")
    stages = c.db.scalars(select(ProjectStage).where(ProjectStage.project_id == p.id, ProjectStage.is_active)
                          .order_by(ProjectStage.sort)).all()
    if not stages:
        _bad("no_stages")
    topics = {}
    for tp in c.db.scalars(select(ProjectStageTopic).where(ProjectStageTopic.project_id == p.id, ProjectStageTopic.is_active)
                           .order_by(ProjectStageTopic.sort)):
        topics.setdefault(tp.stage_id, []).append({"name_ar": tp.name_ar, "name_en": tp.name_en, "checklist": tp.checklist or []})
    t.stages = [{"name_ar": s.name_ar, "name_en": s.name_en, "scope": s.scope, "weight": float(s.weight),
                 "topics": topics.get(s.id, [])} for s in stages]
    audit(c.db, entity="org", action="project_type_from_project", entity_id=t.id, actor=c.user.id, org_id=p.owner_org_id,
          project_id=p.id, changes={"type": t.name_ar, "stages": [s.name_ar for s in stages]}, ip=c.meta.ip,
          user_agent=c.meta.user_agent)
    c.db.flush()
    return {"type_ar": t.name_ar, "type_en": t.name_en, "stages": len(stages)}


def apply_type(c: Ctx, project: Project, t: ProjectType) -> None:
    """Set the project's type and copy its templates where the project has none yet."""
    project.project_type_id = t.id
    project.settings = {**(project.settings or {}),
                        "project_type": {"name_ar": t.name_ar, "name_en": t.name_en},
                        "structure_labels": {"group_ar": t.group_label_ar, "group_en": t.group_label_en,
                                             "unit_ar": t.unit_label_ar, "unit_en": t.unit_label_en}}
    if not c.db.scalar(select(ProjectStage.id).where(ProjectStage.project_id == project.id).limit(1)):
        for i, s in enumerate(t.stages):
            st = ProjectStage(id=uuid.uuid4(), project_id=project.id, name_ar=s["name_ar"], name_en=s["name_en"],
                              scope=s.get("scope", "per_location"), weight=Decimal(str(s.get("weight", 0))),
                              sort=(i + 1) * 10)
            c.db.add(st)
            c.db.flush()
            for j, tp in enumerate(s.get("topics", [])):
                c.db.add(ProjectStageTopic(project_id=project.id, stage_id=st.id, name_ar=tp["name_ar"],
                                           name_en=tp["name_en"], sort=(j + 1) * 10,
                                           checklist=tp.get("checklist", [])))
    if not c.db.scalar(select(ProjectLocation.id).where(ProjectLocation.project_id == project.id).limit(1)):
        g = ProjectLocation(id=uuid.uuid4(), project_id=project.id, kind="group", sort=10,
                            name_ar=f"{t.group_label_ar} 1", name_en=f"{t.group_label_en} 1")
        c.db.add(g)
        c.db.flush()
        for i, u in enumerate(t.units):
            c.db.add(ProjectLocation(project_id=project.id, parent_id=g.id, kind="unit", name_ar=u["name_ar"],
                                     name_en=u["name_en"], sort=(i + 1) * 10))
    c.db.flush()


@router.get("/projects/{project_id}/structure", response_model=StructureOut)
def get_structure(project_id: uuid.UUID, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    return structure_of(c, a.project, a.can_manage_project)


@router.post("/projects/{project_id}/apply-type", response_model=StructureOut)
def post_apply_type(project_id: uuid.UUID, body: ApplyTypeIn, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    t = c.db.get(ProjectType, body.project_type_id)
    if t is None or t.org_id != a.project.owner_org_id:
        _bad("not_found")
    apply_type(c, a.project, t)
    audit(c.db, entity="project", action="apply_type", entity_id=project_id, actor=c.user.id,
          org_id=a.project.owner_org_id, project_id=project_id, changes={"type": t.name_en},
          ip=c.meta.ip, user_agent=c.meta.user_agent)
    return structure_of(c, a.project, True)


@router.put("/projects/{project_id}/stages", response_model=StructureOut)
def save_stages(project_id: uuid.UUID, body: list[StageIO], c: Ctx = Depends(ctx)):
    """The whole list, in order. Active weights total 100. A stage in use can be switched off, not deleted."""
    a = project_access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    for x in body:
        _names(x)
        for tp in x.topics:
            _names(tp)
    _check_weights(body)
    old = {s.id: s for s in c.db.scalars(select(ProjectStage).where(ProjectStage.project_id == project_id))}
    old_topics = {t.id: t for t in c.db.scalars(select(ProjectStageTopic)
                                                .where(ProjectStageTopic.project_id == project_id))}
    removed = set(old) - {x.id for x in body if x.id}
    removed_topics = set(old_topics) - {tp.id for x in body for tp in x.topics if tp.id}
    used_stages, _, used_topics = _used_ids(project_id)
    if removed & used_stages:
        raise HTTPException(status.HTTP_409_CONFLICT, "stage_in_use")
    if removed_topics & used_topics:
        raise HTTPException(status.HTTP_409_CONFLICT, "topic_in_use")
    # a stage that changes scope moves its approved % to other cells: refused once approved reports gave it a %
    # (stop it and add a new stage instead); before that, recount from the approved reports
    rescoped = {x.id for x in body if x.id in old and old[x.id].scope != x.scope}
    if rescoped & progress_stages(project_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "stage_scope_locked")
    if removed & progress_stages(project_id):
        raise HTTPException(status.HTTP_409_CONFLICT, "stage_in_use")
    rescope = bool(rescoped)
    units = set(c.db.scalars(select(ProjectLocation.id).where(ProjectLocation.project_id == project_id,
                                                              ProjectLocation.kind == "unit")))
    for i, x in enumerate(body):
        s = old.get(x.id) if x.id else None
        if x.id and s is None:
            _bad("not_found")
        if s is None:
            s = ProjectStage(id=uuid.uuid4(), project_id=project_id)
            c.db.add(s)
        s.name_ar, s.name_en = _names(x)
        s.scope, s.weight, s.is_active, s.sort = x.scope, x.weight, x.is_active, (i + 1) * 10
        s.location_ids = [u for u in (x.location_ids or []) if u in units] if x.scope == "per_location" else None
        s.location_ids = s.location_ids or None
        c.db.flush()
        for j, tp in enumerate(x.topics):
            r = old_topics.get(tp.id) if tp.id else None
            if tp.id and r is None:
                _bad("not_found")
            if r is None:
                r = ProjectStageTopic(project_id=project_id, stage_id=s.id)
                c.db.add(r)
            elif r.stage_id != s.id and r.id in used_topics:
                raise HTTPException(status.HTTP_409_CONFLICT, "topic_in_use")
            r.stage_id = s.id
            r.name_ar, r.name_en = _names(tp)
            r.is_active, r.sort = tp.is_active, (j + 1) * 10
            r.checklist = _items(tp.checklist)
    if removed_topics:
        c.db.execute(delete(ProjectStageTopic).where(ProjectStageTopic.id.in_(removed_topics)))
    if removed:
        c.db.execute(delete(ProjectStage).where(ProjectStage.id.in_(removed)))
    audit(c.db, entity="project", action="stages", entity_id=project_id, actor=c.user.id,
          org_id=a.project.owner_org_id, project_id=project_id,
          changes={"stages": [f"{x.name_ar} {x.weight}" for x in body]}, ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    if rescope:
        from app.api.daily import rebuild_progress
        rebuild_progress(c.db, project_id)
    return structure_of(c, a.project, True)


@router.put("/projects/{project_id}/locations", response_model=StructureOut)
def save_locations(project_id: uuid.UUID, body: list[GroupIO], c: Ctx = Depends(ctx)):
    """Buildings / zones with their floors / sections, in order. A location in use can be switched off only."""
    a = project_access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    old = {r.id: r for r in c.db.scalars(select(ProjectLocation).where(ProjectLocation.project_id == project_id))}
    kept = {x.id for g in body for x in [g, *g.units] if x.id}
    removed = set(old) - kept
    if removed & _used_ids(project_id)[1]:
        raise HTTPException(status.HTTP_409_CONFLICT, "location_in_use")

    def put(x: UnitIO, kind: str, parent: uuid.UUID | None, sort: int) -> ProjectLocation:
        r = old.get(x.id) if x.id else None
        if x.id and (r is None or r.kind != kind):
            _bad("not_found")
        if r is None:
            r = ProjectLocation(id=uuid.uuid4(), project_id=project_id, kind=kind)
            c.db.add(r)
        r.name_ar, r.name_en = _names(x)
        r.parent_id, r.is_active, r.sort = parent, x.is_active, sort
        return r

    for i, g in enumerate(body):
        grp = put(g, "group", None, (i + 1) * 10)
        c.db.flush()
        for j, u in enumerate(g.units):
            put(u, "unit", grp.id, (j + 1) * 10)
    if removed:
        c.db.execute(delete(ProjectLocation).where(ProjectLocation.id.in_(removed), ProjectLocation.kind == "unit"))
        c.db.execute(delete(ProjectLocation).where(ProjectLocation.id.in_(removed)))
    audit(c.db, entity="project", action="locations", entity_id=project_id, actor=c.user.id,
          org_id=a.project.owner_org_id, project_id=project_id,
          changes={"groups": [f"{g.name_ar} ({len(g.units)})" for g in body]}, ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    # floors added, removed or switched on/off change which cells a report covers: recount
    from app.api.daily import rebuild_progress
    rebuild_progress(c.db, project_id)
    return structure_of(c, a.project, True)
