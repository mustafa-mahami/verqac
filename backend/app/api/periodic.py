"""Weekly and monthly site reports, put together from the approved daily reports of the period:
progress (actual against the programme), staff and labour, equipment, delays, safety, materials,
the works behind plan at the end of the period, and the QA registers (requests)."""
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from app.api.daily import GROUPS, TZ
from app.core.access import project_access
from app.core.deps import Ctx, ctx
from app.models.daily import DailyReport
from app.models.records import Record, RecordType
from app.models.structure import ProjectLocation, ProjectStage

router = APIRouter(tags=["periodic"])
APPROVED = ("approved", "approved_as_noted")
SKIP_TYPES = ("daily_report", "programme")


# ----------------------------------------------------------------------------- schemas
class StageRow(BaseModel):
    stage_id: uuid.UUID
    name_ar: str
    name_en: str
    weight: float
    start: float  # % at the start of the period
    end: float  # % at its end
    planned: float | None = None  # % planned at its end, by the current programme
    locations_ar: list[str] = []  # where it was worked on during the period
    locations_en: list[str] = []
    days: int = 0  # reports in which it appears
    qty: list[dict] = []  # [{qty, unit}] summed per unit
    man_days: int = 0  # workers on its work lines, added up over the reports
    teams: list[str] = []  # who worked on it (the work lines' teams), most man-days first


class CrewRow(BaseModel):
    group: str
    sub: str | None = None
    name: str
    name_en: str | None = None
    man_days: int
    days: int  # reports it appears in
    peak: int


class EquipRow(BaseModel):
    name: str
    unit_days: int
    days: int
    hours: float
    idle_hours: float


class DelayRow(BaseModel):
    cause: str
    count: int
    hours: float


class DelayItem(BaseModel):
    day: date
    cause: str
    hours: float | None = None
    description: str | None = None


class MaterialRow(BaseModel):
    day: date
    material: str
    qty: float | None = None
    unit: str | None = None
    supplier: str | None = None
    delivery_note: str | None = None


class LateRow(BaseModel):
    stage_id: uuid.UUID
    stage_ar: str
    stage_en: str
    where_ar: str
    where_en: str
    planned: float
    actual: float
    plan_finish: date | None = None


class ReqRow(BaseModel):
    code: str
    name_ar: str
    name_en: str
    submitted: int  # during the period
    answered: int
    approved: int  # approved or approved as noted
    returned: int  # revise and resubmit or rejected
    open: int  # waiting for a reply at the end of the period
    overdue: int  # of those, past the reply date


class OverdueItem(BaseModel):
    id: uuid.UUID
    number: str
    title: str
    code: str
    due_at: datetime
    days: int  # late by, at the end of the period


class PeriodOut(BaseModel):
    kind: str
    start: date
    end: date  # last day of the period
    upto: date  # last day counted (today, for the running period)
    prev: date
    next: date | None = None
    project_start: date | None = None  # the project's start (or its first daily report): 'from the start'
    working_days: int
    reports: int  # approved
    pending: int  # submitted, not yet approved
    missing: list[date] = []  # working days without a report
    stopped: list[date] = []
    partial: list[date] = []
    weather: dict[str, int] = {}
    progress_start: float
    progress_end: float
    planned_end: float | None = None
    planned_start: float | None = None
    spi: float | None = None
    stages: list[StageRow] = []
    crew_totals: dict[str, dict] = {}  # group -> {man_days, avg, peak}
    crew: list[CrewRow] = []
    equipment: list[EquipRow] = []
    delays: list[DelayRow] = []
    delay_items: list[DelayItem] = []
    hse: dict[str, int] = {}
    materials: list[MaterialRow] = []
    late: list[LateRow] = []
    requests: list[ReqRow] = []
    overdue: list[OverdueItem] = []


