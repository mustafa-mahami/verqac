"""QA/QC key performance indicators (as in Odoo's dr module, QMP 6.14 / 7.16 / 8.16 / 9.14 / 10.15 / 14.6 / 14.8).

Computed from the registers: every revision is a record of one revision group; the latest revision of a group
is its highest rev_no. A project keeps its own targets (green / amber thresholds, QMP reference, on/off) in
project.settings["kpi"]; the defaults below are the dr module's.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import select

TZ = ZoneInfo("Asia/Hebron")
APPROVED = ("approved", "approved_as_noted")
DECIDED = ("approved", "approved_as_noted", "revise_and_resubmit", "rejected")
RESUBMIT = ("revise_and_resubmit", "rejected")
SECTIONS = ("submittal", "inspection", "test", "ncr", "rfi")

# code, section, unit (pct | days | count | ratio), direction (higher | lower | info), green, amber, QMP ref, ar, en,
# how it is worked out (ar, en)
DEFS = [
    ("SUB_FIRST_PASS", "submittal", "pct", "higher", 75, 60, "6.14 / 7.16 / 8.16",
     "الاعتمادات المقبولة من أول تقديم", "Submittals approved on first submission",
     "الاعتمادات التي قُبل إصدارها الأول R0 (معتمد أو معتمد مع ملاحظات) ÷ الاعتمادات التي رُدّ على R0 فيها × 100.",
     "Submittals whose R0 was Approved / Approved as noted ÷ submittals whose R0 was answered × 100."),
    ("SUB_CYCLE_DAYS", "submittal", "days", "lower", 14, 21, "6.14 / 8.16",
     "متوسط مدة مراجعة الاعتماد (الإشراف)", "Average submittal review time (supervision)",
     "متوسط الأيام من التقديم إلى الرد لكل إصدار رُدّ عليه.", "Mean days from submission to answer, per answered revision."),
    ("SUB_CONTRACTOR_DAYS", "submittal", "days", "lower", 7, 14, "8.16",
     "متوسط مدة إعادة التقديم (المقاول)", "Average resubmission time (contractor)",
     "متوسط الأيام من رد الإشراف بإعادة التقديم أو الرفض إلى تقديم الإصدار التالي.",
     "Mean days from a Revise & resubmit / Rejected answer to the submission of the next revision."),
    ("SUB_WITHIN_PERIOD", "submittal", "pct", "higher", 90, 75, "8.16",
     "مراجعات الاعتماد ضمن المدة", "Submittal reviews within the review period",
     "الإصدارات التي رُدّ عليها في موعدها أو قبله ÷ الإصدارات التي رُدّ عليها × 100.",
     "Answered revisions answered by their due time ÷ answered revisions × 100."),
    ("SUB_OVERDUE", "submittal", "count", "lower", 0, 5, "6.14 / 8.16",
     "اعتمادات متأخرة الرد", "Overdue submittals (awaiting answer)",
     "الاعتمادات التي آخر إصدار منها مقدَّم بلا رد وتجاوز موعد الرد.",
     "Submittals whose latest revision is submitted, unanswered and past its due time."),
    ("SUB_OUTSTANDING", "submittal", "pct", "lower", 10, 20, "8.16",
     "اعتمادات بانتظار إعادة التقديم", "Outstanding resubmissions",
     "الاعتمادات التي آخر إصدار منها «إعادة تقديم» أو «مرفوض» ÷ كل الاعتمادات × 100.",
     "Submittals whose latest revision is Revise & resubmit / Rejected ÷ all submittals × 100."),
    ("SUB_RESUB_INDEX", "submittal", "ratio", "lower", 0.5, 1, "8.16",
     "عدد إعادات التقديم لكل اعتماد", "Resubmissions per submittal",
     "(عدد الإصدارات − عدد الاعتمادات) ÷ عدد الاعتمادات. صفر = كل اعتماد أُغلق من R0.",
     "(Revisions − submittals) ÷ submittals. 0 = every submittal closed at R0."),
    ("SUB_APPROVAL_PROGRESS", "submittal", "pct", "info", None, None, "14.8",
     "تقدّم اعتماد المواد والمخططات", "Material / shop drawing approval progress",
     "الاعتمادات التي آخر إصدار منها معتمد أو معتمد مع ملاحظات ÷ كل الاعتمادات × 100.",
     "Submittals whose latest revision is Approved / Approved as noted ÷ all submittals × 100."),

    ("IR_FIRST_PASS", "inspection", "pct", "higher", 90, 80, "9.14 / 10.15",
     "طلبات الفحص المقبولة من أول مرة", "Inspections passed on first submission",
     "طلبات الفحص التي قُبل R0 منها ÷ التي رُدّ على R0 منها × 100.",
     "IRs whose R0 was accepted ÷ IRs whose R0 was answered × 100."),
    ("IR_REJECTION", "inspection", "pct", "lower", 5, 10, "9.14 / 14.6",
     "طلبات الفحص المرفوضة", "Rejected inspection requests",
     "إصدارات طلبات الفحص المرفوضة ÷ الإصدارات التي رُدّ عليها × 100.",
     "IR revisions Rejected ÷ IR revisions answered × 100."),
    ("IR_RESPONSE_DAYS", "inspection", "days", "lower", 2, 3, "9.14 / 14.6",
     "متوسط مدة الرد على طلب الفحص (الإشراف)", "Average inspection response time (supervision)",
     "متوسط الأيام من موعد الفحص المطلوب (أو التقديم) إلى الرد.",
     "Mean days from the requested inspection time (or submission) to the answer."),
    ("IR_CONTRACTOR_DAYS", "inspection", "days", "lower", 2, 5, "10.15",
     "متوسط مدة إعادة الفحص (المقاول)", "Average re-inspection time (contractor)",
     "متوسط الأيام من رد الإشراف بالرفض أو إعادة الفحص إلى تقديم الإصدار التالي.",
     "Mean days from a returned IR to the submission of the next revision."),
    ("IR_BACKLOG", "inspection", "count", "lower", 0, 3, "9.14",
     "طلبات فحص متأخرة الرد", "Inspection backlog (overdue)",
     "طلبات الفحص التي آخر إصدار منها مقدَّم بلا رد وتجاوز موعد الرد.",
     "IRs whose latest revision is submitted, unanswered and past its due time."),
    ("IR_OUTSTANDING", "inspection", "pct", "lower", 5, 10, "10.15",
     "طلبات فحص بانتظار إعادة الفحص", "Outstanding re-inspections",
     "طلبات الفحص التي آخر إصدار منها «إعادة» أو «مرفوض» ÷ كل طلبات الفحص × 100.",
     "IRs whose latest revision is returned / rejected ÷ all IRs × 100."),

    ("TEST_PASS", "test", "pct", "higher", 98, 95, "7.16 / 14.6",
     "نسبة نجاح الفحوصات المخبرية", "Laboratory test pass rate",
     "الفحوصات الناجحة ÷ الفحوصات التي لها نتيجة × 100.", "Tests with result PASS ÷ tests with a result × 100."),
    ("TEST_FIRST_TIME", "test", "pct", "higher", 95, 90, "7.16 / 9.14",
     "فحوصات نجحت من أول مرة", "Tests passed first time",
     "الفحوصات الأصلية (غير الإعادات) الناجحة ÷ الأصلية التي لها نتيجة × 100.",
     "Original tests (not retests) PASS ÷ original tests with a result × 100."),
    ("TEST_FAILED", "test", "count", "lower", 0, 2, "9.14", "فحوصات راسبة", "Failed laboratory tests",
     "عدد الفحوصات الراسبة في الفترة.", "Count of tests with result FAIL in the period."),
    ("TEST_OPEN_FAILED", "test", "count", "lower", 0, 2, "7.16 / 14.6",
     "فحوصات راسبة بلا قرار", "Failed tests without a decision",
     "الفحوصات التي آخر نتيجة لها راسبة ولم يُتخذ فيها قرار (إعادة، كور، قبول، خصم...).",
     "Tests whose latest result is FAIL and no decision was taken."),
    ("TEST_28D_PASS", "test", "pct", "higher", 98, 95, "14.6",
     "مكعبات 28 يوماً المحققة للمقاومة", "Concrete 28-day specimens reaching strength",
     "عينات 28 يوماً التي بلغت المقاومة المحددة (fck) ÷ كل عينات 28 يوماً × 100.",
     "28-day specimens reaching fck ÷ all 28-day specimens × 100."),
    ("CONC_BELOW_PCT", "test", "pct", "lower", 0, 5, "14.6",
     "عينات خرسانة دون المقاومة المحددة", "Concrete specimens below specified strength",
     "عينات 28 يوماً دون fck ÷ كل عينات 28 يوماً × 100.", "28-day specimens below fck ÷ all 28-day specimens × 100."),
    ("TEST_TURNAROUND", "test", "days", "info", None, None, "7.16",
     "متوسط مدة الفحص (من أخذ العينة إلى التقرير)", "Average lab turnaround (sampling to report)",
     "متوسط الأيام من أخذ العينة إلى تاريخ التقرير (أو الفحص)، ويشمل عمر المعالجة للخرسانة.",
     "Mean days from sampling to the report (or test) date; includes curing age for concrete."),

    ("NCR_OPEN", "ncr", "count", "lower", 5, 10, "14.8", "تقارير عدم مطابقة مفتوحة", "Open NCRs",
     "تقارير عدم المطابقة الصادرة ولم تُغلق.", "Issued NCRs not closed yet."),
    ("NCR_CLOSE_DAYS", "ncr", "days", "lower", 14, 21, "9.14 / 14.6",
     "متوسط مدة إغلاق عدم المطابقة", "Average NCR closure time",
     "متوسط الأيام من الإصدار إلى الإغلاق للتقارير المغلقة.", "Mean days from issue to close, closed NCRs."),
    ("NCR_CONTRACTOR_DAYS", "ncr", "days", "lower", 10, 14, "9.14 / 14.6",
     "متوسط مدة الإجراء التصحيحي (المقاول)", "Average corrective action time (contractor)",
     "متوسط الأيام من الإصدار إلى إرسال المقاول للإجراء التصحيحي.",
     "Mean days from issue to the contractor's corrective action."),
    ("NCR_SUPERVISION_DAYS", "ncr", "days", "lower", 3, 7, "9.14 / 14.6",
     "متوسط مدة التحقق والإغلاق (الإشراف)", "Average verification time (supervision)",
     "متوسط الأيام من الإجراء التصحيحي إلى الإغلاق.", "Mean days from the corrective action to the close."),
    ("NCR_ON_TIME", "ncr", "pct", "higher", 90, 75, "10.15 / 14.6",
     "تقارير أُغلقت ضمن المدة", "NCRs closed on time",
     "التقارير المغلقة خلال مدة الإغلاق المحددة للمشروع ÷ التقارير المغلقة × 100.",
     "Closed NCRs closed within the project's closure period ÷ closed NCRs × 100."),
    ("NCR_OVERDUE", "ncr", "count", "lower", 0, 3, "14.6",
     "تقارير مفتوحة تجاوزت مدة الإغلاق", "Overdue open NCRs",
     "التقارير المفتوحة الأقدم من مدة الإغلاق المحددة للمشروع.", "Open NCRs older than the project's closure period."),
    ("NCR_REPEAT", "ncr", "count", "lower", 0, 2, "10.15 / 14.6", "تقارير عدم مطابقة متكررة", "Repeat NCRs",
     "تقارير صدرت بنفس الموضوع (المرحلة والموضوع، أو العنوان) لتقرير سابق في المشروع.",
     "NCRs raised on a subject (stage + topic, or title) already raised earlier in the project."),

    ("RFI_RESPONSE_DAYS", "rfi", "days", "lower", 7, 10, "6.14", "متوسط مدة الرد على الاستيضاح", "Average RFI response time",
     "متوسط الأيام من تقديم الاستيضاح إلى الإجابة.", "Mean days from submission to answer."),
    ("RFI_OVERDUE", "rfi", "count", "lower", 0, 3, "6.14", "استيضاحات متأخرة الرد", "Overdue open RFIs",
     "الاستيضاحات المقدَّمة بلا إجابة وتجاوزت موعد الرد.", "Submitted RFIs unanswered past their due time."),
]
CODES = [d[0] for d in DEFS]
DEF = {d[0]: d for d in DEFS}
DEFAULT_NCR_CLOSE_DAYS = 14


def settings_of(project) -> dict:
    """{"targets": {code: {green, amber, qmp_ref, active}}, "ncr_close_days": int} with the defaults filled in."""
    raw = dict((project.settings or {}).get("kpi") or {})
    own = raw.get("targets") or {}
    targets = {}
    for code, _s, _u, _d, green, amber, qmp, *_ in DEFS:
        o = own.get(code) or {}
        targets[code] = {"green": o.get("green", green), "amber": o.get("amber", amber),
                         "qmp_ref": o.get("qmp_ref", qmp), "active": o.get("active", True)}
    return {"targets": targets, "ncr_close_days": int(raw.get("ncr_close_days") or DEFAULT_NCR_CLOSE_DAYS)}


def rag(value, direction: str, green, amber) -> str | None:
    """green | amber | red (None: no value, an information line, or no target)."""
    if value is None or direction == "info" or green is None or amber is None:
        return None
    if direction == "higher":
        return "green" if value >= green else "amber" if value >= amber else "red"
    return "green" if value <= green else "amber" if value <= amber else "red"


def _pct(n, d):
    return round(100.0 * n / d, 1) if d else None


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 1) if xs else None


def _days(a: datetime | None, b: datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return max(0.0, (b - a).total_seconds() / 86400)


class _Reg:
    """One register's records (drafts and cancelled out), grouped by revision group."""

    def __init__(self, recs):
        self.recs = [r for r in recs if r.submitted_at is not None and r.state_category not in ("draft", "cancelled")]
        g = defaultdict(list)
        for r in self.recs:
            g[r.revision_group_id].append(r)
        self.groups = [sorted(v, key=lambda r: r.rev_no) for v in g.values()]

    def latest(self):
        return [g[-1] for g in self.groups]

    def returned_gaps(self):
        """Contractor side: from a returned answer to the next revision's submission."""
        out = []
        for g in self.groups:
            for a, b in zip(g, g[1:]):
                if a.state_category in RESUBMIT and a.answered_at and b.submitted_at:
                    out.append(_days(a.answered_at, b.submitted_at))
        return out


