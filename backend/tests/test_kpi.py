from tests.test_records import act, new_sub, site, submit  # noqa: F401 (fixture)


def _k(d, code):
    return next((x for x in d["kpis"] if x["code"] == code), None)


def test_kpi_scorecard_and_targets(client, site):
    pid = site["pid"]
    a = submit(client, site, new_sub(client, site))
    assert act(client, site["hce"], a["id"], "approve").status_code == 200
    b = submit(client, site, new_sub(client, site))
    assert act(client, site["hce"], b["id"], "reject", comment="غير مطابق").status_code == 200
    r1 = client.post(f"/api/v1/records/{b['id']}/revise", headers=site["hqa"]).json()
    submit(client, site, r1)
    submit(client, site, new_sub(client, site))  # waiting for an answer
    d = client.get(f"/api/v1/projects/{pid}/kpi", headers=site["hc"]).json()
    assert d["submittal"]["unique"] == 3 and d["submittal"]["records"] == 4
    assert _k(d, "SUB_FIRST_PASS")["value"] == 50.0  # 1 of the 2 answered R0
    assert _k(d, "SUB_RESUB_INDEX")["value"] == 0.33
    assert _k(d, "SUB_APPROVAL_PROGRESS")["value"] == 33.3 and _k(d, "SUB_APPROVAL_PROGRESS")["status"] is None
    assert _k(d, "SUB_FIRST_PASS")["status"] == "red"  # below 60
    assert _k(d, "IR_FIRST_PASS")["value"] is None  # no inspections: no figures
    assert d["submittal"]["by_discipline"][0]["unique"] == 3
    # the consultant sees the same scorecard
    assert client.get(f"/api/v1/projects/{pid}/kpi", headers=site["hk"]).json()["submittal"]["unique"] == 3
    # discipline and dates narrow it
    assert client.get(f"/api/v1/projects/{pid}/kpi?discipline=E", headers=site["hc"]).json()["submittal"]["unique"] == 0
    assert client.get(f"/api/v1/projects/{pid}/kpi?from=2000-01-01&to=2000-01-02", headers=site["hc"]).json()["submittal"]["unique"] == 0
    # targets: the project's own
    s = client.get(f"/api/v1/projects/{pid}/kpi-settings", headers=site["hc"]).json()
    assert s["targets"]["SUB_FIRST_PASS"]["green"] == 75 and len(s["defs"]) == len(s["targets"])
    t = s["targets"]
    t["SUB_FIRST_PASS"] = {"green": 50, "amber": 40, "qmp_ref": "6.14", "active": True}
    t["NCR_REPEAT"]["active"] = False
    r = client.put(f"/api/v1/projects/{pid}/kpi-settings", headers=site["hc"], json={"targets": t, "ncr_close_days": 10})
    assert r.status_code == 200, r.text
    d = client.get(f"/api/v1/projects/{pid}/kpi", headers=site["hc"]).json()
    assert _k(d, "SUB_FIRST_PASS")["status"] == "green" and _k(d, "NCR_REPEAT") is None and d["ncr_close_days"] == 10
    bad = {**t, "SUB_FIRST_PASS": {"green": 50, "amber": 60, "qmp_ref": None, "active": True}}  # amber above green
    assert client.put(f"/api/v1/projects/{pid}/kpi-settings", headers=site["hc"], json={"targets": bad}).status_code == 422
    assert client.put(f"/api/v1/projects/{pid}/kpi-settings", headers=site["hce"], json={"targets": t}).status_code == 403


def test_kpi_exports(client, site):
    pid = site["pid"]
    a = submit(client, site, new_sub(client, site))
    act(client, site["hce"], a["id"], "approve")
    r = client.get(f"/api/v1/projects/{pid}/kpi/xlsx?lang=ar&discipline=C", headers=site["hk"])
    assert r.status_code == 200 and r.content[:2] == b"PK"
    import io

    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r.content))
    assert len(wb.sheetnames) == 3 and wb.worksheets[0].sheet_view.rightToLeft
    codes = [row[8] for row in wb.worksheets[0].iter_rows(values_only=True) if row and len(row) > 8]
    assert "SUB_FIRST_PASS" in codes
    assert client.get(f"/api/v1/projects/{pid}/kpi/doc", headers=site["hc"]).status_code == 404
