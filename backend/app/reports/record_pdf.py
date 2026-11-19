"""PDF of one record, in Arabic or English, from the record's live data."""
import base64
from datetime import datetime
from zoneinfo import ZoneInfo

import segno
from sqlalchemy import select

from app.core.config import get_settings

from app.core.access import ProjectAccess
from app.core.deps import Ctx
from app.models.core import Organization, ProjectParty
from app.reports.pdf import html_to_pdf, render_html
from app.schemas.records import RecordDetail

T = {
    "ar": {"state": "الحالة", "not_submitted": "لم يُقدَّم بعد", "consultant": "الاستشاري", "owner": "المالك",
           "discipline": "التخصص", "submitted_on": "تاريخ التقديم", "subject": "الموضوع", "description": "الوصف",
           "due": "موعد الرد", "answered_on": "تاريخ الرد", "details": "التفاصيل", "attachments": "المرفقات",
           "decision": "قرار الاستشاري", "comments": "ملاحظات الاستشاري", "submitted_by": "قدّمه (المقاول)",
           "answered_by": "ردّ عليه (الاستشاري)", "on_behalf": "نيابةً عن", "stamp": "بصمة الاعتماد", "requested_for": "موعد الفحص المطلوب", "asap": "فوراً", "performed_at": "وقت الفحص الفعلي", "linked": "الاعتمادات المرتبطة", "resubmit": "إعادة التقديم", "resubmit_text": "يُعاد التقديم خلال {days} يوماً، قبل", "submitted_by_row": "مقدّم الطلب", "addressed_to": "موجّه إلى", "stage": "المرحلة", "locations": "الموقع", "all_locations": "كل المشروع", "photos": "الصور", "checklist": "قائمة الفحص", "item_col": "البند", "result_col": "النتيجة", "note_col": "ملاحظة", "results": {"ok": "مطابق", "nc": "غير مطابق", "na": "لا ينطبق"}, "scan": "امسح الرمز للتحقق من صحة هذا الرد ومطابقته للنسخة المحفوظة في المنصة.",
           "kind": {"submission": "مرفق التقديم", "response": "مرفق الرد", "photo": "صورة", "signed": "النسخة الموقعة", "other": "أخرى"},
           "fields": {"submittal_kind": "نوع الاعتماد", "item": "البند / المادة", "manufacturer": "المصنّع",
                      "supplier": "المورّد / الوكيل", "drawing_ref": "رقم المخطط", "spec_ref": "بند المواصفات",
                      "boq_ref": "بند BOQ", "quantity": "الكمية"}},
    "en": {"state": "Status", "not_submitted": "not submitted", "consultant": "Consultant", "owner": "Owner",
           "discipline": "Discipline", "submitted_on": "Submitted on", "subject": "Subject", "description": "Description",
           "due": "Reply due", "answered_on": "Answered on", "details": "Details", "attachments": "Attachments",
           "decision": "Consultant decision", "comments": "Consultant comments", "submitted_by": "Submitted by (Contractor)",
           "answered_by": "Answered by (Consultant)", "on_behalf": "on behalf of", "stamp": "Approval stamp", "requested_for": "Inspection requested for", "asap": "As soon as possible", "performed_at": "Inspected at", "linked": "Linked submittals", "resubmit": "Resubmission", "resubmit_text": "Resubmit within {days} days, by", "submitted_by_row": "Submitted by", "addressed_to": "Submitted to", "stage": "Stage", "locations": "Location", "all_locations": "Whole project", "photos": "Photos", "checklist": "Inspection checklist", "item_col": "Item", "result_col": "Result", "note_col": "Note", "results": {"ok": "Conforming", "nc": "Non-conforming", "na": "N/A"}, "scan": "Scan to verify that this reply is genuine and matches the copy kept on the platform.",
           "kind": {"submission": "Submission", "response": "Response", "photo": "Photo", "signed": "Signed copy", "other": "Other"},
           "fields": {"submittal_kind": "Submittal type", "item": "Item / material", "manufacturer": "Manufacturer",
                      "supplier": "Supplier / agent", "drawing_ref": "Drawing no.", "spec_ref": "Spec section",
                      "boq_ref": "BOQ item", "quantity": "Quantity"}},
}
PARTY = {"ar": {"contractor": "المقاول", "consultant": "الاستشاري", "owner": "المالك"},
         "en": {"contractor": "Contractor", "consultant": "Consultant", "owner": "Owner"}}