def _review(reg: _Reg, now: datetime, start_of=lambda r: r.submitted_at) -> dict:
    """The figures of a reviewed register (submittals, inspections)."""
    groups, latest = reg.groups, reg.latest()
    r0 = [g[0] for g in groups]
    decided0 = [r for r in r0 if r.state_category in DECIDED]
    answered = [r for r in reg.recs if r.answered_at is not None and r.state_category in DECIDED]
    with_due = [r for r in answered if r.due_at is not None]
    return {
        "unique": len(groups), "records": len(reg.recs),
        "first_pass": _pct(len([r for r in decided0 if r.state_category in APPROVED]), len(decided0)),
        "review_days": _avg([_days(start_of(r), r.answered_at) for r in answered]),
        "contractor_days": _avg(reg.returned_gaps()),
        "within": _pct(len([r for r in with_due if r.answered_at <= r.due_at]), len(with_due)),
        "overdue": len([r for r in latest if r.state_category == "submitted" and r.due_at and r.due_at < now]),
        "outstanding": _pct(len([r for r in latest if r.state_category in RESUBMIT]), len(groups)),
        "outstanding_n": len([r for r in latest if r.state_category in RESUBMIT]),
        "resub_index": round((len(reg.recs) - len(groups)) / len(groups), 2) if groups else None,
        "approved": len([r for r in latest if r.state_category in APPROVED]),
        "approved_pct": _pct(len([r for r in latest if r.state_category in APPROVED]), len(groups)),
        "pending": len([r for r in latest if r.state_category == "submitted"]),
        "rejected_pct": _pct(len([r for r in answered if r.state_category == "rejected"]), len(answered)),
    }


