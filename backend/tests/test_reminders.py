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


def test_missing_daily_report(client, site):
    from zoneinfo import ZoneInfo

    from app.core.workcal import Calendar
    pid = site["pid"]
    tz = ZoneInfo("Asia/Hebron")
    cal = Calendar()
    # a working day d, with the day before it a working day too, and a first report before both
    d = datetime.now(tz).date() - timedelta(days=10)
    while not (cal.working(d) and cal.working(d - timedelta(days=1))):
        d -= timedelta(days=1)
    first = d - timedelta(days=1)
    client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"], json={"report_date": first.isoformat()})

    def missing():
        with session_scope(bypass=True) as s:
            return sorted((n.title_en, str(n.user_id)) for n in s.scalars(
                select(Notification).where(Notification.project_id == pid, Notification.event == "dr_missing")))

    morning = datetime.combine(d + timedelta(days=1), datetime.min.time(), tz)
    run_reminders((morning + timedelta(hours=7)).astimezone(UTC))
    assert missing() == []  # too early in the morning
    run_reminders((morning + timedelta(hours=10)).astimezone(UTC))
    got = missing()
    qa = client.get("/api/v1/auth/me", headers=site["hqa"]).json()["user"]["id"]
    assert got and all(d.isoformat() in t for t, _ in got) and qa in {u for _, u in got}
    assert site["ce"] not in {u for _, u in got}  # supervision writes no daily reports
    run_reminders((morning + timedelta(hours=11)).astimezone(UTC))
    assert len(missing()) == len(got)  # once only
    # the day of the first report has one: nothing for it
    run_reminders((datetime.combine(d, datetime.min.time(), tz) + timedelta(hours=10)).astimezone(UTC))
    assert len(missing()) == len(got)
    # reminders off in the project: nothing
    client.put(f"/api/v1/projects/{pid}/settings", headers=site["hc"], json={"reminders": False})
    run_reminders((morning + timedelta(days=1, hours=10)).astimezone(UTC))
    assert len(missing()) == len(got)
    r = client.get("/api/v1/notifications", headers=site["hqa"]).json()["items"][0]
    assert r["event"] == "dr_missing" and r["project_id"] == pid and r["record_id"] is None
