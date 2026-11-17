from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.db import session_scope
from app.core.reminders import run_reminders
from app.models.records import Notification
from tests.test_inspections import _ir
from tests.test_records import act, new_sub, site, submit  # noqa: F401


def _events(rid):
    with session_scope(bypass=True) as s:
        return sorted((n.event, str(n.user_id)) for n in s.scalars(select(Notification).where(Notification.record_id == rid)))


def _kinds(rid, kind):
    return [e for e in _events(rid) if e[0] == kind]


def test_reply_and_resubmit_reminders(client, site):
    ir = _ir(client, site)
    done = act(client, site["hqa"], ir["id"], "submit").json()
    due = datetime.fromisoformat(done["due_at"])
    run_reminders(due - timedelta(minutes=60))
    assert _kinds(ir["id"], "reply_soon") == []  # too early
    run_reminders(due - timedelta(minutes=20))
    soon = _kinds(ir["id"], "reply_soon")
    assert (("reply_soon", site["ce"]) in soon) and len(soon) == 2  # the civil engineer and the consultant PM
    run_reminders(due - timedelta(minutes=10))
    assert len(_kinds(ir["id"], "reply_soon")) == 2  # once only
    run_reminders(due + timedelta(minutes=5))
    run_reminders(due + timedelta(days=2))
    assert len(_kinds(ir["id"], "reply_late")) == 2  # inspections: one late reminder
    # reject -> the contractor is reminded before the re-inspection deadline
    r = client.post(f"/api/v1/records/{ir['id']}/transitions", headers=site["hce"],
                    json={"action": "reject", "comment": "x"}).json()
    rdue = datetime.fromisoformat(r["resubmit_due_at"])
    run_reminders(rdue - timedelta(minutes=15))
    assert _kinds(ir["id"], "resub_soon")  # the QA engineer who submitted it (and the contractor PM)
    run_reminders(rdue + timedelta(minutes=1))
    assert _kinds(ir["id"], "resub_late")


def test_submittal_late_daily_and_setting(client, site):
    rec = submit(client, site, new_sub(client, site))
    due = datetime.fromisoformat(client.get(f"/api/v1/records/{rec['id']}", headers=site["hqa"]).json()["due_at"])
    run_reminders(due - timedelta(hours=12))
    assert _kinds(rec["id"], "reply_soon")
    for d in (1, 2, 2):
        run_reminders(due + timedelta(days=d, minutes=1))
    late = [e for e in _events(rec["id"]) if e[0] == "reply_late"]
    assert len(late) == 2 * 2  # two people, two different days
    # switched off in the project settings: nothing more
    url = f"/api/v1/projects/{site['pid']}/settings"
    assert client.put(url, headers=site["hc"], json={"reminders": False}).json()["reminders"] is False
    run_reminders(due + timedelta(days=3, minutes=1))
    assert len([e for e in _events(rec["id"]) if e[0] == "reply_late"]) == 4
