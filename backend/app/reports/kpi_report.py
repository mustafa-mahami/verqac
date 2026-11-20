"""The QA/QC KPI scorecard as a PDF (print) or an Excel workbook, in Arabic or English."""
import io
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.access import ProjectAccess
from app.core.deps import Ctx
from app.models.core import Organization, ProjectParty
from app.reports.pdf import html_to_pdf, render_html
from app.reports.record_pdf import PARTY, _n, header_image

TZ = ZoneInfo("Asia/Hebron")
K_T = {
    "ar": {"title": "مؤشرات أداء الجودة (QA/QC KPIs)", "period": "فترة التقديم", "all": "منذ بداية المشروع", "disc": "التخصص",
           "all_disc": "كل التخصصات", "printed": "تاريخ الطباعة", "consultant": "الاستشاري", "summary": "الملخص",
           "on": "ضمن الهدف", "watch": "للمتابعة", "off": "خارج الهدف", "kpi": "المؤشر", "actual": "الفعلي", "target": "الهدف",
           "amber": "حدّ المتابعة", "status": "الحالة", "qmp": "مرجع QMP", "how": "طريقة الحساب", "info": "للمعلومة", "days": "يوم",
           "sec": {"submittal": "طلبات الاعتماد", "inspection": "طلبات الفحص", "test": "الفحوصات المخبرية", "ncr": "عدم المطابقة",
                   "rfi": "الاستيضاحات"},
           "by_disc": "حسب التخصص", "by_mat": "الفحوصات حسب المادة", "by_class": "الخرسانة حسب الفئة", "open_failed": "فحوصات راسبة بلا قرار",
           "c": {"discipline": "التخصص", "unique": "طلبات", "records": "إصدارات", "first_pass": "قبول من أول مرة", "approved": "معتمد",
                 "outstanding_n": "مُعاد/مرفوض", "pending": "بانتظار الرد", "review_days": "أيام الإشراف", "contractor_days": "أيام المقاول",
                 "issued": "صادر", "open": "مفتوح", "close_days": "أيام الإغلاق", "supervision_days": "أيام الإشراف",
                 "response_days": "أيام الرد", "material": "المادة", "tests": "فحوصات", "pass": "ناجح", "fail": "راسب",
                 "pass_rate": "نسبة النجاح", "grade": "الفئة", "fck": "fck", "reports": "تقارير", "failed": "راسب",
                 "specimens": "عينات 28 يوماً", "below": "دون fck", "number": "الرقم", "subject": "الموضوع"},
           "note": "محسوبة من السجلات المقدَّمة؛ المسودات والملغاة مستبعدة. الأخضر ضمن الهدف، والأصفر للمتابعة، وما بعده أحمر.",
           "sheet_score": "المؤشرات", "sheet_disc": "حسب التخصص", "sheet_tests": "الفحوصات"},
    "en": {"title": "QA/QC Key Performance Indicators", "period": "Submitted", "all": "Since the project start", "disc": "Discipline",
           "all_disc": "All disciplines", "printed": "Printed", "consultant": "Consultant", "summary": "Summary",
           "on": "On target", "watch": "Watch", "off": "Off target", "kpi": "KPI", "actual": "Actual", "target": "Target",
           "amber": "Watch limit", "status": "Status", "qmp": "QMP ref", "how": "How it is worked out", "info": "Info", "days": "d",
           "sec": {"submittal": "Submittals", "inspection": "Inspection requests", "test": "Laboratory tests", "ncr": "Non-conformance",
                   "rfi": "RFIs"},
           "by_disc": "By discipline", "by_mat": "Tests by material", "by_class": "Concrete by class", "open_failed": "Failed tests without a decision",
           "c": {"discipline": "Discipline", "unique": "Requests", "records": "Revisions", "first_pass": "First pass", "approved": "Approved",
                 "outstanding_n": "Returned", "pending": "Pending", "review_days": "Superv. days", "contractor_days": "Contr. days",
                 "issued": "Issued", "open": "Open", "close_days": "Close days", "supervision_days": "Superv. days",
                 "response_days": "Response days", "material": "Material", "tests": "Tests", "pass": "Pass", "fail": "Fail",
                 "pass_rate": "Pass %", "grade": "Class", "fck": "fck", "reports": "Reports", "failed": "Failed",
                 "specimens": "28-day specimens", "below": "Below fck", "number": "No.", "subject": "Subject"},
           "note": "Computed from submitted records; drafts and cancelled excluded. Green is on target, amber watch, beyond it red.",
           "sheet_score": "KPIs", "sheet_disc": "By discipline", "sheet_tests": "Tests"},
}
MAT = {"ar": {"CON": "الباطون", "STL": "حديد التسليح", "BC": "الطوب", "SOIL": "التربة", "ASP": "الإسفلت", "BLK": "الطوب",
              "TIL": "البلاط", "WP": "العزل", "MEP": "الكهروميكانيك", "OTH": "أخرى", "other": "أخرى"},
       "en": {"CON": "Concrete", "STL": "Steel", "BC": "Blocks", "SOIL": "Soil", "ASP": "Asphalt", "BLK": "Blocks", "TIL": "Tiles",
              "WP": "Waterproofing", "MEP": "MEP", "OTH": "Other", "other": "Other"}}
