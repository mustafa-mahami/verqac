"""The project's money: contract amount and currency, what was paid, and the cash-flow curves.

Four cumulative curves in the project's currency:
  planned   = contract x the programme's planned % (current approved programme; and its first one, the baseline)
  earned    = contract x the approved progress % (the daily snapshots)
  certified = payment applications certified by supervision (with the retention kept), on the day certified
  payable   = their net amount to pay (after retention and recoveries), on the same day
  paid      = what was paid (advance payment included), on the day paid
Only the roles given the payment type see any of it.
"""
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.access import project_access, require
from app.core.audit import audit
from app.core.deps import Ctx, ctx
from app.models.daily import ProgressSnapshot
from app.models.records import Record, RecordType

router = APIRouter(tags=["finance"])
TZ = ZoneInfo("Asia/Hebron")
CURRENCIES = ("ILS", "USD", "JOD", "EUR")


class Receipt(BaseModel):
    id: str | None = None
    day: date
    amount: float = Field(gt=0, le=1e12)
    kind: Literal["advance", "payment", "other"] = "payment"
    record_id: uuid.UUID | None = None  # the payment application it pays
    note: str | None = Field(default=None, max_length=300)


class FinanceSettings(BaseModel):
    contract_value: float | None = Field(default=None, ge=0, le=1e12)
    currency: str = Field(default="ILS", max_length=3)


class Point(BaseModel):
    day: date
    value: float


class MonthRow(BaseModel):
    month: str
    planned: float | None
    earned: float | None
    certified: float
    payable: float
    paid: float


class FinanceOut(BaseModel):
    contract_value: float | None
    currency: str
    can_edit: bool  # contract amount and currency
    can_pay: bool  # record what was paid
    receipts: list[Receipt]
    applications: list[dict]  # certified / pending payment applications, for linking a receipt
    planned: list[Point]
    baseline: list[Point]
    earned: list[Point]
    certified: list[Point]
    payable: list[Point]
    paid: list[Point]
    months: list[MonthRow]
    totals: dict


def _perms(c: Ctx, a):
    from app.api.records import Perms
    rt = c.db.scalar(select(RecordType).where(RecordType.org_id.is_(None), RecordType.code == "payment"))
    return rt, Perms(c, a, rt)