# fields printed per type (standard detail columns, then the type's extra fields)
TYPE_KEYS = {"inspection": ["item", "drawing_ref", "spec_ref", "boq_ref"],
             "material": ["item", "manufacturer", "supplier", "quantity", "spec_ref", "boq_ref"],
             "rfi": ["item", "drawing_ref", "spec_ref"],
             "ncr": ["item", "drawing_ref", "spec_ref"],
             "test": []}
LAB_T = {"ar": {"title": "نتائج الفحص المخبري", "lab": "المختبر", "report_no": "رقم تقرير المختبر", "sampling": "تاريخ أخذ العينة",
                "test_date": "تاريخ الفحص", "report_date": "تاريخ التقرير", "grade": "الدرجة / الفئة", "fck": "المقاومة المطلوبة",
                "element": "العنصر", "quantity": "الكمية الممثلة", "spec": "المواصفة", "sample": "العينة", "param": "المعامل",
                "value": "القيمة", "limits": "الحدود", "res": "النتيجة", "result": "النتيجة المحسوبة", "pass": "مطابق",
                "fail": "غير مطابق", "na": "—", "lab_concl": "استنتاج المختبر", "decision": "القرار على النتيجة الراسبة",
                "avg": "متوسط مقاومة 28 يوماً", "low": "أضعف عينة",
                "decisions": {"retest": "إعادة الفحص", "core": "فحص كور / موقعي", "accepted": "قبول من المهندس", "deduction": "قبول مع خصم على المقاول",
                              "repair": "إصلاح / إزالة واستبدال", "rejected": "رفض المادة / الدفعة", "other": "أخرى"}},
         "en": {"title": "Laboratory test results", "lab": "Laboratory", "report_no": "Lab report no.", "sampling": "Sampling date",
                "test_date": "Test date", "report_date": "Report date", "grade": "Grade / class", "fck": "Specified strength",
                "element": "Element", "quantity": "Quantity represented", "spec": "Specification", "sample": "Sample",
                "param": "Parameter", "value": "Value", "limits": "Limits", "res": "Result", "result": "Calculated result",
                "pass": "Pass", "fail": "Fail", "na": "—", "lab_concl": "Lab conclusion", "decision": "Decision on the failed test",
                "avg": "Mean 28-day strength", "low": "Lowest specimen",
                "decisions": {"retest": "Retest", "core": "Core / in-situ test", "accepted": "Accepted by the Engineer", "deduction": "Accepted with a deduction",
                              "repair": "Repair / remove and replace", "rejected": "Material / batch rejected", "other": "Other"}}}