DISC_COLS = {
    "submittal": ["unique", "records", "first_pass", "approved", "outstanding_n", "pending", "review_days", "contractor_days"],
    "inspection": ["unique", "records", "first_pass", "approved", "outstanding_n", "pending", "review_days", "contractor_days"],
    "ncr": ["issued", "open", "close_days", "contractor_days", "supervision_days"],
    "rfi": ["issued", "open", "response_days"],
}
PCT_COLS = {"first_pass", "pass_rate"}
DAY_COLS = {"review_days", "contractor_days", "close_days", "supervision_days", "response_days"}


def fmt(unit: str, v, lang: str) -> str:
    if v is None:
        return "—"
    s = f"{v:g}" if isinstance(v, (int, float)) else str(v)
    if unit == "pct":
        return f"{s}%"
    if unit == "days":
        return f"{s} {K_T[lang]['days']}"
    return s


def col_unit(k: str) -> str:
    return "pct" if k in PCT_COLS else "days" if k in DAY_COLS else "count"


def _parties(c: Ctx, a: ProjectAccess, lang: str) -> dict:
    out = {}
    for p, o in c.db.execute(select(ProjectParty, Organization).outerjoin(Organization, Organization.id == ProjectParty.org_id)
                             .where(ProjectParty.project_id == a.project.id, ProjectParty.status != "removed")):
        out[p.kind] = _n(o, lang) if o else (p.placeholder_name or "")
    return out


def _scope(t: dict, date_from: date | None, date_to: date | None, disc_name: str | None) -> tuple[str, str]:
    period = t["all"] if not (date_from or date_to) else f"{date_from.isoformat() if date_from else '…'} → {date_to.isoformat() if date_to else '…'}"
    return period, disc_name or t["all_disc"]


def render_kpi_pdf(c: Ctx, a: ProjectAccess, data: dict, lang: str, date_from, date_to, disc_name) -> bytes:
    t = K_T[lang]
    parties = _parties(c, a, lang)
    counts = {"green": 0, "amber": 0, "red": 0}
    for k in data["kpis"]:
        if k["status"]:
            counts[k["status"]] += 1
    period, disc = _scope(t, date_from, date_to, disc_name)

    def target(k, key="green"):
        if k["direction"] == "info" or k[key] is None:
            return t["info"] if key == "green" else ""
        return ("≥ " if k["direction"] == "higher" else "≤ ") + fmt(k["unit"], k[key], lang)

    html = render_html(
        "kpi.html", lang=lang, t=t, d=data, header=header_image(c, a.project), party=PARTY[lang],
        contractor=parties.get("contractor", ""), consultant=parties.get("consultant", ""),
        project_name=_n(a.project, lang), project_code=a.project.code, period=period, disc=disc, counts=counts,
        printed=datetime.now(TZ).strftime("%Y-%m-%d %H:%M"), fmt=lambda u, v: fmt(u, v, lang), target=target,
        name=lambda x: x[f"name_{lang}"], formula=lambda x: x[f"formula_{lang}"], disc_cols=DISC_COLS, col_unit=col_unit,
        mat=lambda m: MAT[lang].get(m, m), sections=("submittal", "inspection", "test", "ncr", "rfi"))
    return html_to_pdf(html, footer_text=f"Verqac · {a.project.code} · QA/QC KPIs · {period}")


