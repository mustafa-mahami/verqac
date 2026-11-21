from tests.test_records import act, site  # noqa: F401 (fixture)


def _doc(client, s, h, **custom):
    r = client.post(f"/api/v1/projects/{s['pid']}/records", headers=h, json={
        "record_type": "document", "title": "كتاب إزالة العوائق",
        "custom": {"kind": "letter", "direction": "incoming", "doc_date": "2025-01-15", "sender": "مدار", "recipient": "المقاول",
                   "their_ref": "MD-AAU-L-01", **custom}})
    assert r.status_code == 201, r.text
    return r.json()


def test_archive_both_parties_file(client, site):
    pid = site["pid"]
    # the contractor files a letter it received; it is dated by the letter itself
    d = _doc(client, site, site["hqa"])
    assert d["number"].endswith("001") and "DOC" in d["number"]
    r = act(client, site["hqa"], d["id"], "file").json()
    assert r["state"]["code"] == "filed" and r["submitted_at"][:10] == "2025-01-15" and r["due_at"] is None
    # nobody is asked to answer it
    assert not any(i["id"] == d["id"] for i in client.get("/api/v1/inbox", headers=site["hk"]).json())
    # the consultant files its own minutes; both see both
    m = _doc(client, site, site["hk"], kind="minutes", direction="internal", doc_date="2025-02-01")
    act(client, site["hk"], m["id"], "file")
    rows = client.get(f"/api/v1/projects/{pid}/records?type=document", headers=site["hc"]).json()
    assert {x["custom"]["kind"] for x in rows} == {"letter", "minutes"} and rows[0]["custom"]["sender"]
    assert len(client.get(f"/api/v1/projects/{pid}/records?type=document", headers=site["hk"]).json()) == 2
    # each party edits its own only; a filed one is reopened to be corrected
    assert act(client, site["hk"], d["id"], "reopen").status_code == 403
    assert act(client, site["hqa"], d["id"], "reopen").json()["state"]["code"] == "draft"
    bad = client.post(f"/api/v1/projects/{pid}/records", headers=site["hqa"], json={
        "record_type": "document", "title": "x", "custom": {"kind": "poem"}})
    assert bad.status_code == 422
