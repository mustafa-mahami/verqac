from tests.test_records import act, site  # noqa: F401


def _new(client, s, h, type_, **kw):
    r = client.post(f"/api/v1/projects/{s['pid']}/records", headers=h, json={
        "record_type": type_, "title": kw.pop("title", "x"), "discipline_id": kw.pop("discipline_id", s["cdisc"]["C"]), **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_rfi(client, site):
    rfi = _new(client, site, site["hqa"], "rfi", title="منسوب البلاطة في المحور 3", description="هل المنسوب +3.20 أم +3.25؟",
               custom={"proposed": "اعتماد +3.20 حسب المخطط الإنشائي", "impact": "none"})
    assert rfi["number"].endswith("-RFI-C-001") and rfi["custom"]["impact"] == "none"
    bad = client.post(f"/api/v1/projects/{site['pid']}/records", headers=site["hqa"], json={
        "record_type": "rfi", "title": "سؤال", "custom": {"severity": "major"}})
    assert bad.json()["detail"] == "invalid_field"
    act(client, site["hqa"], rfi["id"], "submit")
    assert any(i["id"] == rfi["id"] for i in client.get("/api/v1/inbox", headers=site["hce"]).json())
    r = client.post(f"/api/v1/records/{rfi['id']}/transitions", headers=site["hce"], json={"action": "answer"})
    assert r.json()["detail"] == "comment_required"
    r = act(client, site["hce"], rfi["id"], "answer", comment="المنسوب +3.20").json()
    assert r["state"]["code"] == "answered" and r["can_revise"] is False
    assert client.get(f"/api/v1/records/{rfi['id']}/pdf?lang=ar", headers=site["hqa"]).status_code == 200


def test_material_inspection(client, site):
    mir = _new(client, site, site["hqa"], "material", title="توريد حديد 16 مم",
               details={"supplier": "شركة الحديد", "quantity": "12", "unit": "طن"}, custom={"delivery_note": "DN-5531"})
    meta = client.get(f"/api/v1/projects/{site['pid']}/records/meta?type=material", headers=site["hqa"]).json()
    assert meta["reply_hours"] == 24
    act(client, site["hqa"], mir["id"], "submit")
    r = act(client, site["hce"], mir["id"], "reject", comment="شهادة المصنع غير مرفقة").json()
    assert r["performed_at"] and r["resubmit_due_at"] and r["can_revise"] is False  # the contractor revises
    r2 = client.post(f"/api/v1/records/{mir['id']}/revise", headers=site["hqa"]).json()
    assert r2["rev_no"] == 1 and r2["custom"]["delivery_note"] == "DN-5531"


def test_ncr_cycle(client, site):
    # the consultant engineer issues it; the contractor cannot
    assert client.post(f"/api/v1/projects/{site['pid']}/records", headers=site["hqa"], json={
        "record_type": "ncr", "title": "x", "discipline_id": site["cdisc"]["C"]}).status_code == 403
    meta = client.get(f"/api/v1/projects/{site['pid']}/records/meta?type=ncr", headers=site["hce"]).json()
    assert meta["can_create"] is True
    kdisc = meta["disciplines"][0]["id"]
    ncr = _new(client, site, site["hce"], "ncr", title="تعشيش في عمود C3", discipline_id=kdisc,
               custom={"severity": "major", "required_action": "إزالة الأجزاء المعششة وترميمها بمونة إيبوكسي"})
    act(client, site["hce"], ncr["id"], "issue")
    # the contractor's QA engineer has it in his inbox and proposes the corrective action
    assert any(i["id"] == ncr["id"] and i["reason"] == "reply" for i in client.get("/api/v1/inbox", headers=site["hqa"]).json())
    r = act(client, site["hqa"], ncr["id"], "propose_action", comment="تكسير وترميم بمونة إيبوكسي يوم الأحد").json()
    assert r["state"]["category"] == "responded"
    # the consultant engineer verifies: reopen (needs a reason) then close
    assert any(i["id"] == ncr["id"] and i["reason"] == "verify" for i in client.get("/api/v1/inbox", headers=site["hce"]).json())
    assert {t["action"] for t in r["transitions"]} == set()  # nothing for the contractor now
    r = act(client, site["hce"], ncr["id"], "reopen", comment="الترميم غير مكتمل").json()
    assert r["state"]["code"] == "open" and r["due_at"]
    act(client, site["hqa"], ncr["id"], "propose_action", comment="أُكمل الترميم")
    r = act(client, site["hce"], ncr["id"], "close").json()
    assert r["state"]["code"] == "closed"
    pdf = client.get(f"/api/v1/records/{ncr['id']}/pdf?lang=ar", headers=site["hqa"])
    assert pdf.status_code == 200
