"""Time programme: the contractor enters it (floor cycle, by hand or imported), supervision approves it."""
import io
import uuid
from datetime import date

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.access import project_access, require
from app.core.deps import Ctx, ctx
from app.core.programme import match, read_file
from app.models.programme import Programme
from app.models.records import Record, RecordType
from app.models.structure import ProjectLocation, ProjectStage, ProjectStageTopic

router = APIRouter(tags=["programme"])

APPROVED = ("approved", "approved_as_noted")


class Line(BaseModel):
    stage_id: uuid.UUID
    location_id: uuid.UUID | None = None
    start: date
    finish: date


class Cycle(BaseModel):
    stage_id: uuid.UUID
    start: date | None = None
    duration: int = Field(default=0, ge=0, le=3650)  # days per floor
    lag: int = Field(default=0, ge=0, le=3650)  # days until the next floor starts
    link: str = Field(default="fs", pattern="^(fs|ss)$")  # lag counted after the floor finishes, or from its start
    # optional: the stage starts relative to an earlier one, floor by floor (then "start" is computed)
    pred: uuid.UUID | None = None
    rel: str = Field(default="after_end", pattern="^(after_end|after_start|before_end|before_start)$")
    pred_days: int = Field(default=0, ge=0, le=3650)


class ProgrammeIO(BaseModel):
    lines: list[Line] = Field(default=[], max_length=5000)
    cycles: list[Cycle] = Field(default=[], max_length=200)
    source: str = Field(default="manual", pattern="^(manual|cycle|import)$")


class ProgrammeOut(ProgrammeIO):
    can_edit: bool
    start: date | None
    finish: date | None


class ImportRow(BaseModel):
    name: str
    location: str | None
    path: list[str]
    start: date | None
    finish: date | None
    stage_id: uuid.UUID | None
    location_id: uuid.UUID | None


class ProgrammeRev(BaseModel):
    id: uuid.UUID
    number: str
    rev_no: int
    state_category: str
    state_name_ar: str
    state_name_en: str


class ProgrammeSummary(BaseModel):
    revisions: list[ProgrammeRev]
    baseline_id: uuid.UUID | None
    current_id: uuid.UUID | None
    can_create: bool


def _rt(db) -> RecordType:
    return db.scalar(select(RecordType).where(RecordType.org_id.is_(None), RecordType.code == "programme"))


def programmes(db, project_id) -> tuple[Programme | None, Programme | None]:
    """(baseline, current): the first and the latest approved revisions."""
    rt = _rt(db)
    rows = db.execute(select(Record, Programme).join(Programme, Programme.record_id == Record.id)
                      .where(Record.project_id == project_id, Record.record_type_id == rt.id,
                             Record.state_category.in_(APPROVED)).order_by(Record.rev_no)).all()
    if not rows:
        return None, None
    return rows[0][1], rows[-1][1]


def _load_prg(c: Ctx, record_id: uuid.UUID):
    from app.api.records import _load
    rec, a, rt, p = _load(c, record_id)
    if rt.code != "programme":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    prg = c.db.get(Programme, rec.id)
    if prg is None:
        prg = Programme(record_id=rec.id, project_id=rec.project_id)
        c.db.add(prg)
        c.db.flush()
    return rec, a, rt, p, prg


def _out(rec, p, prg) -> ProgrammeOut:
    lines = [Line(**x) for x in prg.lines]
    return ProgrammeOut(lines=lines, cycles=[Cycle(**x) for x in prg.cycles], source=prg.source,
                        can_edit=rec.state_category == "draft" and p.can("edit", rec),
                        start=min((x.start for x in lines), default=None), finish=max((x.finish for x in lines), default=None))


