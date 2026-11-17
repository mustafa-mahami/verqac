"""Laboratory tests: templates, concrete classes, a test's certificate and results, AI reading of the PDF."""
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.core import storage
from app.core.access import project_access, require
from app.core.audit import audit
from app.core.db import session_scope
from app.core.deps import Ctx, ctx
from app.core.lab import (DECISIONS, MATERIAL_CODES, MATERIALS, ai_call, ai_enabled, ai_prompt, drafts_from_ai, evaluate,
                          log)
from app.models.core import OrgMember, Project
from app.models.lab import ConcreteClass, LabResult, LabTemplate
from app.models.records import Attachment, Record, StoredFile

router = APIRouter(tags=["lab"])


# ----------------------------------------------------------------------------- schemas
class LineIO(BaseModel):
    sample: str | None = Field(default=None, max_length=60)
    parameter: str = Field(max_length=200)
    unit: str | None = Field(default=None, max_length=30)
    method: str | None = Field(default=None, max_length=80)
    age: int | None = None
    kind: Literal["number", "okng"] = "number"
    value: float | None = None
    text: str | None = Field(default=None, max_length=60)
    min: float | None = None
    max: float | None = None
    role: Literal["strength7", "strength28"] | None = None
    legible: bool = True
    result: str | None = None  # output only


class TemplateIO(BaseModel):
    id: uuid.UUID | None = None
    code: str | None = None
    name_ar: str = Field(max_length=150)
    name_en: str = Field(max_length=150)
    material: str = "OTH"
    standard: str | None = Field(default=None, max_length=200)
    acceptance: Literal["all", "concrete"] = "all"
    samples: str | None = Field(default=None, max_length=200)
    lines: list[LineIO] = Field(default=[], max_length=200)
    is_active: bool = True


class ClassIO(BaseModel):
    id: uuid.UUID | None = None
    grade: str = Field(max_length=30)
    name: str | None = Field(default=None, max_length=150)
    aliases: str | None = Field(default=None, max_length=150)
    specimen: Literal["cube", "cylinder"] = "cube"
    fck: Decimal = Field(gt=0, le=200)
    mean_margin: Decimal = Field(default=Decimal(0), ge=0, le=50)
    individual_rule: Literal["minus", "percent"] = "minus"
    individual_margin: Decimal = Field(default=Decimal(4), ge=0, le=100)
    elements: str | None = Field(default=None, max_length=300)
    topic_ids: list[uuid.UUID] = []
    ref: str | None = Field(default=None, max_length=150)
    is_active: bool = True
    tests: int = 0  # output only


class LabIO(BaseModel):
    template_id: uuid.UUID | None = None
    material: str | None = None
    acceptance: Literal["all", "concrete"] = "all"
    lab_name: str | None = Field(default=None, max_length=150)
    lab_report_no: str | None = Field(default=None, max_length=80)
    sampling_date: date | None = None
    test_date: date | None = None
    report_date: date | None = None
    grade: str | None = Field(default=None, max_length=30)
    class_id: uuid.UUID | None = None
    fck: float | None = None
    mean_margin: float | None = None
    individual_rule: Literal["minus", "percent"] | None = None
    individual_margin: float | None = None
    element: str | None = Field(default=None, max_length=200)
    quantity: float | None = None
    quantity_uom: str | None = Field(default=None, max_length=20)
    specimen_count: int | None = Field(default=None, ge=0, le=500)
    specification: str | None = Field(default=None, max_length=200)
    lab_conclusion: Literal["pass", "fail"] | None = None
    lines: list[LineIO] = Field(default=[], max_length=600)
    ai_applied: bool = False  # the values come from the AI review: the draft is cleared