DAY_T = {"ar": {"title": "التقرير اليومي", "day_no": "رقم التقرير (يوم المشروع)", "weekend": "عطلة أسبوعية", "holiday": "عطلة رسمية",
                "days": ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"], "date": "التاريخ", "shift": "الوردية", "status": "حالة العمل", "weather": "الطقس",
                "temp": "الحرارة", "wind": "الرياح", "hours": "ساعات العمل", "crew": "الطاقم والعمالة", "equipment": "المعدات",
                "materials": "المواد الموردة", "works": "الأعمال المنفذة", "planned": "أعمال الغد المخطط لها", "delays": "التأخير والمعوقات",
                "hse": "السلامة", "qa": "سجلات الجودة اليوم", "visitors": "الزوار والتعليمات", "notes": "ملاحظات",
                "stage": "المرحلة / الموضوع", "where": "الموقع", "desc": "الوصف", "qty": "الكمية", "pct": "الإنجاز %", "count": "العدد",
                "hrs": "الساعات", "idle": "توقف", "supplier": "المورّد", "dn": "سند التسليم", "cause": "السبب", "submitted": "مقدَّم",
                "answered": "مُجاب", "incidents": "حوادث", "near": "شبه حوادث", "toolbox": "توعية", "all": "كل المشروع",
                "groups": {"supervision": "طاقم الإشراف", "contractor": "طاقم المقاول", "labour": "العمالة"},
                "v": {"day": "نهارية", "night": "ليلية", "both": "نهارية وليلية", "normal": "عمل كامل", "partial": "عمل جزئي", "stopped": "متوقف",
                      "sunny": "مشمس", "cloudy": "غائم", "rain": "ماطر", "storm": "عاصف", "snow": "ثلج", "fog": "ضباب", "dust": "غبار",
                      "hot": "حار", "cold": "بارد", "calm": "هادئة", "moderate": "معتدلة", "strong": "قوية",
                      "weather_c": "الطقس", "materials": "المواد", "design": "معلومات التصميم", "approval": "الاعتمادات والاستلام",
                      "equipment": "المعدات", "labour": "العمالة", "utilities": "الخدمات", "access": "الوصول للموقع", "other": "أخرى"}},
         "en": {"title": "Daily report", "day_no": "Report no. (project day)", "weekend": "Weekly day off", "holiday": "Official holiday",
                "days": ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"], "date": "Date", "shift": "Shift", "status": "Work status", "weather": "Weather", "temp": "Temperature",
                "wind": "Wind", "hours": "Working hours", "crew": "Staff and labour", "equipment": "Equipment", "materials": "Materials delivered",
                "works": "Works executed", "planned": "Works planned for tomorrow", "delays": "Delays and obstacles", "hse": "Safety",
                "qa": "QA registers today", "visitors": "Visitors and instructions", "notes": "Notes", "stage": "Stage / topic",
                "where": "Location", "desc": "Description", "qty": "Qty", "pct": "Progress %", "count": "Count", "hrs": "Hours", "idle": "Idle",
                "supplier": "Supplier", "dn": "Delivery note", "cause": "Cause", "submitted": "Submitted", "answered": "Answered",
                "incidents": "Incidents", "near": "Near misses", "toolbox": "Toolbox talks", "all": "Whole project",
                "groups": {"supervision": "Supervision staff", "contractor": "Contractor staff", "labour": "Labour"},
                "v": {"day": "Day", "night": "Night", "both": "Day and night", "normal": "Normal", "partial": "Partial", "stopped": "Stopped",
                      "sunny": "Sunny", "cloudy": "Cloudy", "rain": "Rain", "storm": "Storm", "snow": "Snow", "fog": "Fog", "dust": "Dust",
                      "hot": "Hot", "cold": "Cold", "calm": "Calm", "moderate": "Moderate", "strong": "Strong",
                      "weather_c": "Weather", "materials": "Materials", "design": "Design information", "approval": "Approvals / handover",
                      "equipment": "Equipment", "labour": "Labour", "utilities": "Utilities", "access": "Site access", "other": "Other"}}}


