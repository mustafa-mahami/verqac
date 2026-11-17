import app.api.lab as lab_api
from tests.test_records import act, attach, site  # noqa: F401


def _test(client, s, **kw):
    r = client.post(f"/api/v1/projects/{s['pid']}/records", headers=s["hqa"], json={
        "record_type": "test", "title": kw.pop("title", "مكعبات سقف الطابق الأول"), "discipline_id": s["cdisc"]["C"], **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _cubes(fck, values):
    return [{"sample": f"{i + 1}-1", "parameter": "Compressive strength 28-day", "unit": "MPa", "age": 28,
             "value": v, "min": fck, "role": "strength28"} for i, v in enumerate(values)]


def test_templates_classes_and_concrete_result(client, site):
    pid, hc = site["pid"], site["hc"]
    tpls = client.get(f"/api/v1/projects/{pid}/lab-templates", headers=site["hqa"]).json()
    codes = {t["code"]: t for t in tpls}
    assert {"concrete_cubes", "steel_s500", "base_course", "tiles_bia", "asphalt_marshall", "blocks"} <= set(codes)
    # the project's concrete classes: B300 for slabs, B450 for columns
    cls = client.put(f"/api/v1/projects/{pid}/concrete-classes", headers=hc, json=[
        {"grade": "B300", "name": "Slabs", "fck": 30, "individual_margin": 4},
        {"grade": "B450", "name": "Columns", "fck": 45, "aliases": "C35/45", "mean_margin": 2}]).json()
    assert [c["grade"] for c in cls] == ["B300", "B450"]
    assert client.put(f"/api/v1/projects/{pid}/concrete-classes", headers=site["hqa"], json=[]).status_code == 403
    t = _test(client, site)
    lab = client.put(f"/api/v1/records/{t['id']}/lab", headers=site["hqa"], json={
        "template_id": codes["concrete_cubes"]["id"], "material": "CON", "acceptance": "concrete",
        "class_id": cls[0]["id"], "lines": _cubes(0, [32, 29, 35])}).json()
    assert lab["result"] == "pass" and lab["fck"] == 30 and lab["lines"][0]["min"] == 30  # class sets fck and minimums
    assert lab["strength_avg"] == 32.0 and lab["below"] == 1
    lab = client.put(f"/api/v1/records/{t['id']}/lab", headers=site["hqa"], json={
        **{k: lab[k] for k in ("template_id", "material", "acceptance", "class_id")}, "lines": _cubes(30, [32, 25, 35])}).json()
    assert lab["result"] == "fail" and "25.0 < 26.0" in lab["note"]
    rows = client.get(f"/api/v1/projects/{pid}/records?type=test", headers=site["hqa"]).json()
    assert rows[0]["lab_result"] == "fail"
    # the specification changes: the class re-judges its tests
    cls[0]["individual_margin"] = 6
    client.put(f"/api/v1/projects/{pid}/concrete-classes", headers=hc, json=cls)
    assert client.get(f"/api/v1/records/{t['id']}/lab", headers=site["hqa"]).json()["result"] == "pass"
    cls[0]["individual_margin"] = 4
    client.put(f"/api/v1/projects/{pid}/concrete-classes", headers=hc, json=cls)
    # submit, the consultant records a decision and asks for a retest
    act(client, site["hqa"], t["id"], "submit")
    assert client.put(f"/api/v1/records/{t['id']}/lab", headers=site["hqa"], json={"lines": []}).status_code == 403
    d = client.put(f"/api/v1/records/{t['id']}/lab/decision", headers=site["hce"], json={"decision": "core", "note": "كور من العمود"}).json()
    assert d["decision"] == "core"
    assert client.put(f"/api/v1/records/{t['id']}/lab/decision", headers=site["hqa"], json={"decision": "accepted"}).status_code == 403
    act(client, site["hce"], t["id"], "retest", comment="أعيدوا الفحص")
    r1 = client.post(f"/api/v1/records/{t['id']}/revise", headers=site["hqa"]).json()
    lab1 = client.get(f"/api/v1/records/{r1['id']}/lab", headers=site["hqa"]).json()
    assert len(lab1["lines"]) == 3 and lab1["lines"][0]["value"] is None and lab1["fck"] == 30
    assert act(client, site["hqa"], r1["id"], "submit").json()["detail"] == "lab_results_required"
    pdf = client.get(f"/api/v1/records/{t['id']}/pdf?lang=ar", headers=site["hqa"])
    assert pdf.status_code == 200


def test_steel_all_rule_and_ai_reading(client, site, monkeypatch):
    pid = site["pid"]
    client.put(f"/api/v1/projects/{pid}/concrete-classes", headers=site["hc"], json=[{"grade": "B450", "fck": 45, "aliases": "C35/45"}])
    t = _test(client, site, title="حديد Ø16")
    assert attach(client, site["hqa"], t["id"], name="cert.pdf").status_code == 201
    file_id = client.get(f"/api/v1/records/{t['id']}", headers=site["hqa"]).json()["attachments"][0]["file_id"]
    assert client.post(f"/api/v1/records/{t['id']}/lab/ai-read", headers=site["hqa"],
                       json={"file_id": file_id}).json()["detail"] == "ai_not_configured"
    monkeypatch.setattr(lab_api, "ai_enabled", lambda: True)
    seen = {}

    def fake_call(pdf, prompt):
        seen["pdf"], seen["prompt"] = pdf[:8], prompt
        return {"header": {"lab_report_no": "CC-24-020288", "grade": "C35/45", "report_date": "2024-12-10",
                           "lab_conclusion": "PASS"},
                "lines": [{"sample": "1-1", "parameter": "Compressive strength 28-day", "age_days": 28, "value": 47.5},
                          {"sample": "2-1", "parameter": "Compressive strength 28-day", "age_days": 28, "value": 39.0, "legible": False},
                          {"sample": "1-1", "parameter": "Compressive strength 7-day", "age_days": 7, "value": 33.1}],
                "remarks": None}, "test-model"
    monkeypatch.setattr(lab_api, "ai_call", fake_call)
    r = client.post(f"/api/v1/records/{t['id']}/lab/ai-read", headers=site["hqa"], json={"file_id": file_id}).json()
    assert r["ai_state"] == "reading"
    lab = client.get(f"/api/v1/records/{t['id']}/lab", headers=site["hqa"]).json()  # the job ran after the response
    assert lab["ai_state"] == "ready" and seen["pdf"].startswith(b"%PDF")
    d = lab["ai_draft"]
    assert d["acceptance"] == "concrete" and d["class_match"] == "grade" and d["fck"] == 45 and d["grade"] == "B450"
    s28 = [x for x in d["lines"] if x["role"] == "strength28"]
    assert [x["min"] for x in s28] == [45, 45] and s28[1]["legible"] is False
    # the user reviews and applies
    body = {k: d[k] for k in ("acceptance", "lab_report_no", "report_date", "grade", "fck", "lab_conclusion")}
    lab = client.put(f"/api/v1/records/{t['id']}/lab", headers=site["hqa"], json={
        **body, "class_id": d["class_id"], "lines": d["lines"], "ai_applied": True}).json()
    assert lab["ai_draft"] is None and lab["result"] == "fail" and lab["conflict"] is True  # lab said PASS


def test_project_types_toggle(client, site):
    url = f"/api/v1/projects/{site['pid']}/settings"
    s = client.get(url, headers=site["hc"]).json()
    assert "test" in s["types"]
    s = client.put(url, headers=site["hc"], json={"types": ["submittal", "inspection", "test"]}).json()
    assert set(s["types"]) == {"inspection", "submittal", "test"}
    meta = client.get(f"/api/v1/projects/{site['pid']}/records/meta?type=rfi", headers=site["hqa"]).json()
    assert meta["enabled"] is False and meta["can_create"] is False
    assert client.put(url, headers=site["hc"], json={"types": []}).status_code == 422