class LabOut(LabIO):
    result: str | None = None
    note: str | None = None
    strength_avg: float | None = None
    strength_min: float | None = None
    below: int = 0
    checked: int = 0
    failed: int = 0
    decision: str | None = None
    decision_note: str | None = None
    decision_at: datetime | None = None
    conflict: bool = False  # the lab's own conclusion differs from the calculated result
    can_edit: bool = False
    can_decide: bool = False
    ai_enabled: bool = False
    ai_state: str | None = None
    ai_message: str | None = None
    ai_draft: dict | None = None
    ai_file_id: uuid.UUID | None = None


class DecisionIn(BaseModel):
    decision: Literal["retest", "core", "accepted", "repair", "rejected", "other"] | None
    note: str | None = Field(default=None, max_length=2000)


class AiReadIn(BaseModel):
    file_id: uuid.UUID


# ----------------------------------------------------------------------------- templates
def _admin(c: Ctx, org_id: uuid.UUID) -> bool:
    role = c.db.scalar(select(OrgMember.org_role).where(OrgMember.org_id == org_id, OrgMember.user_id == c.user.id,
                                                        OrgMember.is_active))
    if role is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return role == "admin"


def _tpl_out(t: LabTemplate) -> TemplateIO:
    return TemplateIO(id=t.id, code=t.code, name_ar=t.name_ar, name_en=t.name_en, material=t.material, standard=t.standard,
                      acceptance=t.acceptance, samples=t.samples, lines=[LineIO(**x) for x in t.lines], is_active=t.is_active)


@router.get("/lab/materials")
def materials():
    return [{"code": c, "name_ar": ar, "name_en": en} for c, ar, en in MATERIALS]


@router.get("/orgs/{org_id}/lab-templates", response_model=list[TemplateIO])
def org_templates(org_id: uuid.UUID, c: Ctx = Depends(ctx)):
    _admin(c, org_id)
    return [_tpl_out(t) for t in c.db.scalars(select(LabTemplate).where(LabTemplate.org_id == org_id).order_by(LabTemplate.sort))]