def _daily(c: Ctx, d: RecordDetail, lang: str) -> dict | None:
    if d.record_type.code != "daily_report":
        return None
    from app.api.daily import _qa
    from app.models.daily import DailyReport
    from app.models.structure import ProjectLocation, ProjectStage, ProjectStageTopic
    r = c.db.get(DailyReport, d.id)
    if r is None:
        return None
    L, n = DAY_T[lang], f"name_{lang}"
    names = {}
    for model in (ProjectStage, ProjectStageTopic, ProjectLocation):
        for x in c.db.scalars(select(model).where(model.project_id == r.project_id)):
            names[str(x.id)] = getattr(x, n)
    sep = "، " if lang == "ar" else ", "
    num = lambda v: "" if v is None else f"{float(v):g}"  # noqa: E731

    def works(lines):
        return [{"stage": " › ".join(x for x in (names.get(str(w.get("stage_id")), ""), names.get(str(w.get("topic_id")), "")) if x),
                 "where": L["all"] if w.get("all_locations") else sep.join(names.get(str(i), "") for i in w.get("location_ids") or []),
                 "desc": " — ".join(x for x in (w.get("description") or "",
                                                  (("بدأ فعلياً " if lang == "ar" else "actual start ") + w["actual_start"]) if w.get("actual_start") else "",
                                                  (("انتهى فعلياً " if lang == "ar" else "actual finish ") + w["actual_finish"]) if w.get("actual_finish") else "") if x),
                 "qty": f"{num(w.get('qty'))} {w.get('unit') or ''}".strip(),
                 "pct": num(w.get("progress"))} for w in lines]
    v = L["v"]
    from app.api.daily import day_info
    info = day_info(c, r.project_id, r.report_date)
    off = (L["weekend"] if info["day_off"] == "weekend" else f"{L['holiday']}" + (f": {info['holiday']}" if info["holiday"] else "")) if info["day_off"] else ""
    head = [(L["day_no"], str(info["day_no"]) if info["day_no"] else ""),
            (L["date"], f"{L['days'][info['weekday']]} {r.report_date.isoformat()}" + (f" — {off}" if off else "")),
            (L["shift"], v.get(r.shift, r.shift)),
            (L["status"], v.get(r.work_status, "") + (f" — {r.stop_reason}" if r.stop_reason else "")),
            (L["weather"], v.get(r.weather or "", "")), (L["temp"], f"{num(r.temp_min)} – {num(r.temp_max)} °C" if r.temp_max is not None else ""),
            (L["wind"], v.get(r.wind or "", "")), (L["hours"], f"{r.hours_from or ''} – {r.hours_to or ''}" if r.hours_from else "")]
    crew = {}
    for x in r.crew:
        name = (x.get("name_en") or x["name"]) if lang == "en" else x["name"]
        role = (x.get("role_en") or x.get("role")) if lang == "en" else x.get("role")
        crew.setdefault(x["group"], []).append({**x, "name": name + (f" — {role}" if role else "")})
    hse = r.hse or {}
    return {"t": L, "head": [head[i:i + 2] for i in range(0, len(head), 2)],
            "crew": [{"title": L["groups"][g], "rows": rows, "total": sum(int(y.get("count") or 0) for y in rows)}
                     for g, rows in ((g, crew.get(g, [])) for g in ("supervision", "contractor", "labour")) if rows],
            "equipment": r.equipment, "materials": r.materials, "works": works(r.works), "planned": works(r.planned),
            "delays": [{**x, "cause": v.get("weather_c" if x.get("cause") == "weather" else x.get("cause"), "")} for x in r.delays],
            "hse": hse if any(hse.get(k) for k in ("incidents", "near_misses", "toolbox", "notes")) else None,
            "qa": [{"name": getattr(q, n), "submitted": q.submitted, "answered": q.answered} for q in _qa(c, r.project_id, r.report_date)],
            "visitors": r.visitors, "notes": r.notes, "num": num}


PRG_T = {"ar": {"title": "البرنامج الزمني", "float": "الهامش (يوم)", "crit": "حرج", "legend": "الأحمر = المسار الحرج: أي تأخير فيه يؤخر نهاية المشروع",  "stage": "المرحلة", "where": "الموقع", "start": "البداية", "finish": "النهاية",
                "days": "المدة (يوم)", "whole": "المشروع كاملاً", "span": "من {a} إلى {b} — {n} يوماً", "gantt": "المخطط الزمني",
                "list": "تواريخ المراحل والطوابق"},
          "en": {"title": "Time programme", "float": "Float (days)", "crit": "critical", "legend": "Red = critical path: any delay there moves the project finish",  "stage": "Stage", "where": "Location", "start": "Start", "finish": "Finish",
                 "days": "Days", "whole": "Whole project", "span": "{a} to {b} — {n} days", "gantt": "Schedule",
                 "list": "Dates of stages and floors"}}