# ----------------------------------------------------------------------------- the period
def period(kind: str, day: date, weekend: set[int]) -> tuple[date, date]:
    """A week starts on the day after the weekly day off (Saturday when Friday is off); a month is the calendar month."""
    if kind == "month":
        start = day.replace(day=1)
        nxt = (start + timedelta(days=32)).replace(day=1)
        return start, nxt - timedelta(days=1)
    first = (max(weekend) + 1) % 7 if weekend else 6  # 0 = Sunday ... 6 = Saturday
    wd = (day.weekday() + 1) % 7
    start = day - timedelta(days=(wd - first) % 7)
    return start, start + timedelta(days=6)


def _su(st, unit_ids: list) -> list:
    ids = {str(x) for x in (st.location_ids or [])}
    return [u for u in unit_ids if u in ids] if ids else unit_ids


def _replay(reports: list, stages: dict, unit_ids: list, groups: dict) -> list[tuple[date, dict]]:
    """The cells after each approved report, oldest first (the same rules as the live matrix)."""
    cells: dict = {}
    out = []
    for d in reports:
        for line in d.works:
            pct = line.get("progress")
            st = stages.get(str(line.get("stage_id")))
            if st is None or pct is None:
                continue
            if st.scope == "whole" or not unit_ids:
                keys = [(str(st.id), None)]
            elif line.get("all_locations"):
                keys = [(str(st.id), u) for u in _su(st, unit_ids)]
            else:
                ids = {str(x) for x in line.get("location_ids") or []}
                keys = [(str(st.id), u) for u in _su(st, unit_ids) if u in ids or groups.get(u) in ids]
            for k in keys:
                cells[k] = float(pct)
        out.append((d.report_date, dict(cells)))
    return out


def _pct(cells: dict, stages: list, unit_ids: list) -> tuple[float, dict[str, float]]:
    total_w = sum(float(s.weight) for s in stages) or 0
    project, per = 0.0, {}
    for s in stages:
        sid = str(s.id)
        su = _su(s, unit_ids)
        if s.scope == "whole" or not su:
            pct = cells.get((sid, None), 0.0)
        else:
            pct = sum(cells.get((sid, u), 0.0) for u in su) / len(su)
        per[sid] = round(pct, 1)
        if total_w:
            project += float(s.weight) * pct / total_w
    return round(project, 1), per


def _at(history: list, day: date) -> dict:
    cells: dict = {}
    for d, c in history:
        if d > day:
            break
        cells = c
    return cells


MAX_DAYS = 3660  # a custom period: anything sensible, up to ten years (the whole project)


