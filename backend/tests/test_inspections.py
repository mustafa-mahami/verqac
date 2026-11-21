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
    while when.weekday() == 4:  # not on the default weekend (Friday): the period would roll past it
        when += timedelta(days=1)
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


def test_inspection_checklist(client, site):
    pid, hc, org = site["pid"], site["hc"], site["org"] if "org" in site else None
    types = client.get(f"/api/v1/projects/{pid}/structure", headers=hc).json()["types"]
    btype = next(t for t in types if t["name_en"] == "Buildings")
    st = client.post(f"/api/v1/projects/{pid}/apply-type", headers=hc, json={"project_type_id": btype["id"]}).json()
    structure = st["stages"][2]
    slabs = next(tp for tp in structure["topics"] if tp["name_en"] == "Slabs")
    assert any(x["ar"].startswith("الغطاء الخرساني") for x in slabs["checklist"])
    # off by default: no checklist on the request
    off = _ir(client, site, stage_id=structure["id"], topic_id=slabs["id"], all_locations=True)
    assert off["checklist"] == [] and st["checklists"] is False
    assert client.put(f"/api/v1/projects/{pid}/settings", headers=hc, json={"checklists": True}).json()["checklists"] is True
    # the project edits its own copy: keep three lines (English falls back to Arabic)
    slabs["checklist"] = [{"ar": "الشدّات", "en": "Formwork"}, {"ar": "الحديد", "en": ""}, {"ar": "التمديدات", "en": "MEP"}]
    st = client.put(f"/api/v1/projects/{pid}/stages", headers=hc, json=st["stages"]).json()
    assert next(tp for tp in st["stages"][2]["topics"] if tp["name_en"] == "Slabs")["checklist"][1] == {"ar": "الحديد", "en": "الحديد"}
    ir = _ir(client, site, stage_id=structure["id"], topic_id=slabs["id"], all_locations=True)
    assert [x["ar"] for x in ir["checklist"]] == ["الشدّات", "الحديد", "التمديدات"] and ir["checklist"][0]["result"] is None
    act(client, site["hqa"], ir["id"], "submit")
    url = f"/api/v1/records/{ir['id']}/transitions"
    # every line needs an answer
    r = client.post(url, headers=site["hce"], json={"action": "accept", "checklist": [{"result": "ok"}]})
    assert r.json()["detail"] == "checklist_incomplete"
    answers = [{"result": "ok"}, {"result": "nc", "note": "الغطاء 2 سم"}, {"result": "na"}]
    # a plain acceptance cannot carry a non-conforming line
    assert client.post(url, headers=site["hce"], json={"action": "accept", "checklist": answers}).json()["detail"] == "checklist_nonconforming"
    r = client.post(url, headers=site["hce"], json={"action": "accept_with_comments", "comment": "يُعدّل الغطاء قبل الصب",
                                                    "checklist": answers}).json()
    assert r["state"]["code"] == "accepted_with_comments"
    assert [x["result"] for x in r["checklist"]] == ["ok", "nc", "na"] and r["checklist"][1]["note"] == "الغطاء 2 سم"
    assert client.get(f"/api/v1/verify/{r['events'][-1]['stamp']}").json()["intact"] is True
    assert client.get(f"/api/v1/records/{ir['id']}/pdf?lang=ar", headers=site["hqa"]).status_code == 200
    # the checklist was fixed at submission: editing the topic later does not change the answered request
    slabs2 = next(tp for tp in st["stages"][2]["topics"] if tp["name_en"] == "Slabs")
    slabs2["checklist"] = [{"ar": "بند جديد", "en": "New"}]
    client.put(f"/api/v1/projects/{pid}/stages", headers=hc, json=st["stages"])
    assert len(client.get(f"/api/v1/records/{ir['id']}", headers=site["hqa"]).json()["checklist"]) == 3
    # switched off while a request waits: it can be answered without the checklist, which is dropped
    ir2 = _ir(client, site, stage_id=structure["id"], topic_id=slabs2["id"], all_locations=True)
    act(client, site["hqa"], ir2["id"], "submit")
    client.put(f"/api/v1/projects/{pid}/settings", headers=hc, json={"checklists": False})
    r = client.post(f"/api/v1/records/{ir2['id']}/transitions", headers=site["hce"], json={"action": "accept"}).json()
    assert r["state"]["code"] == "accepted" and r["checklist"] == []