def programme_view(db, project_id, lines: list, lang: str, cycles: list | None = None) -> dict | None:
    """Rows (stage, then its floors) with dates and Gantt positions in % of the programme span."""
    from datetime import date, timedelta
    from app.core.programme import plan_cells
    from app.models.structure import ProjectLocation, ProjectStage
    cells = plan_cells(lines)
    if not cells:
        return None
    n = f"name_{lang}"
    stages = list(db.scalars(select(ProjectStage).where(ProjectStage.project_id == project_id).order_by(ProjectStage.sort)))
    groups = {g.id: g for g in db.scalars(select(ProjectLocation).where(ProjectLocation.project_id == project_id,
                                                                        ProjectLocation.kind == "group"))}
    units = sorted(db.scalars(select(ProjectLocation).where(ProjectLocation.project_id == project_id, ProjectLocation.kind == "unit")),
                   key=lambda u: (groups[u.parent_id].sort if u.parent_id in groups else 0, u.sort))
    lo = min(s for s, _ in cells.values())
    hi = max(f for _, f in cells.values())
    span = (hi - lo).days + 1
    pos = lambda s, f: {"l": round((s - lo).days / span * 100, 2), "w": max(0.4, round(((f - s).days + 1) / span * 100, 2))}  # noqa: E731
    T = PRG_T[lang]
    from app.core.programme import total_float
    whole_ids = {str(st.id) for st in stages if st.scope == "whole" or not units}
    active = [str(u.id) for u in units if u.is_active]
    fl = total_float(lines, cycles or [], active, whole_ids)
    has_cpm = bool(fl)
    rows = []
    for st in stages:
        mine = [(u, cells[(str(st.id), str(u.id))]) for u in units if (str(st.id), str(u.id)) in cells]
        whole = cells.get((str(st.id), None))
        if whole:
            f_ = fl.get((str(st.id), None))
            rows.append({"kind": "stage", "stage": getattr(st, n), "where": T["whole"], "s": whole[0], "f": whole[1],
                         "days": (whole[1] - whole[0]).days + 1, "float": f_, "crit": f_ is not None and f_ <= 0, **pos(*whole)})
        elif mine:
            s, f = min(x[1][0] for x in mine), max(x[1][1] for x in mine)
            rows.append({"kind": "stage", "stage": getattr(st, n), "where": "", "s": s, "f": f, "days": (f - s).days + 1,
                         "float": None, "crit": False, **pos(s, f)})
            for u, (a, b) in mine:
                f_ = fl.get((str(st.id), str(u.id)))
                rows.append({"kind": "cell", "stage": "", "where": getattr(u, n), "s": a, "f": b, "days": (b - a).days + 1,
                             "float": f_, "crit": f_ is not None and f_ <= 0, **pos(a, b)})
    months, d = [], date(lo.year, lo.month, 1)
    while d <= hi:
        if d >= lo:
            months.append({"l": round((d - lo).days / span * 100, 2), "label": d.strftime("%m/%Y")})
        d = (d + timedelta(days=32)).replace(day=1)
    return {"t": T, "rows": rows, "months": months, "span": T["span"].format(a=lo.isoformat(), b=hi.isoformat(), n=span),
            "cpm": has_cpm}


def _programme(c: Ctx, d: RecordDetail, lang: str) -> dict | None:
    if d.record_type.code != "programme":
        return None
    from app.models.programme import Programme
    p = c.db.get(Programme, d.id)
    return programme_view(c.db, d.project_id, p.lines, lang, p.cycles) if p else None


