from datetime import date, timedelta

from tests.test_records import act, site  # noqa: F401


def _structure(client, s):
    types = client.get(f"/api/v1/projects/{s['pid']}/structure", headers=s["hc"]).json()["types"]
    bt = next(t for t in types if t["name_en"] == "Buildings")
    return client.post(f"/api/v1/projects/{s['pid']}/apply-type", headers=s["hc"], json={"project_type_id": bt["id"]}).json()


def test_daily_cycle_and_progress(client, site):
    pid = site["pid"]
    st = _structure(client, site)
    structure, block = st["stages"][0], st["stages"][1]  # Structure 20 %, Block walls 8 %
    floors = st["locations"][0]["units"]  # 6 floors of building 1
    # settings: names for supervision, counts for the rest
    s = client.put(f"/api/v1/projects/{pid}/daily-settings", headers=site["hc"], json={
        "crew": {"supervision": "names", "contractor": "counts", "labour": "counts"}, "link_materials": True,
        "lists": {"labour_desc": [{"ar": "حداد", "en": "Steel fixer"}, {"ar": "نجار", "en": ""}, {"ar": " ", "en": ""}],
                  "supervision_names": [{"ar": "م. سامي داود", "en": "Eng. Sami Dawood", "role_ar": "مهندس مدني", "role_en": "Civil engineer"}],
                  "equipment": [{"ar": "رافعة برجية", "en": "Tower crane"}]}}).json()
    assert [(x["ar"], x["en"]) for x in s["lists"]["labour_desc"]] == [("حداد", "Steel fixer"), ("نجار", "نجار")]
    assert s["lists"]["supervision_names"][0]["role_en"] == "Civil engineer"
    d1 = date.today() - timedelta(days=2)
    client.put(f"/api/v1/projects/{pid}/settings", headers=site["hc"],
               json={"calendar": {"weekend": None, "holidays": [{"from": d1.isoformat(), "name": "عيد"}], "work_start": "07:00", "work_end": "15:00"},
                     "dates": {"start_date": (d1 - timedelta(days=9)).isoformat(), "end_date": None}})
    rid = client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"], json={"report_date": d1.isoformat()}).json()["id"]
    assert client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"],
                       json={"report_date": d1.isoformat()}).json()["detail"] == "dr_exists"
    future = (date.today() + timedelta(days=1)).isoformat()
    assert client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"], json={"report_date": future}).status_code == 422
    assert client.get(f"/api/v1/records/{rid}/daily", headers=site["hqa"]).json()["hours_from"] == "07:00"
    body = {"weather": "sunny", "temp_min": 12, "temp_max": 21, "hours_from": "07:00", "hours_to": "15:00",
            "crew": [{"group": "labour", "name": "حداد", "count": 12, "hours": 8}, {"group": "labour", "name": "نجار", "count": 6}],
            "equipment": [{"name": "رافعة برجية", "count": 1, "hours": 8}],
            "works": [{"stage_id": structure["id"], "location_ids": [floors[1]["id"]], "description": "صب سقف الطابق الأرضي",
                       "qty": 45, "unit": "m3", "progress": 100},
                      {"stage_id": structure["id"], "location_ids": [floors[2]["id"]], "description": "حديد سقف الطابق الأول", "progress": 40},
                      {"stage_id": block["id"], "all_locations": True, "description": "بدء البلوك", "progress": 10}],
            "planned": [{"stage_id": structure["id"], "location_ids": [floors[2]["id"]], "description": "استكمال حديد الطابق الأول"}],
            "delays": [{"cause": "materials", "hours": 2, "description": "تأخر وصول الحديد"}]}
    d = client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json=body).json()
    assert d["hours_from"] == "07:00" and d["hours_to"] == "15:00"  # from the project's working hours
    assert d["weekday"] == (d1.weekday() + 1) % 7 and d["day_no"] == 10 and d["day_off"] == "holiday" and d["holiday"] == "عيد"
    assert d["totals"]["labour"] == 18 and d["totals"]["equipment"] == 1 and d["can_edit"] is True
    # nothing counts before supervision approves
    act(client, site["hqa"], rid, "submit")
    assert client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()["project"] == 0
    # supervision returns it for correction: editable again, in the contractor's inbox as "returned"
    r = act(client, site["hce"], rid, "return", comment="نسبة الحديد مبالغ فيها").json()
    assert r["state"]["code"] == "returned"
    assert any(i["id"] == rid and i["reason"] == "returned" for i in client.get("/api/v1/inbox", headers=site["hqa"]).json())
    body["works"][1]["progress"] = 30
    client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json=body)
    act(client, site["hqa"], rid, "submit")
    assert act(client, site["hce"], rid, "approve").json()["state"]["code"] == "approved"
    p = client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()
    # Structure: (100 + 30) / 6 floors = 21.7 % of 20 ; Block: 10 % of 8 ; total weights 100
    assert p["stages"][structure["id"]] == 21.7 and p["stages"][block["id"]] == 10.0
    assert p["project"] == round(20 * 130 / 6 / 100 + 8 * 10 / 100, 1)
    assert p["snapshots"][0]["day"] == d1.isoformat() and p["as_of"] == d1.isoformat()
    # the next day starts from yesterday: crew and equipment copied, the plan becomes the work list
    rid2 = client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"],
                       json={"report_date": (d1 + timedelta(days=1)).isoformat()}).json()["id"]
    d2 = client.get(f"/api/v1/records/{rid2}/daily", headers=site["hqa"]).json()
    assert d2["totals"]["labour"] == 18 and d2["works"][0]["description"] == "استكمال حديد الطابق الأول"
    assert d2["current"][f"{structure['id']}:{floors[2]['id']}"] == 30
    # an older report approved later does not overwrite a newer %
    assert client.get(f"/api/v1/records/{rid}/pdf?lang=ar", headers=site["hqa"]).status_code == 200
    assert client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json=body).status_code == 403