@router.put("/orgs/{org_id}/lab-templates", response_model=list[TemplateIO])
def save_templates(org_id: uuid.UUID, body: list[TemplateIO], c: Ctx = Depends(ctx)):
    require(_admin(c, org_id), "org_admin_required")
    old = {t.id: t for t in c.db.scalars(select(LabTemplate).where(LabTemplate.org_id == org_id))}
    for i, x in enumerate(body):
        if not x.name_ar.strip() or not x.name_en.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "name_required")
        if x.material not in MATERIAL_CODES:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_material")
        t = old.pop(x.id, None) if x.id else None
        if t is None:
            t = LabTemplate(org_id=org_id, code=x.code or "t_" + uuid.uuid4().hex[:8])
            c.db.add(t)
        t.name_ar, t.name_en, t.material, t.standard = x.name_ar.strip(), x.name_en.strip(), x.material, x.standard
        t.acceptance, t.samples, t.is_active, t.sort = x.acceptance, (x.samples or "").strip() or None, x.is_active, (i + 1) * 10
        t.lines = [y.model_dump(exclude={"value", "text", "result", "legible", "age"}) for y in x.lines if y.parameter.strip()]
    for t in old.values():
        c.db.delete(t)
    audit(c.db, entity="org", action="lab_templates", entity_id=org_id, actor=c.user.id, org_id=org_id,
          changes={"templates": len(body)}, ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return org_templates(org_id, c)


@router.get("/projects/{project_id}/lab-templates", response_model=list[TemplateIO])
def project_templates(project_id: uuid.UUID, c: Ctx = Depends(ctx)):
    """The project owner's templates (whoever asks: the contractor writes the tests)."""
    a = project_access(c, project_id)
    with session_scope(bypass=True) as s:
        return [_tpl_out(t) for t in s.scalars(select(LabTemplate).where(LabTemplate.org_id == a.project.owner_org_id,
                                                                       LabTemplate.is_active).order_by(LabTemplate.sort))]


# ----------------------------------------------------------------------------- concrete classes
def _classes(db, project_id) -> list[ConcreteClass]:
    return list(db.scalars(select(ConcreteClass).where(ConcreteClass.project_id == project_id)
                           .order_by(ConcreteClass.sort, ConcreteClass.fck)))


@router.get("/projects/{project_id}/concrete-classes", response_model=list[ClassIO])
def get_classes(project_id: uuid.UUID, c: Ctx = Depends(ctx)):
    project_access(c, project_id)
    counts: dict = {}
    for cid in c.db.scalars(select(LabResult.class_id).where(LabResult.class_id.is_not(None))):
        counts[cid] = counts.get(cid, 0) + 1
    return [ClassIO(id=x.id, grade=x.grade, name=x.name, aliases=x.aliases, specimen=x.specimen, fck=x.fck,
                    mean_margin=x.mean_margin, individual_rule=x.individual_rule, individual_margin=x.individual_margin,
                    elements=x.elements, topic_ids=x.topic_ids or [], ref=x.ref, is_active=x.is_active,
                    tests=counts.get(x.id, 0)) for x in _classes(c.db, project_id)]


@router.put("/projects/{project_id}/concrete-classes", response_model=list[ClassIO])
def save_classes(project_id: uuid.UUID, body: list[ClassIO], c: Ctx = Depends(ctx)):
    """The whole list. Changing a class re-judges the tests that use it (the project specification changed)."""
    a = project_access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    old = {x.id: x for x in _classes(c.db, project_id)}
    seen = set()
    for i, x in enumerate(body):
        g = x.grade.strip().upper()
        if not g or g in seen:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "class_duplicate")
        seen.add(g)
        if x.individual_rule == "percent" and not 50 <= x.individual_margin <= 100:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "class_percent")
        k = old.pop(x.id, None) if x.id else None
        if k is None:
            k = ConcreteClass(project_id=project_id)
            c.db.add(k)
        k.grade, k.name, k.aliases, k.specimen, k.fck = x.grade.strip(), x.name, x.aliases, x.specimen, x.fck
        k.mean_margin, k.individual_rule, k.individual_margin = x.mean_margin, x.individual_rule, x.individual_margin
        k.elements, k.topic_ids, k.ref, k.is_active, k.sort = x.elements, x.topic_ids or None, x.ref, x.is_active, (i + 1) * 10
    for k in old.values():
        c.db.delete(k)
    c.db.flush()
    for res in c.db.scalars(select(LabResult).join(ConcreteClass, ConcreteClass.id == LabResult.class_id)
                            .where(ConcreteClass.project_id == project_id)):
        _apply_class(res, c.db.get(ConcreteClass, res.class_id))
        _judge(res)
    audit(c.db, entity="project", action="concrete_classes", entity_id=project_id, actor=c.user.id,
          org_id=a.project.owner_org_id, project_id=project_id, changes={"classes": [x.grade for x in body]},
          ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return get_classes(project_id, c)


# ----------------------------------------------------------------------------- a test's results
def _load_test(c: Ctx, record_id: uuid.UUID):
    from app.api.records import _load
    rec, a, rt, p = _load(c, record_id)
    if rt.code != "test":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    res = c.db.get(LabResult, rec.id)
    if res is None:
        res = LabResult(record_id=rec.id)
        c.db.add(res)
        c.db.flush()
    return rec, a, rt, p, res


def _as_dict(res: LabResult) -> dict:
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    return {"acceptance": res.acceptance, "fck": f(res.fck), "mean_margin": f(res.mean_margin),
            "individual_rule": res.individual_rule, "individual_margin": f(res.individual_margin), "lines": res.lines}


def _apply_class(res: LabResult, k: ConcreteClass | None) -> None:
    """The class fixes fck and the acceptance rule; 28-day specimens take fck as their minimum."""
    if k is None:
        return
    res.acceptance, res.grade, res.fck = "concrete", k.grade, k.fck
    res.mean_margin, res.individual_rule, res.individual_margin = k.mean_margin, k.individual_rule, k.individual_margin
    res.lines = [{**x, "min": float(k.fck)} if x.get("role") == "strength28" else x for x in res.lines]


def _judge(res: LabResult) -> dict:
    ev = evaluate(_as_dict(res))
    res.result, res.note = ev["result"], (ev["note"] or None)
    return ev


def _lab_out(c: Ctx, rec: Record, a, p, res: LabResult) -> LabOut:
    ev = evaluate(_as_dict(res))
    lines = [LineIO(**{**x, "result": r}) for x, r in zip(res.lines, ev["line_results"])]
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    return LabOut(
        template_id=res.template_id, material=res.material, acceptance=res.acceptance, lab_name=res.lab_name,
        lab_report_no=res.lab_report_no, sampling_date=res.sampling_date, test_date=res.test_date,
        report_date=res.report_date, grade=res.grade, class_id=res.class_id, fck=f(res.fck), mean_margin=f(res.mean_margin),
        individual_rule=res.individual_rule, individual_margin=f(res.individual_margin), element=res.element,
        quantity=f(res.quantity), quantity_uom=res.quantity_uom, specimen_count=res.specimen_count,
        specification=res.specification, lab_conclusion=res.lab_conclusion, lines=lines,
        result=ev["result"], note=ev["note"] or None, strength_avg=ev["strength_avg"], strength_min=ev["strength_min"],
        below=ev["below"], checked=ev["checked"], failed=ev["failed"],
        decision=res.decision, decision_note=res.decision_note, decision_at=res.decision_at,
        conflict=bool(res.lab_conclusion and ev["result"] and res.lab_conclusion != ev["result"]),
        can_edit=rec.state_category == "draft" and p.can("edit", rec),
        can_decide=ev["result"] == "fail" and rec.state_category != "draft" and p.can("respond", rec),
        ai_enabled=ai_enabled(), ai_state=res.ai_state, ai_message=res.ai_message, ai_draft=res.ai_draft,
        ai_file_id=res.ai_file_id)


@router.get("/records/{record_id}/lab", response_model=LabOut)
def get_lab(record_id: uuid.UUID, c: Ctx = Depends(ctx)):
    rec, a, rt, p, res = _load_test(c, record_id)
    return _lab_out(c, rec, a, p, res)


@router.put("/records/{record_id}/lab", response_model=LabOut)
def put_lab(record_id: uuid.UUID, body: LabIO, c: Ctx = Depends(ctx)):
    rec, a, rt, p, res = _load_test(c, record_id)
    require(rec.state_category == "draft" and p.can("edit", rec), "locked_after_submit")
    if body.material and body.material not in MATERIAL_CODES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_material")
    if body.template_id is not None:
        with session_scope(bypass=True) as s:
            t = s.get(LabTemplate, body.template_id)
            if t is None or t.org_id != a.project.owner_org_id:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_template")
    k = None
    if body.class_id is not None:
        k = c.db.get(ConcreteClass, body.class_id)
        if k is None or k.project_id != rec.project_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_class")
    for f in ("template_id", "material", "acceptance", "lab_name", "lab_report_no", "sampling_date", "test_date",
              "report_date", "grade", "class_id", "fck", "mean_margin", "individual_rule", "individual_margin", "element",
              "quantity", "quantity_uom", "specimen_count", "specification", "lab_conclusion"):
        setattr(res, f, getattr(body, f))
    res.lines = [x.model_dump(exclude={"result"}) for x in body.lines if x.parameter.strip()]
    _apply_class(res, k)
    _judge(res)
    if body.ai_applied:
        res.ai_draft, res.ai_state, res.ai_message = None, "applied", None
    from app.api.records import _audit
    _audit(c, rec, "lab", {"lines": len(res.lines), "result": res.result, "ai": body.ai_applied}, a)
    rec.updated_at = datetime.now(UTC)
    c.db.flush()
    return _lab_out(c, rec, a, p, res)


@router.put("/records/{record_id}/lab/decision", response_model=LabOut)
def put_decision(record_id: uuid.UUID, body: DecisionIn, c: Ctx = Depends(ctx)):
    """What is done about a failed test (retest, core test, accepted by the Engineer, repair, rejected ...)."""
    rec, a, rt, p, res = _load_test(c, record_id)
    require(rec.state_category != "draft" and p.can("respond", rec), "cannot_respond")
    require(res.result == "fail", "not_failed")
    res.decision, res.decision_note = body.decision, (body.note or "").strip() or None
    res.decision_by, res.decision_at = (c.user.id, datetime.now(UTC)) if body.decision else (None, None)
    from app.api.records import _audit
    _audit(c, rec, "lab_decision", {"decision": body.decision}, a)
    c.db.flush()
    return _lab_out(c, rec, a, p, res)


# ----------------------------------------------------------------------------- AI reading
def _ai_job(record_id: uuid.UUID, file_id: uuid.UUID) -> None:
    """Runs in the background (a certificate takes 20-60 s); the page polls the test until the draft is ready."""
    try:
        with session_scope(bypass=True) as s:
            res = s.get(LabResult, record_id)
            rec = s.get(Record, record_id)
            f = s.get(StoredFile, file_id)
            pdf = storage.path_of(f.storage_key).read_bytes()
            t = s.get(LabTemplate, res.template_id) if res.template_id else None
            tpl = {"name_en": t.name_en, "lines": t.lines} if t else None
            lab = {**_as_dict(res), "lines": res.lines or (t.lines if t else [])}
            prompt = ai_prompt(tpl, res.acceptance)
        data, model = ai_call(pdf, prompt)
        with session_scope(bypass=True) as s:
            res, rec = s.get(LabResult, record_id), s.get(Record, record_id)
            drafts = drafts_from_ai(data, lab, [k for k in _classes(s, rec.project_id) if k.is_active], rec.topic_id)
            if not drafts or not any(d["lines"] for d in drafts):
                raise ValueError("no_values_found")
            res.ai_draft, res.ai_state, res.ai_message = {"certificates": drafts, "model": model}, "ready", None
    except Exception as e:  # noqa: BLE001 - the reason is shown on the test
        log.warning("AI reading failed for %s: %s", record_id, e)
        with session_scope(bypass=True) as s:
            res = s.get(LabResult, record_id)
            res.ai_state, res.ai_message = "error", str(e)[:290]


@router.post("/records/{record_id}/lab/ai-read", response_model=LabOut)
def ai_read(record_id: uuid.UUID, body: AiReadIn, bg: BackgroundTasks, c: Ctx = Depends(ctx)):
    rec, a, rt, p, res = _load_test(c, record_id)
    require(rec.state_category == "draft" and p.can("edit", rec), "locked_after_submit")
    if not ai_enabled():
        raise HTTPException(status.HTTP_409_CONFLICT, "ai_not_configured")
    att = c.db.scalar(select(Attachment).where(Attachment.record_id == rec.id, Attachment.file_id == body.file_id))
    f = c.db.get(StoredFile, body.file_id)
    if att is None or f is None or f.content_type != "application/pdf":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "not_a_pdf")
    if res.ai_state == "reading":
        raise HTTPException(status.HTTP_409_CONFLICT, "ai_busy")
    res.ai_state, res.ai_message, res.ai_draft, res.ai_file_id = "reading", None, None, body.file_id
    c.db.flush()
    bg.add_task(_ai_job, rec.id, body.file_id)  # after the commit; the page polls until the draft is ready
    return _lab_out(c, rec, a, p, res)


@router.post("/records/{record_id}/lab/ai-discard", response_model=LabOut)
def ai_discard(record_id: uuid.UUID, c: Ctx = Depends(ctx)):
    rec, a, rt, p, res = _load_test(c, record_id)
    require(p.can("edit", rec), "cannot_edit")
    res.ai_draft, res.ai_state, res.ai_message = None, None, None
    c.db.flush()
    return _lab_out(c, rec, a, p, res)
