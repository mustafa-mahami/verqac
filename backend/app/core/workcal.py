"""Working calendar: weekly days off, official holidays and working hours.

The organization that owns a project keeps its calendar (weekend + official holidays); a project can
add its own holidays, use another weekend, and set working hours. Reply and resubmission periods
are counted on it:
  - whole days (multiples of 24 h) are working days, keeping the time of day;
  - the remaining hours are working hours when the project has them (an inspection asked for at
    18:00 starts counting at the next morning), otherwise clock hours on working days only.
Weekdays are 0 = Sunday ... 6 = Saturday.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

DEFAULT_WEEKEND = [5]  # Friday


@dataclass
class Calendar:
    weekend: set[int] = field(default_factory=lambda: set(DEFAULT_WEEKEND))
    holidays: set[date] = field(default_factory=set)
    start: time | None = None  # working hours; None = the whole day
    end: time | None = None
    tz: ZoneInfo = field(default_factory=lambda: ZoneInfo("Asia/Hebron"))

    def working(self, d: date) -> bool:
        return (d.weekday() + 1) % 7 not in self.weekend and d not in self.holidays


def holiday_dates(items) -> set[date]:
    out = set()
    for h in items or []:
        a = date.fromisoformat(h["from"])
        b = date.fromisoformat(h.get("to") or h["from"])
        while a <= b:
            out.add(a)
            a += timedelta(days=1)
    return out


def _hm(v: str | None) -> time | None:
    return time.fromisoformat(v) if v else None


def org_calendar(org) -> dict:
    cal = (org.settings or {}).get("calendar", {}) if org is not None else {}
    return {"weekend": cal.get("weekend", DEFAULT_WEEKEND), "holidays": cal.get("holidays", [])}


def calendar_for(db, project) -> Calendar:
    from app.core.db import session_scope
    from app.models.core import Organization
    with session_scope(bypass=True) as s:  # whoever asks: the owner organization's calendar applies
        org = s.scalar(select(Organization).where(Organization.id == project.owner_org_id))
        oc, tz = org_calendar(org), (org.timezone if org is not None else "Asia/Hebron")
    pc = (project.settings or {}).get("calendar", {})
    weekend = pc.get("weekend")
    return Calendar(weekend=set(oc["weekend"] if weekend is None else weekend),
                    holidays=holiday_dates(oc["holidays"]) | holiday_dates(pc.get("holidays")),
                    start=_hm(pc.get("work_start")), end=_hm(pc.get("work_end")), tz=ZoneInfo(tz))


def _next_working_day(cal: Calendar, d: date) -> date:
    for _ in range(400):  # a whole year off would be a configuration error
        if cal.working(d):
            return d
        d += timedelta(days=1)
    return d


def add_period(start: datetime, hours: int, cal: Calendar | None) -> datetime:
    if cal is None:
        return start + timedelta(hours=hours)
    t = start.astimezone(cal.tz)
    hours_on = cal.start is not None and cal.end is not None and cal.start < cal.end
    if hours_on:  # outside working hours the clock waits for the next working moment
        d = t.date()
        if not cal.working(d) or t.time() >= cal.end:
            d = _next_working_day(cal, d + timedelta(days=1) if cal.working(d) else d)
            t = datetime.combine(d, cal.start, cal.tz)
        elif t.time() < cal.start:
            t = datetime.combine(d, cal.start, cal.tz)
    days, rem = divmod(hours, 24)
    for _ in range(days):
        d = _next_working_day(cal, t.date() + timedelta(days=1))
        t = datetime.combine(d, t.time(), cal.tz)
    if not cal.working(t.date()):  # started on a day off without working hours
        t = datetime.combine(_next_working_day(cal, t.date()), time(0), cal.tz)
    left = timedelta(hours=rem)
    for _ in range(4000):
        if left <= timedelta(0):
            break
        d = t.date()
        if not cal.working(d):
            t = datetime.combine(_next_working_day(cal, d), cal.start if hours_on else time(0), cal.tz)
            continue
        end = datetime.combine(d, cal.end, cal.tz) if hours_on else datetime.combine(d + timedelta(days=1), time(0), cal.tz)
        if t >= end:
            nd = _next_working_day(cal, d + timedelta(days=1))
            t = datetime.combine(nd, cal.start if hours_on else time(0), cal.tz)
            continue
        step = min(left, end - t)
        t += step
        left -= step
    return t.astimezone(start.tzinfo)
