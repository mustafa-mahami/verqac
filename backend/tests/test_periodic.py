from datetime import date, timedelta

from app.api.periodic import period
from tests.test_daily import _structure
from tests.test_records import act, new_sub, site, submit  # noqa: F401


def test_period_bounds():
    # Friday off: the week runs Saturday to Friday
    assert period("week", date(2026, 11, 19), {5}) == (date(2026, 11, 14), date(2026, 11, 20))
    assert period("week", date(2026, 11, 14), {5}) == (date(2026, 11, 14), date(2026, 11, 20))
    # Friday and Saturday off: Sunday to Saturday
    assert period("week", date(2026, 11, 19), {5, 6}) == (date(2026, 11, 15), date(2026, 11, 21))
    assert period("month", date(2026, 2, 10), {5}) == (date(2026, 2, 1), date(2026, 2, 28))


def _report(client, site, day, body):
    rid = client.post(f"/api/v1/projects/{site['pid']}/daily-reports", headers=site["hqa"],
                      json={"report_date": day.isoformat(), "copy_previous": False}).json()["id"]
    r = client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json=body)
    assert r.status_code == 200, r.text
    act(client, site["hqa"], rid, "submit")
    return rid


def test_weekly_report(client, site):
    pid = site["pid"]
    st = _structure(client, site)
    structure = st["stages"][0]
    floors = st["locations"][0]["units"]
    start, end = period("week", date.today() - timedelta(days=14), {5})
    client.put(f"/api/v1/projects/{pid}/settings", headers=site["hc"],
               json={"dates": {"start_date": (start - timedelta(days=30)).isoformat(), "end_date": None}})
    # last week: floor 1 at 50 %
    before = _report(client, site, start - timedelta(days=3),
                     {"works": [{"stage_id": structure["id"], "location_ids": [floors[0]["id"]], "progress": 50}]})
    act(client, site["hce"], before, "approve")
    crew = [{"group": "labour", "name": "حداد", "count": 6}, {"group": "labour", "sub": "شركة النور", "name": "نجار", "count": 4}]
    a = _report(client, site, start + timedelta(days=1), {
        "crew": crew, "equipment": [{"name": "رافعة", "count": 1, "hours": 8, "idle_hours": 2}],
        "works": [{"stage_id": structure["id"], "location_ids": [floors[0]["id"]], "progress": 100, "qty": 30, "unit": "m3"}],
        "delays": [{"cause": "materials", "hours": 3, "description": "تأخر الحديد"}],
        "hse": {"toolbox": 1, "incidents": 0, "near_misses": 1}, "work_status": "partial",
        "materials": [{"material": "حديد", "qty": 12, "unit": "t", "supplier": "X"}]})
    act(client, site["hce"], a, "approve")
    b = _report(client, site, start + timedelta(days=2), {
        "crew": [{**crew[0], "count": 8}],
        "works": [{"stage_id": structure["id"], "location_ids": [floors[1]["id"]], "progress": 20, "qty": 10, "unit": "m3"}]})
    act(client, site["hce"], b, "approve")
    # submitted, not approved: not counted
    _report(client, site, start + timedelta(days=3), {"works": [{"stage_id": structure["id"], "location_ids": [floors[1]["id"]], "progress": 90}]})

    r = client.get(f"/api/v1/projects/{pid}/period-report", headers=site["hk"], params={"kind": "week", "day": start.isoformat()})
    assert r.status_code == 200, r.text
    o = r.json()
    assert (o["start"], o["end"], o["reports"], o["pending"]) == (start.isoformat(), end.isoformat(), 2, 1)
    assert o["partial"] == [(start + timedelta(days=1)).isoformat()]
    assert (start + timedelta(days=4)).isoformat() in o["missing"] and start.isoformat() in o["missing"]
    n = len(floors)
    s = next(x for x in o["stages"] if x["stage_id"] == structure["id"])
    assert s["start"] == round(50 / n, 1) and s["end"] == round(120 / n, 1) and s["days"] == 2
    assert s["qty"] == [{"qty": 40.0, "unit": "m3"}] and len(s["locations_ar"]) == 2
    assert o["progress_end"] > o["progress_start"] > 0
    assert o["crew_totals"]["labour"] == {"man_days": 18, "avg": 9.0, "peak": 10}
    smith = next(x for x in o["crew"] if x["name"] == "حداد")
    assert (smith["man_days"], smith["days"], smith["peak"]) == (14, 2, 8)
    assert o["equipment"][0] == {"name": "رافعة", "unit_days": 1, "days": 1, "hours": 8.0, "idle_hours": 2.0}
    assert o["delays"] == [{"cause": "materials", "count": 1, "hours": 3.0}]
    assert o["hse"] == {"incidents": 0, "near_misses": 1, "toolbox": 1}
    assert o["materials"][0]["material"] == "حديد"
    # the next week can be opened; the PDF prints in both languages
    assert o["next"] == (end + timedelta(days=1)).isoformat() and o["prev"] == (start - timedelta(days=7)).isoformat()
    for lang in ("ar", "en"):
        pdf = client.get(f"/api/v1/projects/{pid}/period-report/pdf", headers=site["hk"],
                         params={"kind": "week", "day": start.isoformat(), "lang": lang})
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    m = client.get(f"/api/v1/projects/{pid}/period-report", headers=site["hk"], params={"kind": "month", "day": start.isoformat()}).json()
    assert m["start"] == start.replace(day=1).isoformat() and m["reports"] >= 1


def test_requests_this_week(client, site):
    pid = site["pid"]
    rec = new_sub(client, site)
    submit(client, site, rec)
    o = client.get(f"/api/v1/projects/{pid}/period-report", headers=site["hk"], params={"kind": "week"}).json()
    row = next(x for x in o["requests"] if x["code"] == "submittal")
    assert (row["submitted"], row["open"], row["answered"]) == (1, 1, 0)
    act(client, site["hce"], rec["id"], "approve")
    o = client.get(f"/api/v1/projects/{pid}/period-report", headers=site["hk"], params={"kind": "week"}).json()
    row = next(x for x in o["requests"] if x["code"] == "submittal")
    assert (row["submitted"], row["open"], row["answered"], row["approved"]) == (1, 0, 1, 1)
    assert client.get(f"/api/v1/projects/{pid}/period-report", headers=site["hk"], params={"kind": "year"}).status_code == 422
