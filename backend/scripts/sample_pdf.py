"""Phase 0 check: render a submittal form in Arabic and English to PDF.

    python -m scripts.sample_pdf  ->  sample_submittal_ar.pdf, sample_submittal_en.pdf
"""
import hashlib
import json
from pathlib import Path

from app.reports.pdf import html_to_pdf, render_html

T = {
    "ar": {
        "title": "طلب اعتماد مواد", "consultant": "الاستشاري", "owner": "المالك", "discipline": "التخصص",
        "date": "تاريخ التقديم", "subject": "الموضوع", "boq": "بند BOQ", "due": "موعد الرد",
        "items_title": "المواد المقدَّمة", "item": "المادة", "manufacturer": "المصنّع", "qty": "الكمية",
        "decision": "قرار الاستشاري", "comments": "الملاحظات",
        "decisions": [("approved", "معتمد"), ("approved_as_noted", "معتمد مع ملاحظات"),
                      ("revise_and_resubmit", "تعديل وإعادة تقديم"), ("rejected", "مرفوض")],
        "submitted_by": "قدّمه (المقاول)", "answered_by": "ردّ عليه (الاستشاري)", "stamp": "بصمة الاعتماد",
    },
    "en": {
        "title": "Material Submittal", "consultant": "Consultant", "owner": "Owner", "discipline": "Discipline",
        "date": "Submitted on", "subject": "Subject", "boq": "BOQ item", "due": "Reply due",
        "items_title": "Submitted materials", "item": "Material", "manufacturer": "Manufacturer", "qty": "Quantity",
        "decision": "Consultant decision", "comments": "Comments",
        "decisions": [("approved", "Approved"), ("approved_as_noted", "Approved as noted"),
                      ("revise_and_resubmit", "Revise and resubmit"), ("rejected", "Rejected")],
        "submitted_by": "Submitted by (Contractor)", "answered_by": "Answered by (Consultant)",
        "stamp": "Approval stamp",
    },
}

DATA = {
    "ar": {
        "org_name": "شركة المصلح للمقاولات", "project_name": "مدرسة بنات الخليل الثانوية",
        "consultant": "مكتب الهندسة الاستشاري", "owner": "وزارة التربية والتعليم",
        "discipline": "مدني", "subject": "اعتماد حديد التسليح قطر 12 و16 ملم، درجة S500",
        "items": [{"name": "حديد تسليح Ø12 ملم", "maker": "مصنع الحديد الوطني", "qty": "18 طن"},
                  {"name": "حديد تسليح Ø16 ملم", "maker": "مصنع الحديد الوطني", "qty": "24 طن"}],
        "comments": "يُعتمد بشرط تقديم شهادة المصنع لكل دفعة، وفحص عينة من كل 20 طن.",
        "submitted_by": "م. أحمد سالم", "answered_by": "م. خالد يوسف (نيابة عن م. سامي داود)",
    },
    "en": {
        "org_name": "Al-Musleh Contracting", "project_name": "Hebron Girls Secondary School",
        "consultant": "Engineering Consultancy Office", "owner": "Ministry of Education",
        "discipline": "Civil", "subject": "Approval of reinforcement steel Ø12 and Ø16 mm, grade S500",
        "items": [{"name": "Rebar Ø12 mm", "maker": "National Steel Mill", "qty": "18 t"},
                  {"name": "Rebar Ø16 mm", "maker": "National Steel Mill", "qty": "24 t"}],
        "comments": "Approved provided a mill certificate is submitted for every batch and one sample "
                    "per 20 t is tested.",
        "submitted_by": "Eng. Ahmad Salem", "answered_by": "Eng. Khaled Yousef (on behalf of Eng. Sami Dawood)",
    },
}

COMMON = {"project_code": "HGSS", "number": "HGSS-SUB-C-045", "rev": 1, "date": "2026-11-10",
          "boq": "03.02.01", "due": "2026-11-24", "decision": "approved_as_noted",
          "submitted_at": "2026-11-10 09:14", "answered_at": "2026-11-15 13:40"}


def main() -> None:
    for lang in ("ar", "en"):
        ctx = {**COMMON, **DATA[lang], "lang": lang, "t": T[lang]}
        ctx["stamp"] = hashlib.sha256(json.dumps({**COMMON, **DATA[lang]}, sort_keys=True,
                                                 ensure_ascii=False).encode()).hexdigest()[:32]
        pdf = html_to_pdf(render_html("submittal_sample.html", **ctx),
                          footer_text="Verqac · " + COMMON["number"])
        out = Path(f"sample_submittal_{lang}.pdf")
        out.write_bytes(pdf)
        print(out, len(pdf), "bytes")


if __name__ == "__main__":
    main()
