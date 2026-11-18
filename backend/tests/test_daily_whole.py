from datetime import date, timedelta

from tests.test_daily import _structure
from tests.test_records import act, site  # noqa: F401


def test_whole_stage_progress(client, site):
    pid = site["pid"]
    st = _structure(client, site)
    stages = st["stages"]
    stages[0]["scope"] = "whole"
    r = client.put(f"/api/v1/projects/{pid}/stages", headers=site["hc"], json=stages)
    assert r.status_code == 200, r.text
    stg = r.json()["stages"][0]
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
    stg = stages[0]  # per location
    d1 = date.today() - timedelta(days=2)
    rid = client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"], json={"report_date": d1.isoformat()}).json()["id"]
    body = {"works": [{"stage_id": stg["id"], "location_ids": [], "all_locations": False, "progress": 40}]}
    client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json=body)
    # a % with no location would count nowhere: refused at submission
    r = act(client, site["hqa"], rid, "submit")
    assert r.status_code == 422 and r.json()["detail"] == "dr_location_required"
    # the stage becomes whole-project (as intended): now it is fine, and approved
    stages[0]["scope"] = "whole"
    client.put(f"/api/v1/projects/{pid}/stages", headers=site["hc"], json=stages)
    act(client, site["hqa"], rid, "submit")
    act(client, site["hce"], rid, "approve")
    assert client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()["stages"][stg["id"]] == 40
    # the stage goes back per location for all floors... then the manager recounts from the approved reports
    assert client.post(f"/api/v1/projects/{pid}/progress/rebuild", headers=site["hk"]).status_code == 403
    r = client.post(f"/api/v1/projects/{pid}/progress/rebuild", headers=site["hc"])
    assert r.status_code == 200 and r.json()["stages"][stg["id"]] == 40 and len(r.json()["snapshots"]) == 1