def compute(db, project, date_from: date | None = None, date_to: date | None = None, discipline: str | None = None) -> dict:
    from app.models.lab import ConcreteClass, LabResult
    from app.models.core import Discipline
    from app.models.records import Record, RecordEvent, RecordType, WorkflowState
    now = datetime.now(UTC)
    types = {t.code: t.id for t in db.scalars(select(RecordType).where(RecordType.org_id.is_(None)))}
    discs = {d.id: d for d in db.scalars(select(Discipline))}
    q = select(Record).where(Record.project_id == project.id,
                             Record.record_type_id.in_([types[c] for c in ("submittal", "inspection", "test", "ncr", "rfi") if c in types]))
    if date_from:
        q = q.where(Record.submitted_at >= datetime.combine(date_from, time.min, TZ))
    if date_to:
        q = q.where(Record.submitted_at <= datetime.combine(date_to, time.max, TZ))
    by_type = defaultdict(list)
    for r in db.scalars(q):
        d = discs.get(r.discipline_id)
        if discipline and (d.code if d else "") != discipline:
            continue
        by_type[r.record_type_id].append(r)
    regs = {c: _Reg(by_type.get(types.get(c), [])) for c in SECTIONS}

    def disc_of(r):
        d = discs.get(r.discipline_id)
        return (d.code, d.name_ar, d.name_en) if d else ("", "—", "—")

    def per_disc(reg: _Reg, fn):
        rows = defaultdict(list)
        for g in reg.groups:
            rows[disc_of(g[0])].extend(g)
        return [{"code": k[0], "name_ar": k[1], "name_en": k[2], **fn(_Reg(v))} for k, v in sorted(rows.items())]

    sub = _review(regs["submittal"], now)
    ir = _review(regs["inspection"], now, start_of=lambda r: max(x for x in (r.submitted_at, r.requested_for) if x))

    # laboratory tests
    treg = regs["test"]
    labs = {x.record_id: x for x in db.scalars(select(LabResult).where(LabResult.record_id.in_([r.id for r in treg.recs])))} \
        if treg.recs else {}
    classes = {c.id: c for c in db.scalars(select(ConcreteClass).where(ConcreteClass.project_id == project.id))}
    with_res = [r for r in treg.recs if labs.get(r.id) and labs[r.id].result in ("pass", "fail")]
    orig = [g[0] for g in treg.groups if labs.get(g[0].id) and labs[g[0].id].result in ("pass", "fail")]
    open_failed = [g[-1] for g in treg.groups if labs.get(g[-1].id) and labs[g[-1].id].result == "fail" and not labs[g[-1].id].decision]
    s28_ok = s28_all = 0
    by_class = defaultdict(lambda: {"reports": 0, "failed": 0, "specimens": 0, "below": 0})
    by_mat = defaultdict(lambda: {"tests": 0, "with_result": 0, "pass": 0, "fail": 0})
    turnaround = []
    for r in treg.recs:
        lab = labs.get(r.id)
        if lab is None:
            continue
        m = by_mat[lab.material or "other"]
        m["tests"] += 1
        if lab.result in ("pass", "fail"):
            m["with_result"] += 1
            m[lab.result] += 1
        start = lab.sampling_date
        end = lab.report_date or lab.test_date
        if start and end and end >= start:
            turnaround.append((end - start).days)
        fck = float(lab.fck) if lab.fck is not None else None
        vals = []
        for x in lab.lines or []:
            if x.get("role") == "strength28":
                try:
                    vals.append(float(x.get("value")))
                except (TypeError, ValueError):
                    pass
        if fck and vals:
            ok = len([v for v in vals if v >= fck])
            s28_ok += ok
            s28_all += len(vals)
            c = classes.get(lab.class_id)
            k = c.grade if c else (lab.grade or f"fck {fck:g}")
            b = by_class[k]
            b["fck"] = fck
            b["reports"] += 1
            b["failed"] += 1 if lab.result == "fail" else 0
            b["specimens"] += len(vals)
            b["below"] += len(vals) - ok
    tests = {
        "records": len(treg.recs), "with_result": len(with_res),
        "pass_rate": _pct(len([r for r in with_res if labs[r.id].result == "pass"]), len(with_res)),
        "first_time": _pct(len([r for r in orig if labs[r.id].result == "pass"]), len(orig)),
        "failed": len([r for r in with_res if labs[r.id].result == "fail"]),
        "open_failed": len(open_failed),
        "s28_pass": _pct(s28_ok, s28_all), "below_pct": _pct(s28_all - s28_ok, s28_all),
        "turnaround": _avg(turnaround),
        "by_material": [{"material": k, **v, "pass_rate": _pct(v["pass"], v["with_result"])} for k, v in sorted(by_mat.items())],
        "by_class": [{"grade": k, **v} for k, v in sorted(by_class.items())],
        "open_failed_list": [{"id": str(r.id), "number": r.number, "rev_no": r.rev_no, "title": r.title} for r in open_failed[:50]],
    }

    # NCRs: issue (submitted) -> corrective action (answered) -> close (an event into a closed state)
    cfg = settings_of(project)
    nreg = regs["ncr"]
    closed_ids = {s.id for s in db.scalars(select(WorkflowState).where(WorkflowState.category == "approved"))}
    close_at = {}
    if nreg.recs:
        for e in db.scalars(select(RecordEvent).where(RecordEvent.record_id.in_([r.id for r in nreg.recs]),
                                                      RecordEvent.to_state_id.in_(closed_ids))):
            close_at[e.record_id] = max(e.at, close_at.get(e.record_id, e.at))

    def ncr_fig(reg: _Reg) -> dict:
        closed = [r for r in reg.recs if r.state_category == "approved"]
        opened = [r for r in reg.recs if r.state_category != "approved"]
        close = {r.id: close_at.get(r.id) or r.answered_at for r in closed}
        limit = cfg["ncr_close_days"]
        cd = [_days(r.submitted_at, close[r.id]) for r in closed]
        return {"issued": len(reg.recs), "open": len(opened), "close_days": _avg(cd),
                "contractor_days": _avg([_days(r.submitted_at, r.answered_at) for r in reg.recs if r.answered_at]),
                "supervision_days": _avg([_days(r.answered_at, close[r.id]) for r in closed if r.answered_at and close[r.id]]),
                "on_time": _pct(len([x for x in cd if x is not None and x <= limit]), len([x for x in cd if x is not None])),
                "overdue": len([r for r in opened if _days(r.submitted_at, now) > limit])}
    ncr = ncr_fig(nreg)
    seen, repeat = set(), 0
    for r in sorted(nreg.recs, key=lambda r: r.submitted_at):
        key = (r.stage_id, r.topic_id) if r.topic_id else ("t", (r.title or "").strip().lower())
        if key in seen:
            repeat += 1
        seen.add(key)
    ncr["repeat"] = repeat

    rreg = regs["rfi"]

    def rfi_fig(reg: _Reg) -> dict:
        ans = [r for r in reg.recs if r.answered_at]
        return {"issued": len(reg.recs), "open": len([r for r in reg.recs if r.state_category == "submitted"]),
                "response_days": _avg([_days(r.submitted_at, r.answered_at) for r in ans]),
                "overdue": len([r for r in reg.recs if r.state_category == "submitted" and r.due_at and r.due_at < now])}
    rfi = rfi_fig(rreg)

    values = {
        "SUB_FIRST_PASS": sub["first_pass"], "SUB_CYCLE_DAYS": sub["review_days"], "SUB_CONTRACTOR_DAYS": sub["contractor_days"],
        "SUB_WITHIN_PERIOD": sub["within"], "SUB_OVERDUE": sub["overdue"], "SUB_OUTSTANDING": sub["outstanding"],
        "SUB_RESUB_INDEX": sub["resub_index"], "SUB_APPROVAL_PROGRESS": sub["approved_pct"],
        "IR_FIRST_PASS": ir["first_pass"], "IR_REJECTION": ir["rejected_pct"], "IR_RESPONSE_DAYS": ir["review_days"],
        "IR_CONTRACTOR_DAYS": ir["contractor_days"], "IR_BACKLOG": ir["overdue"], "IR_OUTSTANDING": ir["outstanding"],
        "TEST_PASS": tests["pass_rate"], "TEST_FIRST_TIME": tests["first_time"], "TEST_FAILED": tests["failed"],
        "TEST_OPEN_FAILED": tests["open_failed"], "TEST_28D_PASS": tests["s28_pass"], "CONC_BELOW_PCT": tests["below_pct"],
        "TEST_TURNAROUND": tests["turnaround"],
        "NCR_OPEN": ncr["open"], "NCR_CLOSE_DAYS": ncr["close_days"], "NCR_CONTRACTOR_DAYS": ncr["contractor_days"],
        "NCR_SUPERVISION_DAYS": ncr["supervision_days"], "NCR_ON_TIME": ncr["on_time"], "NCR_OVERDUE": ncr["overdue"],
        "NCR_REPEAT": ncr["repeat"], "RFI_RESPONSE_DAYS": rfi["response_days"], "RFI_OVERDUE": rfi["overdue"],
    }
    # a register with nothing in it shows no counts either ("0 overdue" of nothing is not a result)
    empty = {s: not regs[s].recs for s in SECTIONS}
    kpis = []
    for code, section, unit, direction, *_rest in DEFS:
        t = cfg["targets"][code]
        if not t["active"]:
            continue
        v = None if empty[section] else values[code]
        kpis.append({"code": code, "section": section, "unit": unit, "direction": direction, "value": v,
                     "green": t["green"], "amber": t["amber"], "qmp_ref": t["qmp_ref"],
                     "status": rag(v, direction, t["green"], t["amber"]),
                     "name_ar": DEF[code][7], "name_en": DEF[code][8], "formula_ar": DEF[code][9], "formula_en": DEF[code][10]})
    return {
        "kpis": kpis, "ncr_close_days": cfg["ncr_close_days"],
        "submittal": {**sub, "by_discipline": per_disc(regs["submittal"], lambda g: _review(g, now))},
        "inspection": {**ir, "by_discipline": per_disc(regs["inspection"], lambda g: _review(
            g, now, start_of=lambda r: max(x for x in (r.submitted_at, r.requested_for) if x)))},
        "test": tests,
        "ncr": {**ncr, "by_discipline": per_disc(nreg, ncr_fig)},
        "rfi": {**rfi, "by_discipline": per_disc(rreg, rfi_fig)},
    }