@router.get("/projects/{project_id}/programme", response_model=ProgrammeSummary)
def summary(project_id: uuid.UUID, c: Ctx = Depends(ctx)):
    from app.api.records import Perms, can_see
    from app.models.records import WorkflowState
    a = project_access(c, project_id)
    rt = _rt(c.db)
    p = Perms(c, a, rt)
    recs = [r for r in c.db.scalars(select(Record).where(Record.project_id == project_id, Record.record_type_id == rt.id)
                                    .order_by(Record.rev_no.desc())) if can_see(c, a, p, r)]
    states = {s.id: s for s in c.db.scalars(select(WorkflowState).where(WorkflowState.id.in_({r.state_id for r in recs})))}
    approved = sorted([r for r in recs if r.state_category in APPROVED], key=lambda r: r.rev_no)
    live = [r for r in recs if r.state_category != "cancelled"]
    return ProgrammeSummary(
        revisions=[ProgrammeRev(id=r.id, number=r.number, rev_no=r.rev_no, state_category=r.state_category,
                                state_name_ar=states[r.state_id].name_ar, state_name_en=states[r.state_id].name_en) for r in recs],
        baseline_id=approved[0].id if approved else None, current_id=approved[-1].id if approved else None,
        can_create=not live and a.party is not None and p.can("create"))


@router.post("/projects/{project_id}/programme", status_code=201)
def create(project_id: uuid.UUID, c: Ctx = Depends(ctx)):
    """The project's one programme (R0); its updates are new revisions of it."""
    from app.api.records import create_record
    from app.schemas.records import RecordIn
    a = project_access(c, project_id)
    rt = _rt(c.db)
    if c.db.scalar(select(Record.id).where(Record.project_id == project_id, Record.record_type_id == rt.id,
                                           Record.state_category != "cancelled").limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "programme_exists")
    rec = create_record(project_id, RecordIn(record_type="programme", number=f"{a.project.code}-PRG",
                                             title="البرنامج الزمني للمشروع"), c)
    c.db.add(Programme(record_id=rec.id, project_id=project_id))
    c.db.flush()
    return {"id": str(rec.id)}


@router.get("/records/{record_id}/programme", response_model=ProgrammeOut)
def get_programme(record_id: uuid.UUID, c: Ctx = Depends(ctx)):
    rec, _, _, p, prg = _load_prg(c, record_id)
    return _out(rec, p, prg)


@router.put("/records/{record_id}/programme", response_model=ProgrammeOut)
def put_programme(record_id: uuid.UUID, body: ProgrammeIO, c: Ctx = Depends(ctx)):
    rec, a, _, p, prg = _load_prg(c, record_id)
    require(rec.state_category == "draft" and p.can("edit", rec), "cannot_edit")
    stages = {s.id: s for s in c.db.scalars(select(ProjectStage).where(ProjectStage.project_id == rec.project_id))}
    units = set(c.db.scalars(select(ProjectLocation.id).where(ProjectLocation.project_id == rec.project_id,
                                                              ProjectLocation.kind == "unit")))
    seen, lines = set(), []
    for x in body.lines:
        st = stages.get(x.stage_id)
        if st is None or (st.scope != "whole" and (x.location_id is None or x.location_id not in units)):
            continue  # a stage or floor removed from the structure since: the cell counts nowhere, drop it
        if x.finish < x.start:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "programme_finish_before_start")
        loc = None if st.scope == "whole" else x.location_id
        key = (x.stage_id, loc)
        if key in seen:
            continue
        seen.add(key)
        lines.append({"stage_id": str(x.stage_id), "location_id": str(loc) if loc else None,
                      "start": x.start.isoformat(), "finish": x.finish.isoformat()})
    prg.lines = lines
    prg.cycles = [{"stage_id": str(x.stage_id), "start": x.start.isoformat() if x.start else None,
                   "duration": x.duration, "lag": x.lag, "link": x.link, "pred": str(x.pred) if x.pred in stages else None,
                   "rel": x.rel, "pred_days": x.pred_days} for x in body.cycles if x.stage_id in stages]
    prg.source = body.source
    from app.api.records import _audit
    _audit(c, rec, "programme", {"lines": len(lines), "source": body.source}, a)
    c.db.flush()
    return _out(rec, p, prg)


