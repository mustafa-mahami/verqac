"""QA/QC KPI scorecard of a project, and its targets (Project settings > KPIs)."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from pydantic import BaseModel, Field

from app.core import kpi
from app.core.access import project_access, require
from app.core.audit import audit
from app.core.deps import Ctx, ctx

router = APIRouter(tags=["kpi"])


class TargetIO(BaseModel):
    green: float | None = Field(None, ge=0, le=100000)
    amber: float | None = Field(None, ge=0, le=100000)
    qmp_ref: str | None = Field(None, max_length=60)
    active: bool = True


class KpiSettings(BaseModel):
    targets: dict[str, TargetIO]
    ncr_close_days: int = Field(kpi.DEFAULT_NCR_CLOSE_DAYS, ge=1, le=365)


class KpiDef(BaseModel):
    code: str
    section: str
    unit: str
    direction: str
    name_ar: str
    name_en: str
    formula_ar: str
    formula_en: str
    default_green: float | None
    default_amber: float | None
    default_qmp: str


class KpiSettingsOut(KpiSettings):
    defs: list[KpiDef]
    can_edit: bool


def _out(a) -> KpiSettingsOut:
    s = kpi.settings_of(a.project)
    defs = [KpiDef(code=d[0], section=d[1], unit=d[2], direction=d[3], default_green=d[4], default_amber=d[5],
                   default_qmp=d[6], name_ar=d[7], name_en=d[8], formula_ar=d[9], formula_en=d[10]) for d in kpi.DEFS]
    return KpiSettingsOut(targets={k: TargetIO(**v) for k, v in s["targets"].items()}, ncr_close_days=s["ncr_close_days"],
                          defs=defs, can_edit=a.can_manage_project)


@router.get("/projects/{project_id}/kpi")
def get_kpi(project_id: uuid.UUID, date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
            discipline: str | None = Query(None, max_length=10), c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_range")
    return kpi.compute(c.db, a.project, date_from, date_to, discipline or None)


def _disc_name(c: Ctx, code: str | None, lang: str) -> str | None:
    from app.models.core import Discipline
    if not code:
        return None
    d = c.db.scalar(select(Discipline).where(Discipline.code == code).limit(1))
    return (getattr(d, f"name_{lang}") or d.name_ar) if d else code


@router.get("/projects/{project_id}/kpi/{fmt}")
def export_kpi(project_id: uuid.UUID, fmt: str, lang: str = Query("ar", pattern="^(ar|en)$"),
               date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
               discipline: str | None = Query(None, max_length=10), c: Ctx = Depends(ctx)):
    """The scorecard to print (pdf) or to work on (xlsx), with the same filters as the screen."""
    from app.reports.kpi_report import kpi_xlsx, render_kpi_pdf
    if fmt not in ("pdf", "xlsx"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    data = get_kpi(project_id, date_from, date_to, discipline, c)
    a = project_access(c, project_id)
    name = f"{a.project.code}-QA-KPIs-{date.today().isoformat()}"
    disc = _disc_name(c, discipline, lang)
    if fmt == "pdf":
        return Response(render_kpi_pdf(c, a, data, lang, date_from, date_to, disc), media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})
    return Response(kpi_xlsx(a, data, lang, date_from, date_to, disc),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}.xlsx"'})


@router.get("/projects/{project_id}/kpi-settings", response_model=KpiSettingsOut)
def get_kpi_settings(project_id: uuid.UUID, c: Ctx = Depends(ctx)):
    return _out(project_access(c, project_id))


@router.put("/projects/{project_id}/kpi-settings", response_model=KpiSettingsOut)
def put_kpi_settings(project_id: uuid.UUID, body: KpiSettings, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    if set(body.targets) - set(kpi.CODES):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_settings")
    for code, t in body.targets.items():
        if kpi.DEF[code][3] != "info" and (t.green is None or t.amber is None):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "kpi_target_required")
        higher = kpi.DEF[code][3] == "higher"
        if t.green is not None and t.amber is not None and (t.amber > t.green if higher else t.amber < t.green):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "kpi_amber_order")
    new = {"targets": {k: v.model_dump() for k, v in body.targets.items()}, "ncr_close_days": body.ncr_close_days}
    a.project.settings = {**(a.project.settings or {}), "kpi": new}
    audit(c.db, entity="project", action="kpi_settings", entity_id=project_id, actor=c.user.id,
          org_id=a.project.owner_org_id, project_id=project_id, changes=new, ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return _out(a)


@router.get("/kpi/portfolio")
def kpi_portfolio(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
                  c: Ctx = Depends(ctx)):
    """The scorecard of every project the user can reach, side by side (each against its own targets)."""
    from app.models.core import Project
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_range")
    rows, used = [], []
    for p in c.db.scalars(select(Project).where(Project.is_archived.is_(False)).order_by(Project.code)):
        k = kpi.compute(c.db, p, date_from, date_to)
        vals = {x["code"]: {"value": x["value"], "status": x["status"]} for x in k["kpis"]}
        if not any(v["value"] is not None for v in vals.values()):
            continue  # nothing recorded in the period
        for code in vals:
            if code not in used:
                used.append(code)
        score = {s: sum(1 for v in vals.values() if v["status"] == s) for s in ("green", "amber", "red")}
        rows.append({"id": str(p.id), "code": p.code, "name_ar": p.name_ar, "name_en": p.name_en, "kpis": vals,
                     "score": score, "counts": {s: k[s].get("records", k[s].get("issued")) for s in kpi.SECTIONS}})
    order = {d[0]: i for i, d in enumerate(kpi.DEFS)}
    defs = [{"code": d[0], "section": d[1], "unit": d[2], "direction": d[3], "name_ar": d[7], "name_en": d[8]}
            for d in kpi.DEFS if d[0] in used]
    defs.sort(key=lambda d: order[d["code"]])
    return {"projects": rows, "defs": defs}
