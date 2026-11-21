from datetime import date, timedelta

from tests.test_daily import _structure
from tests.test_records import act, site  # noqa: F401


def test_whole_stage_progress(client, site):
    pid = site["pid"]
    st = _structure(client, site)
    stages = st["stages"]
    stages[2]["scope"] = "whole"
    r = client.put(f"/api/v1/projects/{pid}/stages", headers=site["hc"], json=stages)
    assert r.status_code == 200, r.text
    stg = r.json()["stages"][2]
    topic = stg["topics"][0]["id"] if stg["topics"] else None
    d1 = date.today() - timedelta(days=2)
    rid = client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"], json={"report_date": d1.isoformat()}).json()["id"]
    body = {"works": [{"stage_id": stg["id"], "topic_id": topic, "location_ids": [], "all_locations": False, "progress": 40}]}
    r = client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json=body)
    assert r.status_code == 200, r.text
    act(client, site["hqa"], rid, "submit")
    assert act(client, site["hce"], rid, "approve").json()["state"]["code"] == "approved"
    p = client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()
    assert p["stages"][stg["id"]] == 40 and p["as_of"] == d1.isoformat()


def test_location_required_and_rebuild(client, site):
    pid = site["pid"]
    st = _structure(client, site)
    stages = st["stages"]
    stg = stages[2]  # per location
    d1 = date.today() - timedelta(days=2)
    rid = client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"], json={"report_date": d1.isoformat()}).json()["id"]
    body = {"works": [{"stage_id": stg["id"], "location_ids": [], "all_locations": False, "progress": 40}]}
    client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json=body)
    # a % with no location would count nowhere: refused at submission
    r = act(client, site["hqa"], rid, "submit")
    assert r.status_code == 422 and r.json()["detail"] == "dr_location_required"
    # the stage becomes whole-project (as intended): now it is fine, and approved
    stages[2]["scope"] = "whole"
    client.put(f"/api/v1/projects/{pid}/stages", headers=site["hc"], json=stages)
    act(client, site["hqa"], rid, "submit")
    act(client, site["hce"], rid, "approve")
    assert client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()["stages"][stg["id"]] == 40
    # the stage goes back per location for all floors... then the manager recounts from the approved reports
    assert client.post(f"/api/v1/projects/{pid}/progress/rebuild", headers=site["hk"]).status_code == 403
    r = client.post(f"/api/v1/projects/{pid}/progress/rebuild", headers=site["hc"])
    assert r.status_code == 200 and r.json()["stages"][stg["id"]] == 40 and len(r.json()["snapshots"]) == 1
    # once approved reports gave the stage a %, its scope is locked (it would move or drop that progress)
    st2 = client.get(f"/api/v1/projects/{pid}/structure", headers=site["hc"]).json()
    assert next(x for x in st2["stages"] if x["id"] == stg["id"])["scope_locked"] is True
    stages[2]["scope"] = "per_location"
    r = client.put(f"/api/v1/projects/{pid}/stages", headers=site["hc"], json=stages)
    assert r.status_code == 409 and r.json()["detail"] == "stage_scope_locked"
    assert client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()["stages"][stg["id"]] == 40
    stages[2]["scope"] = "whole"
    # a stage without approved progress still changes scope freely
    stages[3]["scope"] = "whole"
    assert client.put(f"/api/v1/projects/{pid}/stages", headers=site["hc"], json=stages).status_code == 200


def test_actual_dates(client, site):
    pid = site["pid"]
    st = _structure(client, site)
    stg, floor = st["stages"][2], st["locations"][0]["units"][0]
    d1 = date.today() - timedelta(days=2)
    rid = client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"], json={"report_date": d1.isoformat()}).json()["id"]
    began, ended = d1 - timedelta(days=60), d1 - timedelta(days=10)
    line = {"stage_id": stg["id"], "location_ids": [floor["id"]], "progress": 100,
            "actual_start": began.isoformat(), "actual_finish": ended.isoformat()}
    # off by default: the dates are dropped
    r = client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json={"works": [line]}).json()
    assert r["works"][0]["actual_start"] is None
    s = client.get(f"/api/v1/projects/{pid}/daily-settings", headers=site["hc"]).json()
    s["actual_dates"] = True
    assert client.put(f"/api/v1/projects/{pid}/daily-settings", headers=site["hc"], json=s).json()["actual_dates"] is True
    bad = client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json={"works": [{**line, "progress": 60}]})
    assert bad.status_code == 422 and bad.json()["detail"] == "dr_actual_finish_needs_100"
    bad = client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json={"works": [{**line, "actual_start": (d1 + timedelta(days=1)).isoformat()}]})
    assert bad.status_code == 422
    r = client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json={"works": [line]})
    assert r.status_code == 200 and r.json()["works"][0]["actual_start"] == began.isoformat()
    act(client, site["hqa"], rid, "submit")
    act(client, site["hce"], rid, "approve")
    cell = next(c for c in client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()["cells"]
                if c["location_id"] == floor["id"] and c["stage_id"] == stg["id"])
    assert cell["started_on"] == began.isoformat() and cell["finished_on"] == ended.isoformat()


def test_forecast_basis_setting(client, site):
    pid = site["pid"]
    s = client.get(f"/api/v1/projects/{pid}/daily-settings", headers=site["hc"]).json()
    assert s["forecast_basis"] == "planned"
    s.update(forecast=True, forecast_basis="pace")
    assert client.put(f"/api/v1/projects/{pid}/daily-settings", headers=site["hc"], json=s).json()["forecast_basis"] == "pace"
    s["forecast_basis"] = "magic"
    assert client.put(f"/api/v1/projects/{pid}/daily-settings", headers=site["hc"], json=s).status_code == 422
