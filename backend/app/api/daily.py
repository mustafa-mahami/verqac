"""Daily site report: one per project per day, written by the contractor, approved or returned by supervision.
Approved reports set the progress of the stage x location cells; the project % follows the stage weights."""
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.core.access import project_access, require
from app.core.audit import audit
from app.core.deps import Ctx, ctx
from app.models.core import Project
from app.models.daily import DailyReport, ProgressCell, ProgressSnapshot
from app.models.records import Record, RecordType
from app.models.structure import ProjectLocation, ProjectStage

router = APIRouter(tags=["daily"])
TZ = ZoneInfo("Asia/Hebron")

GROUPS = ("supervision", "contractor", "labour")
CAUSES = ("weather", "materials", "design", "approval", "equipment", "labour", "utilities", "access", "other")


# ----------------------------------------------------------------------------- schemas
class CrewLine(BaseModel):
    group: Literal["supervision", "contractor", "labour"]
    sub: str | None = Field(default=None, max_length=150)  # subcontractor (labour / contractor staff)
    name: str = Field(max_length=150)  # person (names mode) or trade / description (counts mode), Arabic
    name_en: str | None = Field(default=None, max_length=150)
    role: str | None = Field(default=None, max_length=150)  # position of a named person, Arabic
    role_en: str | None = Field(default=None, max_length=150)
    count: int = Field(default=1, ge=0, le=5000)
    hours: float | None = Field(default=None, ge=0, le=24)


class EquipLine(BaseModel):
    name: str = Field(max_length=150)
    count: int = Field(default=1, ge=0, le=1000)
    hours: float | None = Field(default=None, ge=0, le=24)
    idle_hours: float | None = Field(default=None, ge=0, le=24)
    note: str | None = Field(default=None, max_length=300)


class MaterialLine(BaseModel):
    material: str = Field(max_length=200)
    qty: float | None = None
    unit: str | None = Field(default=None, max_length=20)
    supplier: str | None = Field(default=None, max_length=150)
    delivery_note: str | None = Field(default=None, max_length=60)
    submittal_id: uuid.UUID | None = None
    mir_id: uuid.UUID | None = None


class WorkLine(BaseModel):
    stage_id: uuid.UUID | None = None
    topic_id: uuid.UUID | None = None
    location_ids: list[uuid.UUID] = []
    all_locations: bool = False
    description: str | None = Field(default=None, max_length=1000)
    qty: float | None = None
    unit: str | None = Field(default=None, max_length=20)
    crew: int | None = Field(default=None, ge=0, le=5000)
    progress: float | None = Field(default=None, ge=0, le=100)  # cumulative % of the cell(s) after today's work


class DelayLine(BaseModel):
    cause: Literal["weather", "materials", "design", "approval", "equipment", "labour", "utilities", "access", "other"] = "other"
    hours: float | None = Field(default=None, ge=0, le=24)
    description: str | None = Field(default=None, max_length=1000)
    link_id: uuid.UUID | None = None


class Hse(BaseModel):
    incidents: int = Field(default=0, ge=0)
    near_misses: int = Field(default=0, ge=0)
    toolbox: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=2000)


class DailyIO(BaseModel):
    shift: Literal["day", "night", "both"] = "day"
    work_status: Literal["normal", "partial", "stopped"] = "normal"
    stop_reason: str | None = Field(default=None, max_length=300)
    weather: Literal["sunny", "cloudy", "rain", "storm", "snow", "fog", "dust", "hot", "cold"] | None = None
    temp_min: float | None = Field(default=None, ge=-30, le=60)
    temp_max: float | None = Field(default=None, ge=-30, le=60)
    wind: Literal["calm", "moderate", "strong"] | None = None
    hours_from: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    hours_to: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    crew: list[CrewLine] = Field(default=[], max_length=300)
    equipment: list[EquipLine] = Field(default=[], max_length=200)
    materials: list[MaterialLine] = Field(default=[], max_length=200)
    works: list[WorkLine] = Field(default=[], max_length=300)
    planned: list[WorkLine] = Field(default=[], max_length=300)
    delays: list[DelayLine] = Field(default=[], max_length=50)
    hse: Hse = Hse()
    visitors: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)