def build(c: Ctx, project_id: uuid.UUID, kind: str, day: date, until: date | None = None) -> PeriodOut:
    """kind week | month: the period around `day`; custom: from `day` to `until`, previous / next of the same length."""
    from app.api.programme import programmes
    from app.api.records import Perms, can_see
    from app.core.programme import cell_planned, plan_cells, planned_at
    from app.core.programme import status as cell_status
    from app.core.workcal import calendar_for
    a = project_access(c, project_id)
    db, project = c.db, a.project
    cal = calendar_for(db, project)
    today = datetime.now(TZ).date()
    if kind == "custom":
        start, end = day, until
        prev = start - timedelta(days=(end - start).days + 1)
    else:
        start, end = period(kind, day, cal.weekend)
        prev = period(kind, start - timedelta(days=1), cal.weekend)[0]
    upto = min(end, today)
    nxt = end + timedelta(days=1)

    stages = list(db.scalars(select(ProjectStage).where(ProjectStage.project_id == project_id, ProjectStage.is_active)
                             .order_by(ProjectStage.sort)))
    sby = {str(s.id): s for s in db.scalars(select(ProjectStage).where(ProjectStage.project_id == project_id))}
    locs = list(db.scalars(select(ProjectLocation).where(ProjectLocation.project_id == project_id).order_by(ProjectLocation.sort)))
    lby = {str(x.id): x for x in locs}
    units = [x for x in locs if x.kind == "unit" and x.is_active]
    unit_ids = [str(u.id) for u in units]
    groups = {str(u.id): str(u.parent_id) for u in units}
    many = len({u.parent_id for u in units}) > 1

    def where(lid: str | None, lang: str) -> str:
        x = lby.get(lid) if lid else None
        if x is None:
            return "كل المشروع" if lang == "ar" else "Whole project"
        g = lby.get(str(x.parent_id)) if many and x.parent_id else None
        return f"{getattr(g, 'name_' + lang)} – {getattr(x, 'name_' + lang)}" if g else getattr(x, "name_" + lang)

    rows = db.execute(select(DailyReport, Record.state_category).join(Record, Record.id == DailyReport.record_id)
                      .where(DailyReport.project_id == project_id, DailyReport.report_date <= end,
                             Record.state_category != "cancelled").order_by(DailyReport.report_date)).all()
    approved = [d for d, cat in rows if cat in APPROVED]
    history = _replay(approved, sby, unit_ids, groups)
    p0, s0 = _pct(_at(history, start - timedelta(days=1)), stages, unit_ids)
    end_cells = _at(history, end)
    p1, s1 = _pct(end_cells, stages, unit_ids)
    in_period = [d for d in approved if start <= d.report_date <= end]
    reported = {d.report_date for d, cat in rows if start <= d.report_date <= end}
    # days without a report count from the project's start (or its first report)
    since = max(start, project.start_date or (rows[0][0].report_date if rows else upto + timedelta(days=1)))
    out = PeriodOut(kind=kind, start=start, end=end, upto=upto, prev=prev, next=nxt if nxt <= today else None,
                    working_days=sum(1 for i in range((end - start).days + 1) if cal.working(start + timedelta(days=i))),
                    reports=len(in_period),
                    pending=sum(1 for d, cat in rows if start <= d.report_date <= end and cat not in APPROVED),
                    missing=[since + timedelta(days=i) for i in range((upto - since).days + 1)
                             if cal.working(since + timedelta(days=i)) and since + timedelta(days=i) not in reported],
                    progress_start=p0, progress_end=p1,
                    project_start=project.start_date or (rows[0][0].report_date if rows else None))

    # ---- the programme: planned at the end of the period, and the works behind it
    _, cur = programmes(db, project_id)
    plan = plan_cells(cur.lines) if cur is not None else {}
    ps: dict[str, float] = {}
    if plan:
        out.planned_end, ps = planned_at(plan, stages, units, upto)
        out.planned_start = planned_at(plan, stages, units, start - timedelta(days=1))[0]
        out.spi = round(p1 / out.planned_end, 2) if out.planned_end else None
        late = []
        for (sid, lid), (ps_, pf) in plan.items():
            st = sby.get(sid)
            if st is None or not st.is_active or (lid and lid not in unit_ids):
                continue
            planned = cell_planned(ps_, pf, upto)
            actual = end_cells.get((sid, lid), 0.0)
            if cell_status(planned, actual) == "late":
                late.append(LateRow(stage_id=st.id, stage_ar=st.name_ar, stage_en=st.name_en, where_ar=where(lid, "ar"),
                                    where_en=where(lid, "en"), planned=planned, actual=actual, plan_finish=pf))
        out.late = sorted(late, key=lambda r: (r.actual - r.planned, r.plan_finish or upto))[:60]

    # ---- the daily reports of the period
    worked: dict[str, dict] = defaultdict(lambda: {"locs": set(), "days": set(), "qty": defaultdict(float), "men": 0,
                                                   "teams": defaultdict(int)})
    crew: dict[tuple, dict] = {}
    gday: dict[str, dict[date, int]] = {g: defaultdict(int) for g in GROUPS}
    equip: dict[str, dict] = {}
    delays: dict[str, dict] = {}
    hse = {"incidents": 0, "near_misses": 0, "toolbox": 0}
    for d in in_period:
        if d.work_status == "stopped":
            out.stopped.append(d.report_date)
        elif d.work_status == "partial":
            out.partial.append(d.report_date)
        if d.weather:
            out.weather[d.weather] = out.weather.get(d.weather, 0) + 1
        for line in d.works:
            st = sby.get(str(line.get("stage_id")))
            if st is None:
                continue
            w = worked[str(st.id)]
            w["days"].add(d.report_date)
            if st.scope == "whole":
                pass
            elif line.get("all_locations"):
                w["locs"].add("*")
            else:
                w["locs"].update(str(x) for x in line.get("location_ids") or [])
            if line.get("qty") is not None:
                w["qty"][(line.get("unit") or "").strip()] += float(line["qty"])
            n = int(line.get("crew") or 0)
            w["men"] += n
            if n and (line.get("team") or "").strip():
                w["teams"][line["team"].strip()] += n
        for x in d.crew:
            g, n = x.get("group"), int(x.get("count") or 0)
            if g not in GROUPS:
                continue
            gday[g][d.report_date] += n
            key = (g, (x.get("sub") or "").strip() or None, (x.get("name") or "").strip())
            r = crew.setdefault(key, {"man_days": 0, "days": set(), "peak": 0, "en": x.get("name_en")})
            r["man_days"] += n
            r["days"].add(d.report_date)
            r["peak"] = max(r["peak"], n)
        for x in d.equipment:
            k = (x.get("name") or "").strip()
            r = equip.setdefault(k, {"unit_days": 0, "days": set(), "hours": 0.0, "idle": 0.0})
            n = int(x.get("count") or 0)
            r["unit_days"] += n
            r["days"].add(d.report_date)
            r["hours"] += float(x.get("hours") or 0) * max(n, 1)
            r["idle"] += float(x.get("idle_hours") or 0) * max(n, 1)
        for x in d.delays:
            k = x.get("cause") or "other"
            r = delays.setdefault(k, {"count": 0, "hours": 0.0})
            r["count"] += 1
            r["hours"] += float(x.get("hours") or 0)
            out.delay_items.append(DelayItem(day=d.report_date, cause=k, hours=x.get("hours"), description=x.get("description")))
        for k in hse:
            hse[k] += int((d.hse or {}).get(k) or 0)
        for x in d.materials:
            out.materials.append(MaterialRow(day=d.report_date, material=x.get("material") or "", qty=x.get("qty"), unit=x.get("unit"),
                                             supplier=x.get("supplier"), delivery_note=x.get("delivery_note")))
    out.hse = hse
    n = len(in_period) or 1
    out.crew_totals = {g: {"man_days": sum(v.values()), "avg": round(sum(v.values()) / n, 1), "peak": max(v.values(), default=0)}
                       for g, v in gday.items()}
    out.crew = sorted([CrewRow(group=g, sub=sub, name=name, name_en=r["en"], man_days=r["man_days"], days=len(r["days"]), peak=r["peak"])
                       for (g, sub, name), r in crew.items()], key=lambda r: (GROUPS.index(r.group), -r.man_days))
    out.equipment = sorted([EquipRow(name=k, unit_days=r["unit_days"], days=len(r["days"]), hours=round(r["hours"], 1),
                                     idle_hours=round(r["idle"], 1)) for k, r in equip.items()], key=lambda r: -r.unit_days)
    out.delays = sorted([DelayRow(cause=k, count=r["count"], hours=round(r["hours"], 1)) for k, r in delays.items()],
                        key=lambda r: -r.hours)
    for s in stages:
        sid = str(s.id)
        w = worked.get(sid)
        if w is None and s0.get(sid, 0) == s1.get(sid, 0) and not (ps.get(sid) or 0) > s1.get(sid, 0):
            continue  # nothing happened and nothing was due
        locs_ = []
        if w is not None and s.scope != "whole":
            ids = w["locs"]
            locs_ = (["*"] if "*" in ids else
                     [u for u in unit_ids if u in ids or groups.get(u) in ids])
        name = lambda lang: ([where(None, lang)] if locs_ == ["*"] else [where(u, lang) for u in locs_])  # noqa: E731
        out.stages.append(StageRow(stage_id=s.id, name_ar=s.name_ar, name_en=s.name_en, weight=float(s.weight),
                                   start=s0.get(sid, 0.0), end=s1.get(sid, 0.0), planned=ps.get(sid) if plan else None,
                                   locations_ar=name("ar"), locations_en=name("en"), days=len(w["days"]) if w else 0,
                                   qty=[{"qty": round(q, 2), "unit": u} for u, q in w["qty"].items()] if w else [],
                                   man_days=w["men"] if w else 0,
                                   teams=[k for k, _ in sorted(w["teams"].items(), key=lambda x: -x[1])][:4] if w else []))

    # ---- the QA registers (only what this user may see)
    t0 = datetime.combine(start, datetime.min.time(), TZ)
    t1 = datetime.combine(end + timedelta(days=1), datetime.min.time(), TZ)
    edge = min(t1, datetime.now(UTC))
    for rt in db.scalars(select(RecordType).where(RecordType.org_id.is_(None), RecordType.code.notin_(SKIP_TYPES))
                         .order_by(RecordType.sort)):
        p = Perms(c, a, rt)
        recs = [r for r in db.scalars(select(Record).where(Record.project_id == project_id, Record.record_type_id == rt.id,
                                                          Record.submitted_at.is_not(None), Record.submitted_at < t1))
                if can_see(c, a, p, r)]
        row = ReqRow(code=rt.code, name_ar=rt.name_ar, name_en=rt.name_en, submitted=0, answered=0, approved=0, returned=0,
                     open=0, overdue=0)
        for r in recs:
            if r.submitted_at >= t0:
                row.submitted += 1
            if r.answered_at and t0 <= r.answered_at < t1:
                row.answered += 1
                row.approved += r.state_category in APPROVED
                row.returned += r.state_category in ("revise_and_resubmit", "rejected")
            if r.state_category == "cancelled" or (r.answered_at and r.answered_at < t1):
                continue
            row.open += 1
            if r.due_at and r.due_at < edge:
                row.overdue += 1
                out.overdue.append(OverdueItem(id=r.id, number=r.number, title=r.title, code=rt.code, due_at=r.due_at,
                                               days=(edge - r.due_at).days))
        if row.submitted or row.answered or row.open:
            out.requests.append(row)
    out.overdue.sort(key=lambda x: -x.days)
    out.overdue = out.overdue[:60]
    return out