def _lab(c: Ctx, d: RecordDetail, lang: str) -> dict | None:
    if d.record_type.code != "test":
        return None
    from app.core.lab import evaluate
    from app.models.lab import LabResult
    res = c.db.get(LabResult, d.id)
    if res is None or not res.lines:
        return None
    L = LAB_T[lang]
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    ev = evaluate({"acceptance": res.acceptance, "fck": f(res.fck), "mean_margin": f(res.mean_margin),
                   "individual_rule": res.individual_rule, "individual_margin": f(res.individual_margin), "lines": res.lines})
    num = lambda v: "" if v is None else f"{v:g}"  # noqa: E731

    def limits(x):
        mn, mx = x.get("min"), x.get("max")
        if mn is not None and mx is not None:
            return f"{num(mn)} – {num(mx)}"
        return f"≥ {num(mn)}" if mn is not None else (f"≤ {num(mx)}" if mx is not None else "")
    head = [(L["lab"], res.lab_name), (L["report_no"], res.lab_report_no), (L["sampling"], res.sampling_date),
            (L["test_date"], res.test_date), (L["report_date"], res.report_date),
            (L["grade"], res.grade), (L["fck"], f"{float(res.fck):g} MPa" if res.fck else None), (L["element"], res.element),
            (L["quantity"], f"{float(res.quantity):g} {res.quantity_uom or ''}" if res.quantity else None),
            (L["spec"], res.specification)]
    head = [(k, str(v)) for k, v in head if v]
    rows = [{"sample": x.get("sample") or "", "param": x["parameter"] + (f" ({x['age']} d)" if x.get("age") and "day" not in x["parameter"] else ""),
             "value": x.get("text") or num(x.get("value")), "unit": x.get("unit") or "", "limits": limits(x),
             "code": r, "res": L.get(r, "")} for x, r in zip(res.lines, ev["line_results"])]
    summary = []
    if ev["strength_avg"] is not None:
        summary += [(L["avg"], f"{ev['strength_avg']} MPa"), (L["low"], f"{ev['strength_min']} MPa")]
    if res.lab_conclusion:
        summary.append((L["lab_concl"], L[res.lab_conclusion]))
    return {"t": L, "head": [head[i:i + 2] for i in range(0, len(head), 2)], "rows": rows, "result": ev["result"],
            "result_text": L.get(ev["result"] or "na"), "note": ev["note"], "summary": summary,
            "decision": L["decisions"].get(res.decision) if res.decision else None, "decision_note": res.decision_note}
CUSTOM = {"ar": {"proposed": "الحل المقترح من المقاول", "impact": "الأثر المتوقع", "delivery_note": "رقم سند التسليم",
                 "storage": "مكان التخزين", "severity": "درجة عدم المطابقة", "required_action": "الإجراء المطلوب",
                 "none": "لا يوجد", "cost": "على الكلفة", "time": "على المدة", "cost_time": "على الكلفة والمدة",
                 "minor": "بسيطة", "major": "جسيمة"},
          "en": {"proposed": "Contractor's proposal", "impact": "Expected impact", "delivery_note": "Delivery note no.",
                 "storage": "Storage location", "severity": "Severity", "required_action": "Required action",
                 "none": "None", "cost": "Cost", "time": "Time", "cost_time": "Cost and time",
                 "minor": "Minor", "major": "Major"}}
ITEM_LABEL = {"inspection": ("تفاصيل العمل المطلوب فحصه", "Work to be inspected"),
              "material": ("المادة الموردة", "Material delivered"),
              "rfi": ("العنصر / الموقع", "Element / location"), "ncr": ("العنصر / الموقع", "Element / location")}
COMMENT_LABEL = {"rfi": ("إجابة الاستشاري", "Consultant's answer"),
                 "ncr": ("الإجراء التصحيحي", "Corrective action")}

DECISIONS = {
    "ar": [("approved", "معتمد"), ("approved_as_noted", "معتمد مع ملاحظات"),
           ("revise_and_resubmit", "تعديل وإعادة تقديم"), ("rejected", "مرفوض")],
    "en": [("approved", "Approved"), ("approved_as_noted", "Approved as noted"),
           ("revise_and_resubmit", "Revise and resubmit"), ("rejected", "Rejected")],
}
LTR_FIELDS = {"drawing_ref", "spec_ref", "boq_ref"}


def _n(obj, lang: str, base: str = "name") -> str:
    if obj is None:
        return ""
    return getattr(obj, f"{base}_{lang}", None) or getattr(obj, f"{base}_ar", "")


def _qr(url: str) -> str:
    """QR of the public verification link, as an inline SVG data URI (vector, sharp when printed)."""
    return segno.make(url, error="m").svg_data_uri(scale=1, border=0, dark="#111")