class QaCount(BaseModel):
    code: str
    name_ar: str
    name_en: str
    submitted: int
    answered: int


class DailyOut(DailyIO):
    record_id: uuid.UUID
    report_date: date
    day_no: int | None = None  # day of the project, counted from its start date
    weekday: int = 0  # 0 = Sunday ... 6 = Saturday
    day_off: str | None = None  # weekend | holiday
    holiday: str | None = None  # the holiday's name
    can_edit: bool
    qa: list[QaCount] = []
    current: dict[str, float] = {}  # "stage:location" -> approved % before this report
    totals: dict[str, int] = {}


class ListItem(BaseModel):
    """A suggested person / trade / subcontractor / equipment, in both languages."""
    ar: str = Field(max_length=150)
    en: str = Field(default="", max_length=150)
    role_ar: str | None = Field(default=None, max_length=150)  # people: position
    role_en: str | None = Field(default=None, max_length=150)
    active: bool = True

    @classmethod
    def of(cls, x):
        return cls(ar=x, en=x) if isinstance(x, str) else cls(**x)


class DailySettings(BaseModel):
    crew: dict[str, Literal["names", "counts"]] = {"supervision": "names", "contractor": "counts", "labour": "counts"}
    link_materials: bool = False
    # per crew group two lists: <group>_names (people, "names" mode) and <group>_desc (positions / trades, "counts" mode);
    # plus subcontractors and equipment
    lists: dict[str, list[ListItem]] = {}


LIST_KEYS = {*(f"{g}_{m}" for g in ("supervision", "contractor", "labour") for m in ("names", "desc")), "subcontractors", "equipment"}


class NewDaily(BaseModel):
    report_date: date
    copy_previous: bool = True


class Cell(BaseModel):
    stage_id: uuid.UUID
    location_id: uuid.UUID | None
    progress: float
    progress_on: date | None = None
    started_on: date | None = None
    finished_on: date | None = None
    planned: float | None = None  # today, by the current programme
    plan_start: date | None = None
    plan_finish: date | None = None
    status: str | None = None  # not_started | on_track | ahead | late | done


class ProgressOut(BaseModel):
    project: float
    stages: dict[str, float]
    cells: list[Cell]
    snapshots: list[dict]
    as_of: date | None
    # the programme (absent until one is approved)
    planned: float | None = None  # project % planned for today, current programme
    planned_baseline: float | None = None
    spi: float | None = None  # actual / planned
    planned_stages: dict[str, float] = {}
    plan_curve: list[dict] = []  # current programme, week by week
    baseline_curve: list[dict] = []  # the first approved programme, when it differs
    plan_start: date | None = None
    plan_finish: date | None = None
    baseline_finish: date | None = None
    programme_id: uuid.UUID | None = None
    baseline_id: uuid.UUID | None = None
    late: list[Cell] = []  # behind plan, worst first


# ----------------------------------------------------------------------------- settings
def daily_settings(project: Project) -> DailySettings:
    raw = dict((project.settings or {}).get("daily", {}))
    lists = {}
    for k, v in (raw.get("lists") or {}).items():
        if k in GROUPS:  # older settings: one list per group (people for staff, trades for labour)
            k = f"{k}_desc" if k == "labour" else f"{k}_names"
        lists.setdefault(k, []).extend(ListItem.of(x) for x in v)  # older lists were plain text
    raw["lists"] = lists
    return DailySettings(**raw)
    return DailySettings(**raw)


@router.get("/projects/{project_id}/daily-settings", response_model=DailySettings)
def get_daily_settings(project_id: uuid.UUID, c: Ctx = Depends(ctx)):
    return daily_settings(project_access(c, project_id).project)