def kpi_xlsx(a: ProjectAccess, data: dict, lang: str, date_from, date_to, disc_name) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    t = K_T[lang]
    rtl = lang == "ar"
    head = PatternFill("solid", fgColor="EEF2F7")
    fills = {"green": PatternFill("solid", fgColor="D3F9D8"), "amber": PatternFill("solid", fgColor="FFF3BF"),
             "red": PatternFill("solid", fgColor="FFE3E3")}
    bold = Font(bold=True)
    wb = Workbook()
    period, disc = _scope(t, date_from, date_to, disc_name)

    def sheet(ws, title):
        ws.title = title
        ws.sheet_view.rightToLeft = rtl
        ws.append([f"{_n(a.project, lang)} · {a.project.code}"])
        ws["A1"].font = Font(bold=True, size=13)
        ws.append([t["title"]])
        ws.append([f"{t['period']}: {period}", f"{t['disc']}: {disc}"])
        ws.append([])

    def header(ws, cols):
        ws.append(cols)
        for cell in ws[ws.max_row]:
            cell.font, cell.fill = bold, head

    def widths(ws, ws_widths):
        for i, w in enumerate(ws_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

    # 1. the scorecard: numbers stay numbers (the unit has its own column), so they can be charted or filtered
    ws = wb.active
    sheet(ws, t["sheet_score"])
    unit_name = {"pct": "%", "days": t["days"], "count": "#", "ratio": "×"}
    for s in ("submittal", "inspection", "test", "ncr", "rfi"):
        rows = [k for k in data["kpis"] if k["section"] == s]
        if not rows:
            continue
        ws.append([t["sec"][s]])
        ws.cell(ws.max_row, 1).font = Font(bold=True, size=12, color="1F3A5F")
        header(ws, [t["kpi"], t["actual"], "", t["target"], t["amber"], t["status"], t["qmp"], t["how"], "code"])
        for k in rows:
            info = k["direction"] == "info"
            sign = "" if info else ("≥" if k["direction"] == "higher" else "≤")
            ws.append([k[f"name_{lang}"], k["value"], unit_name[k["unit"]],
                       t["info"] if info else f"{sign} {k['green']:g}" if k["green"] is not None else "",
                       "" if info or k["amber"] is None else f"{sign} {k['amber']:g}",
                       {"green": t["on"], "amber": t["watch"], "red": t["off"]}.get(k["status"] or "", ""),
                       k["qmp_ref"], k[f"formula_{lang}"], k["code"]])
            if k["status"]:
                ws.cell(ws.max_row, 6).fill = fills[k["status"]]
            ws.cell(ws.max_row, 8).alignment = Alignment(wrap_text=True, vertical="top")
        ws.append([])
    widths(ws, [48, 11, 7, 12, 12, 13, 16, 70, 22])

    # 2. per discipline
    ws = wb.create_sheet()
    sheet(ws, t["sheet_disc"])
    for s, cols in DISC_COLS.items():
        rows = data[s]["by_discipline"]
        if not rows:
            continue
        ws.append([t["sec"][s]])
        ws.cell(ws.max_row, 1).font = Font(bold=True, size=12, color="1F3A5F")
        header(ws, [t["c"]["discipline"]] + [t["c"][k] + (" %" if k in PCT_COLS else "") for k in cols])
        for r in rows:
            ws.append([r[f"name_{lang}"]] + [r.get(k) for k in cols])
        ws.append([])
    widths(ws, [22] + [14] * 8)

    # 3. tests
    ws = wb.create_sheet()
    sheet(ws, t["sheet_tests"])
    tst = data["test"]
    if tst["by_material"]:
        ws.append([t["by_mat"]])
        ws.cell(ws.max_row, 1).font = bold
        header(ws, [t["c"][k] for k in ("material", "tests", "pass", "fail")] + [t["c"]["pass_rate"] + " %"])
        for m in tst["by_material"]:
            ws.append([MAT[lang].get(m["material"], m["material"]), m["tests"], m["pass"], m["fail"], m["pass_rate"]])
        ws.append([])
    if tst["by_class"]:
        ws.append([t["by_class"]])
        ws.cell(ws.max_row, 1).font = bold
        header(ws, [t["c"][k] for k in ("grade", "fck", "reports", "failed", "specimens", "below")])
        for x in tst["by_class"]:
            ws.append([x["grade"], x["fck"], x["reports"], x["failed"], x["specimens"], x["below"]])
        ws.append([])
    if tst["open_failed_list"]:
        ws.append([t["open_failed"]])
        ws.cell(ws.max_row, 1).font = bold
        header(ws, [t["c"]["number"], t["c"]["subject"]])
        for x in tst["open_failed_list"]:
            ws.append([f"{x['number']} R{x['rev_no']}", x["title"]])
    widths(ws, [24, 12, 12, 12, 16, 12])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