def access(c: Ctx, project_id: uuid.UUID):
    """(project access, payment type, perms); 404 for whoever may not see the project's money."""
    a = project_access(c, project_id)
    rt, p = _perms(c, a)
    if rt is None or not p.can("view"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return a, rt, p


def settings_of(project) -> dict:
    f = dict((project.settings or {}).get("finance") or {})
    return {"contract_value": f.get("contract_value"), "currency": f.get("currency") or "ILS", "receipts": f.get("receipts") or []}


def _save(project, f: dict) -> None:
    project.settings = {**(project.settings or {}), "finance": f}


def _cum(events: list[tuple[date, float]]) -> list[Point]:
    out, total = [], 0.0
    by = defaultdict(float)
    for d, v in events:
        by[d] += v
    for d in sorted(by):
        total += by[d]
        out.append(Point(day=d, value=round(total, 2)))
    return out


def _at(points: list[Point], day: date) -> float | None:
    """The cumulative value on that day (the last point on or before it)."""
    v = None
    for p in points:
        if p.day > day:
            break
        v = p.value
    return v


def build(c: Ctx, a, rt) -> FinanceOut:
    from app.api.daily import _units
    from app.api.programme import programmes
    from app.core.programme import plan_cells, series
    from app.models.structure import ProjectStage
    project = a.project
    f = settings_of(project)
    cv = f["contract_value"] or 0.0
    stages = list(c.db.scalars(select(ProjectStage).where(ProjectStage.project_id == project.id, ProjectStage.is_active)))
    units = _units(c.db, project.id)
    planned, baseline = [], []
    base, cur = programmes(c.db, project.id)
    if cv and cur is not None:
        plan = plan_cells(cur.lines)
        planned = [Point(day=date.fromisoformat(x["day"]), value=round(cv * x["planned"] / 100, 2)) for x in series(plan, stages, units)]
        if base is not None and base.record_id != cur.record_id:
            bplan = plan_cells(base.lines)
            baseline = [Point(day=date.fromisoformat(x["day"]), value=round(cv * x["planned"] / 100, 2))
                        for x in series(bplan, stages, units)]
    earned = [Point(day=s.day, value=round(cv * float(s.actual) / 100, 2)) for s in c.db.scalars(
        select(ProgressSnapshot).where(ProgressSnapshot.project_id == project.id).order_by(ProgressSnapshot.day))] if cv else []
    apps = list(c.db.scalars(select(Record).where(Record.project_id == project.id, Record.record_type_id == rt.id,
                                                  Record.state_category.notin_(("draft", "cancelled")))
                             .order_by(Record.number, Record.rev_no)))

    def num(r, k):
        try:
            return float((r.custom or {}).get(k) or 0)
        except ValueError:
            return 0.0
    done = [r for r in apps if r.state_category == "approved"]
    certified = _cum([(r.answered_at.astimezone(TZ).date(), num(r, "certified")) for r in done if r.answered_at])
    payable_c = _cum([(r.answered_at.astimezone(TZ).date(), num(r, "payable")) for r in done if r.answered_at])
    receipts = [Receipt(**x) for x in f["receipts"]]
    paid = _cum([(x.day, x.amount) for x in receipts])
    today = datetime.now(TZ).date()
    # months from the first to the last thing that happened (or is planned)
    days = [p.day for s in (planned, earned, certified, payable_c, paid) for p in s]
    months = []
    if days:
        m, last = min(days).replace(day=1), max(days)
        while m <= last:
            nxt = (m + timedelta(days=32)).replace(day=1)
            end = nxt - timedelta(days=1)
            months.append(MonthRow(month=m.strftime("%Y-%m"), planned=_at(planned, end), earned=_at(earned, min(end, today)) if m <= today else None,
                                   certified=_at(certified, end) or 0.0, payable=_at(payable_c, end) or 0.0,
                                   paid=_at(paid, end) or 0.0))
            m = nxt
    payable = sum(num(r, "payable") for r in done)
    advance = sum(x.amount for x in receipts if x.kind == "advance")
    paid_total = sum(x.amount for x in receipts)
    totals = {
        "contract": cv or None,
        "planned": _at(planned, today), "earned": earned[-1].value if earned else None,
        "certified": certified[-1].value if certified else 0.0, "payable": round(payable, 2),
        "paid": round(paid_total, 2), "advance": round(advance, 2),
        "unpaid": round(max(0.0, payable - (paid_total - advance)), 2),  # certified for payment, not paid yet
        "claimed_pending": round(sum(num(r, "claimed") for r in apps if r.state_category == "submitted"), 2),
    }
    _, p = _perms(c, a)
    return FinanceOut(contract_value=f["contract_value"], currency=f["currency"], can_edit=a.can_manage_project,
                      can_pay=p.can("create") or p.can("respond"), receipts=receipts,
                      applications=[{"id": str(r.id), "number": r.number, "rev_no": r.rev_no, "state": r.state_category,
                                     "payable": num(r, "payable"), "certified": num(r, "certified"), "claimed": num(r, "claimed")}
                                    for r in apps],
                      planned=planned, baseline=baseline, earned=earned, certified=certified, payable=payable_c, paid=paid, months=months, totals=totals)


@router.get("/projects/{project_id}/finance", response_model=FinanceOut)
def get_finance(project_id: uuid.UUID, c: Ctx = Depends(ctx)):
    a, rt, _ = access(c, project_id)
    return build(c, a, rt)


@router.put("/projects/{project_id}/finance/settings", response_model=FinanceOut)
def put_finance_settings(project_id: uuid.UUID, body: FinanceSettings, c: Ctx = Depends(ctx)):
    a, rt, _ = access(c, project_id)
    require(a.can_manage_project, "manage_project_required")
    cur = body.currency.upper()
    if cur not in CURRENCIES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_currency")
    f = settings_of(a.project)
    f.update(contract_value=body.contract_value, currency=cur)
    _save(a.project, f)
    audit(c.db, entity="project", action="finance_settings", entity_id=project_id, actor=c.user.id, org_id=a.project.owner_org_id,
          project_id=project_id, changes={"contract_value": body.contract_value, "currency": cur}, ip=c.meta.ip,
          user_agent=c.meta.user_agent)
    c.db.flush()
    return build(c, a, rt)


@router.post("/projects/{project_id}/finance/receipts", response_model=FinanceOut, status_code=201)
def add_receipt(project_id: uuid.UUID, body: Receipt, c: Ctx = Depends(ctx)):
    """Money paid: the advance payment, a certified application (its number), or other."""
    a, rt, p = access(c, project_id)
    require(p.can("create") or p.can("respond"), "cannot_record_payment")
    if body.day > datetime.now(TZ).date():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "payment_in_future")
    if body.record_id is not None:
        r = c.db.get(Record, body.record_id)
        if r is None or r.project_id != a.project.id or r.record_type_id != rt.id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_application")
    f = settings_of(a.project)
    x = body.model_dump(mode="json") | {"id": uuid.uuid4().hex[:12], "by": str(c.user.id), "at": datetime.now(UTC).isoformat()}
    f["receipts"] = sorted([*f["receipts"], x], key=lambda y: y["day"])
    _save(a.project, f)
    audit(c.db, entity="project", action="payment_received", entity_id=project_id, actor=c.user.id, org_id=a.project.owner_org_id,
          project_id=project_id, changes=x, ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return build(c, a, rt)


@router.delete("/projects/{project_id}/finance/receipts/{receipt_id}", response_model=FinanceOut)
def delete_receipt(project_id: uuid.UUID, receipt_id: str, c: Ctx = Depends(ctx)):
    a, rt, p = access(c, project_id)
    require(p.can("create") or p.can("respond"), "cannot_record_payment")
    f = settings_of(a.project)
    gone = [x for x in f["receipts"] if x.get("id") == receipt_id]
    if not gone:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    f["receipts"] = [x for x in f["receipts"] if x.get("id") != receipt_id]
    _save(a.project, f)
    audit(c.db, entity="project", action="payment_removed", entity_id=project_id, actor=c.user.id, org_id=a.project.owner_org_id,
          project_id=project_id, changes=gone[0], ip=c.meta.ip, user_agent=c.meta.user_agent)
    c.db.flush()
    return build(c, a, rt)