@router.put("/projects/{project_id}/daily-settings", response_model=DailySettings)
def put_daily_settings(project_id: uuid.UUID, body: DailySettings, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    if set(body.crew) - set(GROUPS) or set(body.lists) - LIST_KEYS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_settings")
    clean = {}
    for k, v in body.lists.items():
        seen, rows = set(), []
        for x in v:
            ar, en = x.ar.strip(), x.en.strip()
            if not (ar or en) or (ar or en) in seen:
                continue
            seen.add(ar or en)
            item = {**x.model_dump(), "ar": ar or en, "en": en or ar}
            if not k.endswith("_names"):
                item["role_ar"] = item["role_en"] = None  # positions only for people
            rows.append(item)
        clean[k] = rows[:300]
    a.project.settings = {**(a.project.settings or {}), "daily": {**body.model_dump(), "lists": clean}}
    c.db.flush()
    return daily_settings(a.project)


# ----------------------------------------------------------------------------- progress
def _units(db, project_id) -> list[ProjectLocation]:
    return list(db.scalars(select(ProjectLocation).where(ProjectLocation.project_id == project_id, ProjectLocation.kind == "unit",
                                                         ProjectLocation.is_active).order_by(ProjectLocation.sort)))


def _cells_of(db, project_id, line: dict, stages: dict) -> list[tuple]:
    """(stage, location) cells a work line covers: a whole-project stage has one cell; buildings mean all their floors."""
    st = stages.get(str(line.get("stage_id")))
    if st is None:
        return []
    if st.scope == "whole":
        return [(st.id, None)]
    units = _units(db, project_id)
    if line.get("all_locations"):
        return [(st.id, u.id) for u in units]
    ids = {str(x) for x in line.get("location_ids") or []}
    return [(st.id, u.id) for u in units if str(u.id) in ids or str(u.parent_id) in ids]


def project_progress(db, project_id) -> ProgressOut:
    stages = [s for s in db.scalars(select(ProjectStage).where(ProjectStage.project_id == project_id, ProjectStage.is_active))]
    units = _units(db, project_id)
    cells = list(db.scalars(select(ProgressCell).where(ProgressCell.project_id == project_id)))
    by = {(c.stage_id, c.location_id): float(c.progress) for c in cells}
    stage_pct: dict[str, float] = {}
    total_w = sum(float(s.weight) for s in stages) or 0
    project = 0.0
    for s in stages:
        if s.scope == "whole" or not units:
            pct = by.get((s.id, None), 0.0)
        else:
            pct = sum(by.get((s.id, u.id), 0.0) for u in units) / len(units)
        stage_pct[str(s.id)] = round(pct, 1)
        if total_w:
            project += float(s.weight) * pct / total_w
    snaps = [{"day": x.day.isoformat(), "actual": float(x.actual), "planned": float(x.planned) if x.planned is not None else None}
             for x in db.scalars(select(ProgressSnapshot).where(ProgressSnapshot.project_id == project_id).order_by(ProgressSnapshot.day))]
    as_of = max((c.progress_on for c in cells if c.progress_on), default=None)
    out = ProgressOut(project=round(project, 1), stages=stage_pct, as_of=as_of, snapshots=snaps,
                      cells=[Cell(stage_id=c.stage_id, location_id=c.location_id, progress=float(c.progress), progress_on=c.progress_on,
                                  started_on=c.started_on, finished_on=c.finished_on) for c in cells])
    _with_plan(db, project_id, out, stages, units, by)
    return out


def _with_plan(db, project_id, out: ProgressOut, stages, units, actual: dict) -> None:
    """Planned against actual, from the approved programme (current = latest approved, baseline = the first)."""
    from app.api.programme import programmes
    from app.core.programme import plan_cells, planned_at, series, status
    base, cur = programmes(db, project_id)
    if cur is None:
        return
    today = datetime.now(TZ).date()
    plan = plan_cells(cur.lines)
    if not plan:
        return
    out.programme_id, out.baseline_id = cur.record_id, base.record_id
    out.planned, out.planned_stages = planned_at(plan, stages, units, today)
    out.spi = round(out.project / out.planned, 2) if out.planned else None
    out.plan_curve = series(plan, stages, units)
    out.plan_start = min(s for s, _ in plan.values())
    out.plan_finish = max(f for _, f in plan.values())
    if base.record_id != cur.record_id:
        bplan = plan_cells(base.lines)
        if bplan:
            out.planned_baseline = planned_at(bplan, stages, units, today)[0]
            out.baseline_curve = series(bplan, stages, units)
            out.baseline_finish = max(f for _, f in bplan.values())
    # every cell of the matrix, worked on or not: planned today and its status
    keys = [(s.id, None) if s.scope == "whole" or not units else (s.id, u.id) for s in stages
            for u in ([None] if s.scope == "whole" or not units else units)]
    have = {(c.stage_id, c.location_id): c for c in out.cells}
    cells, late = [], []
    from app.core.programme import cell_planned
    for sid, lid in keys:
        p = plan.get((str(sid), str(lid) if lid else None))
        c = have.get((sid, lid)) or Cell(stage_id=sid, location_id=lid, progress=0.0)
        if p is not None:
            c.plan_start, c.plan_finish = p
            c.planned = cell_planned(*p, today)
            c.status = status(c.planned, actual.get((sid, lid), 0.0))
            if c.status == "late":
                late.append(c)
        cells.append(c)
    out.cells = cells
    out.late = sorted(late, key=lambda c: (c.progress - (c.planned or 0), c.plan_finish or today))[:50]


def check_works(db, rec: Record) -> None:
    """Before submitting: a % on a per-location stage needs its locations, or it would count nowhere."""
    d = db.get(DailyReport, rec.id)
    if d is None:
        return
    stages = {str(s.id): s for s in db.scalars(select(ProjectStage).where(ProjectStage.project_id == d.project_id))}
    for line in d.works:
        st = stages.get(str(line.get("stage_id")))
        if st is not None and line.get("progress") is not None and not _cells_of(db, d.project_id, line, stages):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "dr_location_required")