def test_labour_from_work_lines(client, site):
    """The team and its workers on each work line: the day's labour is worked out from them, plus what is
    entered by hand (guards, cleaners...); worked-out lines sent back are ignored (they are worked out again)."""
    pid = site["pid"]
    day = date.today() - timedelta(days=3)
    rid = client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"], json={"report_date": day.isoformat()}).json()["id"]
    body = {"crew": [{"group": "labour", "name": "حارس", "count": 1, "hours": 12},
                     {"group": "labour", "name": "قديم", "count": 50, "auto": True}],
            "works": [{"description": "قصارة الطابق 8", "crew": 6, "team": "فريق هلال", "sub": "عارف شهاب", "hours": 8},
                      {"description": "قصارة الطابق 9", "crew": 4, "team": "فريق هلال", "sub": "عارف شهاب", "hours": 6},
                      {"description": "بلاط", "crew": 3, "team": "بلّيط"},
                      {"description": "تنظيف", "crew": 2}]}
    d = client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json=body).json()
    lab = sorted((x["name"], x.get("sub"), x["count"], x.get("hours"), x.get("auto")) for x in d["crew"] if x["group"] == "labour")
    assert lab == [("بلّيط", None, 3, None, True), ("حارس", None, 1, 12.0, False), ("فريق هلال", "عارف شهاب", 10, 8.0, True)]
    assert d["totals"]["labour"] == 14 and d["works"][0]["team"] == "فريق هلال"


def test_default_lists(client, site):
    """A new project starts with the usual positions, trades and equipment in both languages; an existing one can
    add them, and a name entered twice (another case or spacing) is kept once."""
    pid = site["pid"]
    s = client.get(f"/api/v1/projects/{pid}/daily-settings", headers=site["hc"]).json()
    trades = s["lists"]["labour_desc"]
    assert any(x["ar"] == "قصّارون" and x["en"] == "Plaster Masons" for x in trades)
    assert s["lists"]["supervision_desc"] and s["lists"]["contractor_desc"] and s["lists"]["equipment"]
    # an imported list: English only, with duplicates
    s["lists"] = {"labour_desc": [{"ar": "Plaster Masons", "en": "Plaster Masons"}, {"ar": "Excavation team", "en": "Excavation team"},
                                  {"ar": "Excavation Team", "en": "Excavation Team"}, {"ar": "Hitachi", "en": "Hitachi"}]}
    r = client.put(f"/api/v1/projects/{pid}/daily-settings", headers=site["hc"], json=s).json()
    assert [x["en"] for x in r["lists"]["labour_desc"]] == ["Plaster Masons", "Excavation team", "Hitachi"]
    r = client.post(f"/api/v1/projects/{pid}/daily-settings/defaults", headers=site["hc"]).json()
    assert r["translated"] >= 2 and r["added"] > 20
    lab = r["settings"]["lists"]["labour_desc"]
    assert next(x for x in lab if x["en"] == "Plaster Masons")["ar"] == "قصّارون"
    assert len([x for x in lab if x["en"].lower() == "excavation team"]) == 1 and any(x["en"] == "Hitachi" for x in lab)
    again = client.post(f"/api/v1/projects/{pid}/daily-settings/defaults", headers=site["hc"]).json()
    assert again["added"] == 0 and again["translated"] == 0
    assert client.post(f"/api/v1/projects/{pid}/daily-settings/defaults", headers=site["hce"]).status_code == 403
