"""PDF of the weekly / monthly report, in Arabic or English."""
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.access import ProjectAccess
from app.core.deps import Ctx
from app.models.core import Organization, ProjectParty
from app.reports.pdf import html_to_pdf, render_html
from app.reports.record_pdf import DAY_T, PARTY, _n, header_image

P_T = {
    "ar": {"week": "التقرير الأسبوعي", "month": "التقرير الشهري", "period": "الفترة", "upto": "محسوب حتى",
           "consultant": "الاستشاري", "owner": "المالك", "summary": "الملخص", "working_days": "أيام العمل في الفترة",
           "reports": "التقارير اليومية المعتمدة", "pending": "بانتظار الاعتماد (غير محسوبة)", "missing": "أيام عمل بلا تقرير",
           "stopped": "أيام توقف", "partial": "أيام عمل جزئي", "weather": "الطقس",
           "progress": "الإنجاز", "p_start": "بداية الفترة", "p_end": "نهاية الفترة", "p_delta": "إنجاز الفترة",
           "planned": "المخطط", "spi": "مؤشر الأداء الزمني SPI", "stage": "المرحلة", "weight": "الوزن",
           "where": "مواقع العمل في الفترة", "qty": "الكميات", "days": "أيام", "no_prg": "لا يوجد برنامج زمني معتمد",
           "crew": "الطاقم والعمالة", "man_days": "يوم-عمل", "avg": "متوسط يومي", "peak": "الذروة", "sub": "المقاول الفرعي",
           "name": "الاسم / المهنة", "equipment": "المعدات", "unit_days": "يوم-معدة", "hours": "ساعات التشغيل", "idle": "ساعات التوقف",
           "delays": "التأخير والمعوقات", "cause": "السبب", "count": "مرات", "date": "التاريخ", "desc": "الوصف",
           "hse": "السلامة", "materials": "المواد الموردة", "supplier": "المورّد", "dn": "سند التسليم",
           "late": "الأعمال المتأخرة عن البرنامج (نهاية الفترة)", "actual": "الفعلي", "finish": "النهاية المخططة",
           "requests": "سجلات الجودة (الطلبات)", "type": "النوع", "submitted": "قُدّم", "answered": "أُجيب", "approved": "معتمد",
           "returned": "مُعاد / مرفوض", "open": "مفتوح", "overdue": "متأخر الرد", "number": "الرقم", "title": "الموضوع",
           "due": "موعد الرد", "late_by": "متأخر (يوم)", "none": "لا يوجد"},
    "en": {"week": "Weekly report", "month": "Monthly report", "period": "Period", "upto": "Counted up to",
           "consultant": "Consultant", "owner": "Owner", "summary": "Summary", "working_days": "Working days in the period",
           "reports": "Approved daily reports", "pending": "Awaiting approval (not counted)", "missing": "Working days without a report",
           "stopped": "Days stopped", "partial": "Days of partial work", "weather": "Weather",
           "progress": "Progress", "p_start": "Start of period", "p_end": "End of period", "p_delta": "Progress in the period",
           "planned": "Planned", "spi": "Schedule performance index (SPI)", "stage": "Stage", "weight": "Weight",
           "where": "Locations worked", "qty": "Quantities", "days": "Days", "no_prg": "No approved programme",
           "crew": "Staff and labour", "man_days": "Man-days", "avg": "Daily average", "peak": "Peak", "sub": "Subcontractor",
           "name": "Name / trade", "equipment": "Equipment", "unit_days": "Unit-days", "hours": "Working hours", "idle": "Idle hours",
           "delays": "Delays and obstacles", "cause": "Cause", "count": "Times", "date": "Date", "desc": "Description",
           "hse": "Safety", "materials": "Materials delivered", "supplier": "Supplier", "dn": "Delivery note",
           "late": "Works behind the programme (end of period)", "actual": "Actual", "finish": "Planned finish",
           "requests": "QA registers (requests)", "type": "Type", "submitted": "Submitted", "answered": "Answered", "approved": "Approved",
           "returned": "Returned / rejected", "open": "Open", "overdue": "Reply overdue", "number": "No.", "title": "Subject",
           "due": "Reply due", "late_by": "Late (days)", "none": "None"},
}


def render_period_pdf(c: Ctx, a: ProjectAccess, out, lang: str) -> bytes:
    tz = ZoneInfo("Asia/Hebron")
    parties = {}
    for p, o in c.db.execute(select(ProjectParty, Organization).outerjoin(Organization, Organization.id == ProjectParty.org_id)
                             .where(ProjectParty.project_id == a.project.id, ProjectParty.status != "removed")):
        parties[p.kind] = _n(o, lang) if o else (p.placeholder_name or "")
    D = DAY_T[lang]
    v = D["v"]

    def cause(k: str) -> str:
        return v.get("weather_c" if k == "weather" else k, k)

    def qty(rows: list[dict]) -> str:
        return " · ".join(f"{r['qty']:g} {r['unit']}".strip() for r in rows)

    ctx = dict(
        lang=lang, t=P_T[lang], D=D, o=out, header=header_image(c, a.project),
        contractor=parties.get("contractor", ""), consultant=parties.get("consultant", ""), owner=parties.get("owner", ""),
        project_name=_n(a.project, lang), project_code=a.project.code, title=P_T[lang][out.kind],
        weather=" · ".join(f"{v.get(k, k)} {n}" for k, n in sorted(out.weather.items(), key=lambda x: -x[1])),
        cause=cause, qty=qty, groups=D["groups"], party=PARTY[lang],
        due=lambda x: x.astimezone(tz).strftime("%Y-%m-%d"),
        dates=lambda xs: " · ".join(d.strftime("%m/%d") for d in xs),
    )
    return html_to_pdf(render_html("period.html", **ctx),
                       footer_text=f"Verqac · {a.project.code} · {out.start.isoformat()} → {out.end.isoformat()}")