@router.post("/records/{record_id}/programme/import", response_model=list[ImportRow])
def import_file(record_id: uuid.UUID, file: UploadFile = File(...), c: Ctx = Depends(ctx)):
    """Read an Excel (the template, or an MS Project / P6 export), MS Project XML or P6 XER file. Nothing is saved:
    the rows come back with the stage and floor their names suggest, for the engineer to check."""
    rec, _, _, p, _ = _load_prg(c, record_id)
    require(rec.state_category == "draft" and p.can("edit", rec), "cannot_edit")
    data = file.file.read(20 * 1024 * 1024 + 1)
    if len(data) > 20 * 1024 * 1024:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "file_too_large")
    try:
        rows = read_file(file.filename or "", data)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    except Exception:  # a damaged or foreign file
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "programme_file_unreadable") from None
    if not rows:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "programme_file_empty")
    stages = list(c.db.scalars(select(ProjectStage).where(ProjectStage.project_id == rec.project_id, ProjectStage.is_active)
                               .order_by(ProjectStage.sort)))
    topics = list(c.db.scalars(select(ProjectStageTopic).where(ProjectStageTopic.project_id == rec.project_id,
                                                               ProjectStageTopic.is_active)))
    units = list(c.db.scalars(select(ProjectLocation).where(ProjectLocation.project_id == rec.project_id,
                                                            ProjectLocation.kind == "unit", ProjectLocation.is_active)))
    return match(rows[:3000], stages, topics, units)


