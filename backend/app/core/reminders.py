"""Deadline reminders: before and after the reply and resubmission deadlines.

A background thread in each API worker runs `run_reminders` every few minutes. Each reminder is
claimed in record_reminders first (insert ... on conflict do nothing), so two workers never send
the same one. Projects switch them off in their settings ("reminders").
"""
import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.db import session_scope
from app.core.notify import members_who_can, notify
from app.models.core import Project
from app.models.records import Record, RecordReminder, RecordType

log = logging.getLogger("verqac.reminders")

# how long before a deadline the "soon" reminder goes out, and whether "late" repeats daily
LEAD = {"inspection": timedelta(minutes=30), "material": timedelta(hours=2)}
DEFAULT_LEAD = timedelta(days=1)
DAILY_LATE = {"submittal", "rfi", "ncr"}
EVERY = 300  # seconds between runs


def reminders_on(project: Project) -> bool:
    return bool((project.settings or {}).get("reminders", True))


def _claim(db, rec: Record, kind: str, key: str) -> bool:
    res = db.execute(insert(RecordReminder).values(record_id=rec.id, kind=kind, key=key)
                     .on_conflict_do_nothing().returning(RecordReminder.record_id))
    return res.first() is not None


def _late_key(rt: RecordType, due: datetime, now: datetime) -> str:
    return f"d{(now - due).days}" if rt.code in DAILY_LATE else "once"


def _when(rt: RecordType, lang: str) -> str:
    lead = LEAD.get(rt.code, DEFAULT_LEAD)
    mins = int(lead.total_seconds() // 60)
    if mins < 60:
        return f"خلال {mins} دقيقة" if lang == "ar" else f"in {mins} minutes"
    hours = mins // 60
    if hours % 24 == 0:
        days = hours // 24
        return ("خلال يوم" if days == 1 else f"خلال {days} أيام") if lang == "ar" else (
            "within a day" if days == 1 else f"within {days} days")
    return f"خلال {hours} ساعة" if lang == "ar" else f"within {hours} hours"


def _reply_users(c, project: Project, rec: Record, rt: RecordType) -> set:
    from app.api.records import _responders, routing
    to_manager = rec.assigned_to is None and routing(project, rt) == "manager"
    return {m.user_id for m, r in _responders(c, rec, rt)
            if r.act_on_behalf or (not to_manager and (rec.assigned_to is None or m.user_id == rec.assigned_to))}


def _author_users(c, rec: Record, rt: RecordType) -> set:
    users = {rec.created_by, rec.submitted_by}
    users |= {m.user_id for m, r in members_who_can(c, rec.project_id, rec.from_party_id, rt, "create",
                                                     rec.discipline_id) if r.manage_project}
    return users


def run_reminders(now: datetime | None = None) -> int:
    """Send the reminders that are due; returns how many went out."""
    from app.api.records import RESUBMIT_STATES
    now = now or datetime.now(UTC)
    horizon = now + max([DEFAULT_LEAD, *LEAD.values()])
    sent = 0
    bg = BackgroundTasks()
    with session_scope(bypass=True) as db:
        c = SimpleNamespace(db=db, user=SimpleNamespace(id=None))
        types = {t.id: t for t in db.scalars(select(RecordType))}
        projects: dict = {}

        def project(pid):
            if pid not in projects:
                projects[pid] = db.get(Project, pid)
            return projects[pid]

        def send(rec, rt, kind, key, users, ar, en):
            nonlocal sent
            if users and _claim(db, rec, kind, key):
                notify(c, bg, project=project(rec.project_id), rec=rec, event=kind, user_ids=users,
                       title_ar=ar, title_en=en, body=rec.title)
                sent += 1

        waiting = db.scalars(select(Record).where(Record.state_category == "submitted", Record.due_at.is_not(None),
                                                  Record.due_at <= horizon))
        for rec in waiting:
            rt, p = types[rec.record_type_id], project(rec.project_id)
            if not reminders_on(p):
                continue
            head_ar, head_en = f"{rt.name_ar} {rec.number} R{rec.rev_no}", f"{rt.name_en} {rec.number} R{rec.rev_no}"
            lead = LEAD.get(rt.code, DEFAULT_LEAD)
            if rec.due_at > now:
                # skip "soon" when the whole period is shorter than the lead (it was just submitted)
                if rec.due_at - lead <= now and (rec.submitted_at is None or rec.due_at - lead > rec.submitted_at):
                    send(rec, rt, "reply_soon", "once", _reply_users(c, p, rec, rt),
                         f"{head_ar}: ينتهي موعد الرد {_when(rt, 'ar')}", f"{head_en}: reply due {_when(rt, 'en')}")
            else:
                send(rec, rt, "reply_late", _late_key(rt, rec.due_at, now), _reply_users(c, p, rec, rt),
                     f"{head_ar}: تأخر الرد، انتهى الموعد", f"{head_en}: reply overdue")

        pending = db.scalars(select(Record).where(Record.state_category.in_(RESUBMIT_STATES),
                                                  Record.resubmit_due_at.is_not(None), Record.resubmitted_at.is_(None),
                                                  Record.resubmit_due_at <= horizon))
        for rec in pending:
            rt, p = types[rec.record_type_id], project(rec.project_id)
            if not reminders_on(p):
                continue
            head_ar, head_en = f"{rt.name_ar} {rec.number} R{rec.rev_no}", f"{rt.name_en} {rec.number} R{rec.rev_no}"
            lead = LEAD.get(rt.code, DEFAULT_LEAD)
            if rec.resubmit_due_at > now:
                if rec.resubmit_due_at - lead <= now and (rec.answered_at is None or rec.resubmit_due_at - lead > rec.answered_at):
                    send(rec, rt, "resub_soon", "once", _author_users(c, rec, rt),
                         f"{head_ar}: تنتهي مهلة إعادة التقديم {_when(rt, 'ar')}",
                         f"{head_en}: resubmission due {_when(rt, 'en')}")
            else:
                send(rec, rt, "resub_late", _late_key(rt, rec.resubmit_due_at, now), _author_users(c, rec, rt),
                     f"{head_ar}: تأخرت إعادة التقديم", f"{head_en}: resubmission overdue")
    # e-mail and push go out after the commit, like for a request
    for task in bg.tasks:
        try:
            task.func(*task.args, **task.kwargs)
        except Exception:  # noqa: BLE001 - one failed send must not stop the rest
            log.exception("reminder send failed")
    return sent


def _loop() -> None:
    time.sleep(30)  # let the app finish starting
    while True:
        try:
            n = run_reminders()
            if n:
                log.info("sent %s reminders", n)
        except Exception:  # noqa: BLE001 - keep the loop alive
            log.exception("reminders run failed")
        time.sleep(EVERY)


def start() -> None:
    threading.Thread(target=_loop, name="verqac-reminders", daemon=True).start()
