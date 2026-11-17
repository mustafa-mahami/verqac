from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.workcal import Calendar, add_period
from tests.test_inspections import _ir
from tests.test_records import act, new_sub, site, submit  # noqa: F401

TZ = ZoneInfo("Asia/Hebron")


def test_add_period_rules():
    hours = Calendar(start=time(7), end=time(15))
    thu = datetime(2026, 11, 19, 18, 0, tzinfo=TZ)  # Thursday evening; Friday off
    assert add_period(thu, 2, hours) == datetime(2026, 11, 21, 9, 0, tzinfo=TZ)
    assert add_period(thu.replace(hour=14, minute=30), 2, hours) == datetime(2026, 11, 21, 8, 30, tzinfo=TZ)
    days = Calendar(holidays={date(2026, 11, 22)})
    # 7 working days from Thursday: skips Friday 20, 27 and the holiday on Sunday 22
    assert add_period(thu.replace(hour=10), 7 * 24, days) == datetime(2026, 11, 29, 10, 0, tzinfo=TZ)
    assert add_period(thu, 5, None) == thu + timedelta(hours=5)


def test_org_and_project_calendar(client, site):
    hc, pid = site["hc"], site["pid"]
    org = client.get("/api/v1/auth/me", headers=hc).json()["orgs"][0]["org"]["id"]
    url = f"/api/v1/orgs/{org}/calendar"
    assert client.get(url, headers=hc).json() == {"weekend": [5], "holidays": []}
    # the whole of the next 10 days are an official holiday: a submittal's 7 days start after it
    today = datetime.now(TZ).date()
    hol = {"from": today.isoformat(), "to": (today + timedelta(days=10)).isoformat(), "name": "عطلة"}
    r = client.put(url, headers=hc, json={"weekend": [5, 6], "holidays": [hol]})
    assert r.status_code == 200 and r.json()["holidays"][0]["name"] == "عطلة"
    assert client.put(url, headers=site["hqa"], json={"weekend": [5]}).status_code == 403
    assert client.put(url, headers=hc, json={"weekend": [9]}).json()["detail"] == "invalid_weekend"
    rec = submit(client, site, new_sub(client, site))
    due = datetime.fromisoformat(rec["due_at"]).astimezone(TZ).date()
    assert due > today + timedelta(days=17)  # 10 holiday days + 7 working days (+ Fridays and Saturdays)
    # project: working hours and its own settings come back with the organization's calendar
    s = client.put(f"/api/v1/projects/{pid}/settings", headers=hc,
                   json={"calendar": {"weekend": None, "holidays": [], "work_start": "07:00", "work_end": "15:00"}}).json()
    assert s["calendar"]["work_start"] == "07:00" and s["org_calendar"]["weekend"] == [5, 6]
    bad = client.put(f"/api/v1/projects/{pid}/settings", headers=hc,
                     json={"calendar": {"work_start": "15:00", "work_end": "07:00"}})
    assert bad.json()["detail"] == "invalid_work_hours"
    # an inspection now waits for the end of the holiday and the start of the working day
    ir = act(client, site["hqa"], _ir(client, site)["id"], "submit").json()
    d = datetime.fromisoformat(ir["due_at"]).astimezone(TZ)
    assert d.date() > today + timedelta(days=10) and time(7) < d.time() <= time(15)