def rebuild_progress(db, project_id) -> None:
    """Start again from the approved reports, oldest first: after the stages or locations changed."""
    db.execute(delete(ProgressCell).where(ProgressCell.project_id == project_id))
    db.execute(delete(ProgressSnapshot).where(ProgressSnapshot.project_id == project_id))
    db.flush()
    recs = db.scalars(select(Record).join(DailyReport, DailyReport.record_id == Record.id)
                      .where(Record.project_id == project_id, Record.state_category == "approved")
                      .order_by(DailyReport.report_date))
    for rec in recs:
        apply_progress(db, rec)


def apply_progress(db, rec: Record) -> None:
    """Supervision approved the report: its work lines set their cells (the latest report date wins)."""
    d = db.get(DailyReport, rec.id)
    if d is None:
        return
    stages = {str(s.id): s for s in db.scalars(select(ProjectStage).where(ProjectStage.project_id == d.project_id))}
    for line in d.works:
        cells = _cells_of(db, d.project_id, line, stages)
        for stage_id, loc_id in cells:
            cell = db.scalar(select(ProgressCell).where(ProgressCell.project_id == d.project_id, ProgressCell.stage_id == stage_id,
                                                        ProgressCell.location_id.is_(None) if loc_id is None
                                                        else ProgressCell.location_id == loc_id))
            if cell is None:
                cell = ProgressCell(project_id=d.project_id, stage_id=stage_id, location_id=loc_id, progress=Decimal(0))
                db.add(cell)
            if cell.started_on is None or cell.started_on > d.report_date:
                cell.started_on = d.report_date  # work on the cell, with or without a %
            pct = line.get("progress")
            if pct is None or (cell.progress_on and cell.progress_on > d.report_date):
                continue
            cell.progress, cell.progress_on, cell.record_id = Decimal(str(pct)), d.report_date, rec.id
            cell.finished_on = d.report_date if pct >= 100 else None
    db.flush()
    pct = project_progress(db, d.project_id).project
    db.execute(insert(ProgressSnapshot).values(project_id=d.project_id, day=d.report_date, actual=pct)
               .on_conflict_do_update(index_elements=["project_id", "day"], set_={"actual": pct}))


@router.get("/projects/{project_id}/progress", response_model=ProgressOut)
def get_progress(project_id: uuid.UUID, c: Ctx = Depends(ctx)):
    project_access(c, project_id)
    return project_progress(c.db, project_id)