def header_image(c: Ctx, project) -> str | None:
    """The project's letterhead banner (logos of the parties) as a data URI, if one was uploaded."""
    from app.core import storage
    from app.models.records import StoredFile
    fid = (project.settings or {}).get("header_file_id")
    f = c.db.get(StoredFile, fid) if fid else None
    if f is None:
        return None
    try:
        data = storage.path_of(f.storage_key).read_bytes()
    except Exception:
        return None
    return f"data:{f.content_type};base64,{base64.b64encode(data).decode()}"


def sep_join(lang: str, items: list[str]) -> str:
    return ("، " if lang == "ar" else ", ").join(items)


def _decisions(c: Ctx, d: RecordDetail, lang: str) -> list[tuple[str, str]]:
    """The answers this record type's workflow offers, as printed tick boxes."""
    from app.models.records import RecordType, WorkflowState, WorkflowTransition
    rt = c.db.get(RecordType, d.record_type.id)
    rows = c.db.execute(select(WorkflowState).join(WorkflowTransition, WorkflowTransition.to_state_id == WorkflowState.id)
                        .where(WorkflowTransition.workflow_id == rt.workflow_id,
                               WorkflowTransition.effect.in_(("respond", "none")))
                        .order_by(WorkflowState.sort)).scalars().unique().all()
    return [(x.category, _n(x, lang)) for x in rows]


IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp", "image/gif")
MAX_PHOTOS = 24


def _photos(c: Ctx, d: RecordDetail) -> list[dict]:
    """Photo attachments, shrunk for print (the originals stay as they are)."""
    import base64
    import io

    from PIL import Image, ImageOps

    from app.core import storage
    from app.models.records import StoredFile
    out = []
    for x in d.attachments:
        if x.content_type not in IMAGE_TYPES or len(out) >= MAX_PHOTOS:
            continue
        f = c.db.get(StoredFile, x.file_id)
        try:
            with Image.open(storage.path_of(f.storage_key)) as im:
                im = ImageOps.exif_transpose(im).convert("RGB")  # phone photos carry their rotation in EXIF
                im.thumbnail((1000, 1000))
                buf = io.BytesIO()
                im.save(buf, "JPEG", quality=78, optimize=True)
        except Exception:  # noqa: BLE001 - an unreadable image is listed, not printed
            continue
        out.append({"src": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
                    "name": x.filename, "caption": x.caption, "kind": x.kind, "party": x.party_kind})
    return out


