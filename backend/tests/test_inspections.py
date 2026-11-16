from datetime import UTC, datetime, timedelta

from tests.test_records import act, site  # noqa: F401


def _ir(client, s, h=None, **kw):
    r = client.post(f"/api/v1/projects/{s['pid']}/records", headers=h or s["hqa"], json={
        "record_type": "inspection", "title": "فحص أعمدة", "discipline_id": s["cdisc"]["C"], **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_inspection_flow_and_periods(client, site):
    meta = client.get(f"/api/v1/projects/{site['pid']}/records/meta?type=inspection", headers=site["hqa"]).json()
    assert meta["can_create"] and meta["reply_hours"] == 2
    assert [s["name_ar"] for s in meta["states"]][2] == "مقبول"
    ir = _ir(client, site)
    assert ir["number"].endswith("-IR-C-001") and ir["record_type"]["code"] == "inspection"
    # reply due 2 hours after submission when no time was asked for
    done = act(client, site["hqa"], ir["id"], "submit").json()
    delta = datetime.fromisoformat(done["due_at"]) - datetime.fromisoformat(done["submitted_at"])
    assert round(delta.total_seconds() / 60) == 120
    # inspection asked for tomorrow 10:00 -> due 12:00
    when = (datetime.now(UTC) + timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)
    ir2 = _ir(client, site, requested_for=when.isoformat())
    done2 = act(client, site["hqa"], ir2["id"], "submit").json()
    assert datetime.fromisoformat(done2["due_at"]) == when + timedelta(hours=2)
    # the consultant engineer answers; performed time is recorded; reject asks for re-inspection in 2 hours
    t = {x["action"] for x in client.get(f"/api/v1/records/{ir['id']}", headers=site["hce"]).json()["transitions"]}
    assert t == {"accept", "accept_with_comments", "reject"}
    performed = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
    r = client.post(f"/api/v1/records/{ir['id']}/transitions", headers=site["hce"],
                    json={"action": "reject", "comment": "تباعد الكانات غير صحيح", "performed_at": performed}).json()
    assert r["state"]["code"] == "rejected" and r["performed_at"] and r["resubmit_due_at"]
    gap = datetime.fromisoformat(r["resubmit_due_at"]) - datetime.fromisoformat(r["answered_at"])
    assert round(gap.total_seconds() / 60) == 120
    stamp = r["events"][-1]["stamp"]
    assert client.get(f"/api/v1/verify/{stamp}").json()["intact"] is True
    assert client.get(f"/api/v1/records/{ir['id']}/pdf?lang=ar", headers=site["hqa"]).status_code == 200
    # performed in the future is refused
    future = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
    assert client.post(f"/api/v1/records/{ir2['id']}/transitions", headers=site["hce"],
                       json={"action": "accept", "performed_at": future}).json()["detail"] == "performed_in_future"


def test_inspection_links_to_submittals(client, site):
    pid, hc = site["pid"], site["hc"]
    sub = client.post(f"/api/v1/projects/{pid}/records", headers=site["hqa"], json={
        "title": "حديد تسليح", "discipline_id": site["cdisc"]["C"]}).json()
    act(client, site["hqa"], sub["id"], "submit")
    # links off: no warning
    ir = _ir(client, site, linked_ids=[sub["id"]])
    assert ir["link_warning"] is None and ir["linked"][0]["number"] == sub["number"]
    client.put(f"/api/v1/projects/{pid}/settings", headers=hc, json={"link_submittals": True})
    got = client.get(f"/api/v1/records/{ir['id']}", headers=site["hqa"]).json()
    assert got["link_warning"] == "not_approved"
    act(client, site["hce"], sub["id"], "approve")
    assert client.get(f"/api/v1/records/{ir['id']}", headers=site["hqa"]).json()["link_warning"] is None
    assert _ir(client, site)["link_warning"] == "no_link"
    cands = client.get(f"/api/v1/projects/{pid}/link-candidates", headers=site["hqa"]).json()
    assert cands[0]["id"] == sub["id"] and cands[0]["state"]["category"] == "approved"
    # only submittals of this project can be linked
    bad = client.post(f"/api/v1/projects/{pid}/records", headers=site["hqa"], json={
        "record_type": "inspection", "title": "xyz", "discipline_id": site["cdisc"]["C"], "linked_ids": [ir["id"]]})
    assert bad.json()["detail"] == "invalid_link"