def _args(kind: str, day: date | None, start: date | None, end: date | None) -> tuple[date, date | None]:
    if kind == "custom":
        if start is None or end is None or end < start or (end - start).days >= MAX_DAYS:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_period")
        if start > datetime.now(TZ).date():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_period")
        return start, end
    return day or datetime.now(TZ).date(), None


Kind = Literal["week", "month", "custom"]


@router.get("/projects/{project_id}/period-report", response_model=PeriodOut)
def get_period(project_id: uuid.UUID, kind: Kind = "week", day: date | None = None, start: date | None = None,
               end: date | None = None, c: Ctx = Depends(ctx)):
    return build(c, project_id, kind, *_args(kind, day, start, end))


@router.get("/projects/{project_id}/period-report/pdf")
def period_pdf(project_id: uuid.UUID, kind: Kind = "week", day: date | None = None, start: date | None = None,
               end: date | None = None, lang: Literal["ar", "en"] = Query("ar"), c: Ctx = Depends(ctx)):
    from app.reports.period_pdf import render_period_pdf
    out = build(c, project_id, kind, *_args(kind, day, start, end))
    pdf = render_period_pdf(c, project_access(c, project_id), out, lang)
    name = f"{ {'week': 'weekly', 'month': 'monthly'}.get(kind, 'period') }-{out.start.isoformat()}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})