def render_record_pdf(c: Ctx, a: ProjectAccess, d: RecordDetail, lang: str) -> bytes:
    tz = ZoneInfo("Asia/Hebron")

    def dt(v: datetime | None) -> str:
        return v.astimezone(tz).strftime("%Y-%m-%d %H:%M") if v else ""

    parties = {}
    for p, o in c.db.execute(select(ProjectParty, Organization).outerjoin(Organization, Organization.id == ProjectParty.org_id)
                             .where(ProjectParty.project_id == d.project_id, ProjectParty.status != "removed")):
        parties[p.kind] = _n(o, lang) if o else (p.placeholder_name or "")
    from app.models.records import RecordType
    rtm = c.db.get(RecordType, d.record_type.id)
    by, to_ = PARTY[lang].get(rtm.creator_party, ""), PARTY[lang].get(rtm.responder_party, "")
    t = dict(T[lang])
    if lang == "ar":
        t.update(decision=f"قرار {to_}" if rtm.creator_party == "contractor" else "الحالة",
                 comments=COMMENT_LABEL.get(rtm.code, ("ملاحظات " + to_, ""))[0],
                 submitted_by=f"قدّمه ({by})", answered_by=f"ردّ عليه ({to_})")
    else:
        t.update(decision=f"{to_} decision" if rtm.creator_party == "contractor" else "Status",
                 comments=COMMENT_LABEL.get(rtm.code, ("", f"{to_} comments"))[1],
                 submitted_by=f"Submitted by ({by})", answered_by=f"Answered by ({to_})")
    stamp = next((e.stamp for e in reversed(d.events) if e.stamp), None)
    verify_url = f"{get_settings().app_url.rstrip('/')}/v/{stamp}" if stamp else None
    det = d.details.model_dump()
    if d.submittal_kind_name:
        det["submittal_kind"] = getattr(d.submittal_kind_name, lang)
    if det.get("quantity") is not None:
        det["quantity"] = f"{float(det['quantity']):g} {det.get('unit') or ''}".strip()
    code = d.record_type.code
    inspection = code in ("inspection", "material")
    keys = TYPE_KEYS.get(code, list(t["fields"]))
    labels = dict(t["fields"])
    if code in ITEM_LABEL:
        labels["item"] = ITEM_LABEL[code][0 if lang == "ar" else 1]
    pairs = [(labels[k], det.get(k) or "", k in LTR_FIELDS) for k in keys]
    cl = CUSTOM[lang]
    pairs += [(cl[k], cl.get(v, v), False) for k, v in d.custom.items() if v]
    if inspection:
        pairs += [(t["requested_for"], dt(d.requested_for) or t["asap"], True),
                  (t["performed_at"], dt(d.performed_at), True)]
        if d.linked:
            pairs.append((t["linked"], sep_join(lang, [f"{x.number} R{x.rev_no} ({_n(x.state, lang)})" for x in d.linked]), False))
    sep = "، " if lang == "ar" else ", "
    place = t["all_locations"] if d.all_locations else sep.join(getattr(x, f"name_{lang}") for x in d.locations)
    if d.stage or place:
        pairs = [(t["stage"], getattr(d.stage, f"name_{lang}") if d.stage else "", False),
                 (t["locations"], place, False)] + pairs
    rows = [(*pairs[i], *(pairs[i + 1] if i + 1 < len(pairs) else ("", "", False))) for i in range(0, len(pairs), 2)]
    ctx = dict(
        lang=lang, t=t, contractor=parties.get("contractor", ""), consultant=parties.get("consultant", ""),
        owner=parties.get("owner", ""), project_name=_n(a.project, lang), project_code=a.project.code,
        type_name=_n(d.record_type, lang), number=d.number, rev=d.rev_no, state_name=_n(d.state, lang),
        state_category=d.state.category, is_draft=d.state.category == "draft",
        discipline=_n(d.discipline, lang), title=d.title, description=d.description,
        submitted_at=dt(d.submitted_at), due_at=dt(d.due_at), answered_at=dt(d.answered_at),
        detail_rows=rows, decisions=_decisions(c, d, lang), response_comment=d.response_comment,
        attachments=[{"filename": x.filename, "kind": t["kind"].get(x.kind, x.kind)} for x in d.attachments
                     if x.content_type not in IMAGE_TYPES],  # photos print in their own section
        submitted_by=_n(d.submitted_by, lang, "full_name"), answered_by=_n(d.answered_by, lang, "full_name"),
        on_behalf=_n(d.answered_on_behalf_of, lang, "full_name"),
        title_text=getattr(d.topic, f"name_{lang}") if d.topic else d.title,
        submitter=_n(d.submitted_by or d.created_by, lang, "full_name"),
        addressed_to=("، " if lang == "ar" else ", ").join(_n(u, lang, "full_name") for u in d.addressed_to),
        header=header_image(c, a.project),
        resubmit_by=dt(d.resubmit_due_at)[:10] if d.resubmit_due_at else None,
        resubmit_days=(d.resubmit_due_at - d.answered_at).days if d.resubmit_due_at and d.answered_at else None,
        stamp=stamp, stamp_short="-".join(stamp[i:i + 4] for i in range(0, 12, 4)).upper() if stamp else None,
        verify_url=verify_url, qr=_qr(verify_url) if verify_url else None,
        lab=_lab(c, d, lang), daily=_daily(c, d, lang), programme=_programme(c, d, lang),
        photos=[{**p, "who": PARTY[lang].get(p["party"], "")} for p in _photos(c, d)],
        checklist=[{"text": getattr(x, lang), "result": t["results"].get(x.result, ""), "code": x.result,
                    "note": x.note or ""} for x in d.checklist],
    )
    return html_to_pdf(render_html("record.html", **ctx), footer_text=f"Verqac · {d.number} · Rev. {d.rev_no}",
                       landscape=d.record_type.code == "programme")