@router.get("/projects/{project_id}/programme/template")
def template(project_id: uuid.UUID, lang: str = "ar", c: Ctx = Depends(ctx)):
    """An Excel sheet with one row per cell of the project, to fill the dates in."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    a = project_access(c, project_id)
    ar = lang != "en"
    stages = list(c.db.scalars(select(ProjectStage).where(ProjectStage.project_id == project_id, ProjectStage.is_active)
                               .order_by(ProjectStage.sort)))
    groups = {g.id: g for g in c.db.scalars(select(ProjectLocation).where(ProjectLocation.project_id == project_id,
                                                                          ProjectLocation.kind == "group"))}
    units = sorted(c.db.scalars(select(ProjectLocation).where(ProjectLocation.project_id == project_id,
                                                              ProjectLocation.kind == "unit", ProjectLocation.is_active)),
                   key=lambda u: (groups[u.parent_id].sort if u.parent_id in groups else 0, u.sort))
    wb = Workbook()
    ws = wb.active
    ws.title = "Programme"
    ws.sheet_view.rightToLeft = ar
    ws.append(["المرحلة", "الموقع", "البداية", "النهاية"] if ar else ["Stage", "Location", "Start", "Finish"])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F3A5F")
    for s in stages:
        name = s.name_ar if ar else s.name_en
        if s.scope == "whole" or not units:
            ws.append([name, "كل المشروع" if ar else "Whole project", None, None])
        else:
            from app.models.structure import stage_units
            for u in stage_units(s, units):
                ws.append([name, u.name_ar if ar else u.name_en, None, None])
    for col, w in zip("ABCD", (34, 22, 14, 14)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=4):
        for cell in row:
            cell.number_format = "yyyy-mm-dd"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{a.project.code}-programme.xlsx"'})


@router.get("/records/{record_id}/programme/xlsx")
def export_xlsx(record_id: uuid.UUID, lang: str = "ar", c: Ctx = Depends(ctx)):
    """The programme as Excel: the dates (re-importable) and a week-by-week bar sheet."""
    from datetime import timedelta
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from app.reports.record_pdf import programme_view
    rec, _, _, _, prg = _load_prg(c, record_id)
    ar = lang != "en"
    view = programme_view(c.db, rec.project_id, prg.lines, "ar" if ar else "en", prg.cycles)
    cpm_on = bool(view and view.get("cpm"))
    wb = Workbook()
    ws = wb.active
    ws.title = "Programme"
    ws.sheet_view.rightToLeft = ar
    head = Font(bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="1F3A5F")
    ws.append((["المرحلة", "الموقع", "البداية", "النهاية", "المدة (يوم)"] if ar else ["Stage", "Location", "Start", "Finish", "Days"])
              + ((["الهامش (يوم)"] if ar else ["Float (days)"]) if cpm_on else []))
    red_font = Font(bold=True, color="C92A2A")
    for cell in ws[1]:
        cell.font, cell.fill = head, fill
    stage_fill = PatternFill("solid", fgColor="EEF2F7")
    last_stage = ""
    rows = view["rows"] if view else []
    for r in rows:
        if r["kind"] == "stage":
            last_stage = r["stage"]
            if r["where"]:  # a whole-project stage: one importable row
                ws.append([r["stage"], r["where"], r["s"], r["f"], r["days"]] + ([r["float"]] if cpm_on else []))
                for cell in ws[ws.max_row]:
                    cell.fill = stage_fill
            continue
        ws.append([last_stage, r["where"], r["s"], r["f"], r["days"]] + ([r["float"]] if cpm_on else []))
        if r.get("crit"):
            for cell in ws[ws.max_row]:
                cell.font = red_font
    for col, w in zip("ABCDEF", (34, 22, 13, 13, 11, 12)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2, min_col=3, max_col=4):
        for cell in row:
            cell.number_format = "yyyy-mm-dd"
    # week-by-week bars
    if rows:
        g = wb.create_sheet("Gantt")
        g.sheet_view.rightToLeft = ar
        lo = min(r["s"] for r in rows)
        lo = lo - timedelta(days=lo.weekday())  # Monday
        hi = max(r["f"] for r in rows)
        weeks = []
        d = lo
        while d <= hi:
            weeks.append(d)
            d += timedelta(days=7)
        g.append(["المرحلة / الموقع" if ar else "Stage / location", "البداية" if ar else "Start", "النهاية" if ar else "Finish",
                  *[w.strftime("%d/%m/%y") for w in weeks]])
        for cell in g[1]:
            cell.font, cell.fill = Font(bold=True, color="FFFFFF", size=8), fill
            cell.alignment = Alignment(text_rotation=90 if cell.column > 3 else 0, horizontal="center")
        bar, sbar, cbar = PatternFill("solid", fgColor="2B5D8F"), PatternFill("solid", fgColor="343A40"), PatternFill("solid", fgColor="E03131")
        for r in rows:
            label = r["stage"] + (f" · {r['where']}" if r["where"] and r["kind"] == "stage" else "") if r["kind"] == "stage" else f"   {r['where']}"
            g.append([label, r["s"], r["f"]])
            i = g.max_row
            if r["kind"] == "stage":
                g.cell(i, 1).font = Font(bold=True)
                for k in range(1, 4 + len(weeks)):
                    if k <= 3:
                        g.cell(i, k).fill = stage_fill
            for k, w in enumerate(weeks):
                if w <= r["f"] and w + timedelta(days=6) >= r["s"]:
                    g.cell(i, 4 + k).fill = sbar if r["kind"] == "stage" and not r.get("crit") else cbar if r.get("crit") else bar
            g.cell(i, 2).number_format = g.cell(i, 3).number_format = "yyyy-mm-dd"
        g.column_dimensions["A"].width = 34
        g.column_dimensions["B"].width = g.column_dimensions["C"].width = 11
        for k in range(len(weeks)):
            g.column_dimensions[get_column_letter(4 + k)].width = 2.6
        g.row_dimensions[1].height = 48
        g.freeze_panes = "D2"
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                             headers={"Content-Disposition": f'attachment; filename="{rec.number}-R{rec.rev_no}.xlsx"'})