@router.post("/projects/{project_id}/progress/rebuild", response_model=ProgressOut)
def rebuild(project_id: uuid.UUID, c: Ctx = Depends(ctx)):
    """Recount the matrix and the curve from the approved daily reports (the project manager)."""
    a = project_access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    rebuild_progress(c.db, project_id)
    audit(c.db, entity="project", action="progress_rebuild", entity_id=project_id, actor=c.user.id,
          org_id=a.project.owner_org_id, project_id=project_id, changes={}, ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return project_progress(c.db, project_id)


# ----------------------------------------------------------------------------- reports
def _rt(c: Ctx) -> RecordType:
    return c.db.scalar(select(RecordType).where(RecordType.org_id.is_(None), RecordType.code == "daily_report"))


def _strip(line: dict) -> dict:
    return {k: (str(v) if isinstance(v, uuid.UUID) else [str(x) for x in v] if k == "location_ids" else v)
            for k, v in line.items()}


@router.post("/projects/{project_id}/daily-reports", status_code=201)
def new_daily(project_id: uuid.UUID, body: NewDaily, c: Ctx = Depends(ctx)):
    """The report of a day. Crew and equipment are copied from the previous report, and yesterday's plan
    becomes today's work list (without quantities or %), so the engineer only corrects what changed."""
    from app.api.records import create_record
    from app.schemas.records import RecordIn
    if body.report_date > datetime.now(TZ).date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "dr_future")
    a = project_access(c, project_id)
    taken = c.db.scalar(select(func.count()).select_from(DailyReport).join(Record, Record.id == DailyReport.record_id)
                        .where(DailyReport.project_id == project_id, DailyReport.report_date == body.report_date,
                               Record.state_category != "cancelled"))
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "dr_exists")
    base = f"DR-{body.report_date.isoformat()}"
    n = c.db.scalar(select(func.count()).select_from(Record).where(Record.project_id == project_id, Record.number.like(base + "%")))
    rec = create_record(project_id, RecordIn(record_type="daily_report", number=base if not n else f"{base}-{n + 1}",
                                             title=f"التقرير اليومي {body.report_date.isoformat()}"), c)
    d = DailyReport(record_id=rec.id, project_id=project_id, report_date=body.report_date)
    cal = (a.project.settings or {}).get("calendar", {})
    if cal.get("work_start") and cal.get("work_end"):  # the project's working hours
        d.hours_from, d.hours_to = cal["work_start"], cal["work_end"]
    if body.copy_previous:
        prev = c.db.scalar(select(DailyReport).join(Record, Record.id == DailyReport.record_id)
                           .where(DailyReport.project_id == project_id, DailyReport.report_date < body.report_date,
                                  Record.state_category != "cancelled").order_by(DailyReport.report_date.desc()).limit(1))
        if prev is not None:
            d.shift = prev.shift
            if not d.hours_from:
                d.hours_from, d.hours_to = prev.hours_from, prev.hours_to
            d.crew, d.equipment = prev.crew, prev.equipment
            d.works = [{**x, "qty": None, "progress": None} for x in prev.planned]
    c.db.add(d)
    c.db.flush()
    return {"id": str(rec.id)}


