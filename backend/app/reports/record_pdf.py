"""PDF of one record, in Arabic or English, from the record's live data."""
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
           "answered_by": "ردّ عليه (الاستشاري)", "on_behalf": "نيابةً عن", "stamp": "بصمة الاعتماد", "scan": "امسح الرمز للتحقق من صحة هذا الرد ومطابقته للنسخة المحفوظة في المنصة.",
           "kind": {"submission": "مرفق التقديم", "response": "مرفق الرد", "photo": "صورة", "other": "أخرى"},
           "fields": {"submittal_kind": "نوع الاعتماد", "item": "البند / المادة", "manufacturer": "المصنّع",
                      "supplier": "المورّد / الوكيل", "drawing_ref": "رقم المخطط", "spec_ref": "بند المواصفات",
                      "boq_ref": "بند BOQ", "quantity": "الكمية"}},
    "en": {"state": "Status", "not_submitted": "not submitted", "consultant": "Consultant", "owner": "Owner",
           "discipline": "Discipline", "submitted_on": "Submitted on", "subject": "Subject", "description": "Description",
           "due": "Reply due", "answered_on": "Answered on", "details": "Details", "attachments": "Attachments",
           "decision": "Consultant decision", "comments": "Consultant comments", "submitted_by": "Submitted by (Contractor)",
           "answered_by": "Answered by (Consultant)", "on_behalf": "on behalf of", "stamp": "Approval stamp", "scan": "Scan to verify that this reply is genuine and matches the copy kept on the platform.",
           "kind": {"submission": "Submission", "response": "Response", "photo": "Photo", "other": "Other"},
           "fields": {"submittal_kind": "Submittal type", "item": "Item / material", "manufacturer": "Manufacturer",
                      "supplier": "Supplier / agent", "drawing_ref": "Drawing no.", "spec_ref": "Spec section",
                      "boq_ref": "BOQ item", "quantity": "Quantity"}},
}
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


def render_record_pdf(c: Ctx, a: ProjectAccess, d: RecordDetail, lang: str) -> bytes:
    tz = ZoneInfo("Asia/Hebron")

    def dt(v: datetime | None) -> str:
        return v.astimezone(tz).strftime("%Y-%m-%d %H:%M") if v else ""

    parties = {}
    for p, o in c.db.execute(select(ProjectParty, Organization).outerjoin(Organization, Organization.id == ProjectParty.org_id)
                             .where(ProjectParty.project_id == d.project_id, ProjectParty.status != "removed")):
        parties[p.kind] = _n(o, lang) if o else (p.placeholder_name or "")
    t = T[lang]
    stamp = next((e.stamp for e in reversed(d.events) if e.stamp), None)
    verify_url = f"{get_settings().app_url.rstrip('/')}/v/{stamp}" if stamp else None
    det = d.details.model_dump()
    if d.submittal_kind_name:
        det["submittal_kind"] = getattr(d.submittal_kind_name, lang)
    if det.get("quantity") is not None:
        det["quantity"] = f"{float(det['quantity']):g} {det.get('unit') or ''}".strip()
    pairs = [(t["fields"][k], det.get(k) or "", k in LTR_FIELDS) for k in t["fields"]]
    rows = [(*pairs[i], *(pairs[i + 1] if i + 1 < len(pairs) else ("", "", False))) for i in range(0, len(pairs), 2)]
    ctx = dict(
        lang=lang, t=t, contractor=parties.get("contractor", ""), consultant=parties.get("consultant", ""),
        owner=parties.get("owner", ""), project_name=_n(a.project, lang), project_code=a.project.code,
        type_name=_n(d.record_type, lang), number=d.number, rev=d.rev_no, state_name=_n(d.state, lang),
        state_category=d.state.category, is_draft=d.state.category == "draft",
        discipline=_n(d.discipline, lang), title=d.title, description=d.description,
        submitted_at=dt(d.submitted_at), due_at=dt(d.due_at), answered_at=dt(d.answered_at),
        detail_rows=rows, decisions=DECISIONS[lang], response_comment=d.response_comment,
        attachments=[{"filename": x.filename, "kind": t["kind"].get(x.kind, x.kind)} for x in d.attachments],
        submitted_by=_n(d.submitted_by, lang, "full_name"), answered_by=_n(d.answered_by, lang, "full_name"),
        on_behalf=_n(d.answered_on_behalf_of, lang, "full_name"),
        stamp=stamp, stamp_short="-".join(stamp[i:i + 4] for i in range(0, 12, 4)).upper() if stamp else None,
        verify_url=verify_url, qr=_qr(verify_url) if verify_url else None,
    )
    return html_to_pdf(render_html("record.html", **ctx), footer_text=f"Verqac · {d.number} · Rev. {d.rev_no}")