def _load_daily(c: Ctx, record_id: uuid.UUID):
    from app.api.records import _load
    rec, a, rt, p = _load(c, record_id)
    if rt.code != "daily_report":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    d = c.db.get(DailyReport, rec.id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return rec, a, rt, p, d


def _qa(c: Ctx, project_id, day: date) -> list[QaCount]:
    """What happened in the QA registers that day (local time): submitted and answered requests per type."""
    start = datetime.combine(day, datetime.min.time(), TZ)
    end = start + timedelta(days=1)
    out = []
    for rt in c.db.scalars(select(RecordType).where(RecordType.org_id.is_(None), RecordType.code != "daily_report")
                           .order_by(RecordType.sort)):
        sub = c.db.scalar(select(func.count()).select_from(Record).where(Record.project_id == project_id, Record.record_type_id == rt.id,
                                                                       Record.submitted_at >= start, Record.submitted_at < end))
        ans = c.db.scalar(select(func.count()).select_from(Record).where(Record.project_id == project_id, Record.record_type_id == rt.id,
                                                                       Record.answered_at >= start, Record.answered_at < end))
        if sub or ans:
            out.append(QaCount(code=rt.code, name_ar=rt.name_ar, name_en=rt.name_en, submitted=sub, answered=ans))
    return out


def day_info(c: Ctx, project_id, day: date) -> dict:
    """Report no. (day of the project) and whether the day is a weekly day off or an official holiday."""
    from app.core.workcal import day_off
    project = c.db.get(Project, project_id)
    off = day_off(c.db, project, day)
    start = project.start_date
    return {"day_no": (day - start).days + 1 if start and day >= start else None, "weekday": (day.weekday() + 1) % 7,
            "day_off": off[0] if off else None, "holiday": off[1] if off else None}


def _out(c: Ctx, rec, p, d: DailyReport) -> DailyOut:
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    cur = {}
    for cell in c.db.scalars(select(ProgressCell).where(ProgressCell.project_id == d.project_id)):
        cur[f"{cell.stage_id}:{cell.location_id or ''}"] = float(cell.progress)
    totals = {g: sum(int(x.get("count") or 0) for x in d.crew if x.get("group") == g) for g in GROUPS}
    totals["equipment"] = sum(int(x.get("count") or 0) for x in d.equipment)
    return DailyOut(record_id=rec.id, report_date=d.report_date,
                    can_edit=rec.state_category in ("draft", "revise_and_resubmit") and p.can("edit", rec),
                    shift=d.shift, work_status=d.work_status, stop_reason=d.stop_reason, weather=d.weather,
                    temp_min=f(d.temp_min), temp_max=f(d.temp_max), wind=d.wind, hours_from=d.hours_from, hours_to=d.hours_to,
                    crew=d.crew, equipment=d.equipment, materials=d.materials, works=d.works, planned=d.planned, delays=d.delays,
                    hse=Hse(**(d.hse or {})), visitors=d.visitors, notes=d.notes, qa=_qa(c, d.project_id, d.report_date),
                    current=cur, totals=totals, **day_info(c, d.project_id, d.report_date))


@router.get("/records/{record_id}/daily", response_model=DailyOut)
def get_daily(record_id: uuid.UUID, c: Ctx = Depends(ctx)):
    rec, a, rt, p, d = _load_daily(c, record_id)
    return _out(c, rec, p, d)


@router.put("/records/{record_id}/daily", response_model=DailyOut)
def put_daily(record_id: uuid.UUID, body: DailyIO, c: Ctx = Depends(ctx)):
    rec, a, rt, p, d = _load_daily(c, record_id)
    require(rec.state_category in ("draft", "revise_and_resubmit") and p.can("edit", rec), "locked_after_submit")
    stages = {s.id for s in c.db.scalars(select(ProjectStage).where(ProjectStage.project_id == rec.project_id))}
    for w in [*body.works, *body.planned]:
        if w.stage_id is not None and w.stage_id not in stages:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_stage")
        if w.progress is not None and w.stage_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "progress_needs_stage")
    for k in ("shift", "work_status", "stop_reason", "weather", "temp_min", "temp_max", "wind", "hours_from", "hours_to",
              "visitors", "notes"):
        setattr(d, k, getattr(body, k))
    d.crew = [x.model_dump() for x in body.crew if x.name.strip()]
    d.equipment = [x.model_dump() for x in body.equipment if x.name.strip()]
    d.materials = [_strip(x.model_dump()) for x in body.materials if x.material.strip()]
    d.works = [_strip(x.model_dump()) for x in body.works if x.stage_id or (x.description or "").strip()]
    d.planned = [_strip(x.model_dump()) for x in body.planned if x.stage_id or (x.description or "").strip()]
    d.delays = [_strip(x.model_dump()) for x in body.delays]
    d.hse = body.hse.model_dump()
    rec.updated_at = datetime.now(UTC)
    from app.api.records import _audit
    _audit(c, rec, "daily", {"works": len(d.works), "crew": sum(x["count"] for x in d.crew)}, a)
    c.db.flush()
    return _out(c, rec, p, d)
