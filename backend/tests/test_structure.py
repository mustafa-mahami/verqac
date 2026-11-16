from tests.test_records import act, new_sub, site  # noqa: F401


def test_project_types_seeded_and_editable(client, site):
    hc = site["hc"]
    org = client.get("/api/v1/auth/me", headers=hc).json()["orgs"][0]["org"]["id"]
    types = client.get(f"/api/v1/orgs/{org}/project-types", headers=hc).json()
    b = next(t for t in types if t["name_en"] == "Buildings")
    assert len(b["stages"]) == 17 and sum(float(s["weight"]) for s in b["stages"]) == 100 and b["unit_label_ar"] == "طابق"
    b["stages"][0]["weight"] = 30  # total 110
    assert client.put(f"/api/v1/orgs/{org}/project-types", headers=hc, json=types).json()["detail"] == "weights_must_total_100"
    b["stages"][0]["weight"] = 20
    types.append({"name_ar": "جسور", "name_en": "Bridges", "group_label_ar": "جسر", "group_label_en": "Bridge",
                  "unit_label_ar": "بحر", "unit_label_en": "Span", "stages": [], "units": []})
    r = client.put(f"/api/v1/orgs/{org}/project-types", headers=hc, json=types)
    assert r.status_code == 200 and r.json()[-1]["name_en"] == "Bridges"
    # a non-admin cannot change them
    assert client.put(f"/api/v1/orgs/{org}/project-types", headers=site["hqa"], json=types).status_code == 403


def _structure(client, site, h=None):
    return client.get(f"/api/v1/projects/{site['pid']}/structure", headers=h or site["hc"]).json()


def test_apply_type_stages_locations_and_records(client, site):
    pid, hc = site["pid"], site["hc"]
    st = _structure(client, site)
    assert st["stages"] == [] and st["can_edit"] and any(t["name_en"] == "Buildings" for t in st["types"])
    btype = next(t for t in st["types"] if t["name_en"] == "Buildings")
    st = client.post(f"/api/v1/projects/{pid}/apply-type", headers=hc, json={"project_type_id": btype["id"]}).json()
    assert len(st["stages"]) == 17 and st["labels"]["unit_ar"] == "طابق" and st["project_type"]["name_en"] == "Buildings"
    assert len(st["locations"]) == 1 and len(st["locations"][0]["units"]) == 6
    # the consultant reads it but cannot edit
    k = _structure(client, site, site["hk"])
    assert k["can_edit"] is False and len(k["stages"]) == 17
    assert client.put(f"/api/v1/projects/{pid}/stages", headers=site["hk"], json=k["stages"]).status_code == 403

    # a second building
    locs = st["locations"]
    locs.append({"name_ar": "مبنى 2", "name_en": "Building 2",
                 "units": [{"name_ar": "الأرضي", "name_en": "Ground"}, {"name_ar": "الأول", "name_en": "First"}]})
    st = client.put(f"/api/v1/projects/{pid}/locations", headers=hc, json=locs).json()
    b1, b2 = st["locations"]
    tiles = next(s for s in st["stages"] if s["name_en"] == "Tiles")
    elevator = next(s for s in st["stages"] if s["name_en"] == "Elevator")

    # a submittal for tiles on two floors of building 1 and the whole building 2
    f3, roof = b1["units"][4]["id"], b1["units"][5]["id"]
    rec = new_sub(client, site, stage_id=tiles["id"], location_ids=[f3, roof, b2["id"]])
    assert rec["stage"]["name_en"] == "Tiles" and rec["all_locations"] is False
    assert [x["name_ar"] for x in rec["locations"]] == ["مبنى 1 – الطابق الثالث", "مبنى 1 – السطح", "مبنى 2"]
    row = next(x for x in client.get(f"/api/v1/projects/{pid}/records", headers=hc).json() if x["id"] == rec["id"])
    assert row["stage_id"] == tiles["id"] and len(row["location_ids"]) == 3
    # a whole-project stage covers every location
    rec2 = new_sub(client, site, stage_id=elevator["id"], location_ids=[f3])
    assert rec2["all_locations"] is True and rec2["locations"] == []
    # another project's location is refused
    bad = client.post(f"/api/v1/projects/{pid}/records", headers=site["hqa"], json={
        "title": "xyz", "discipline_id": site["cdisc"]["C"], "location_ids": ["00000000-0000-0000-0000-000000000000"]})
    assert bad.json()["detail"] == "invalid_location"
    # edit the draft: whole project
    r = client.patch(f"/api/v1/records/{rec['id']}", headers=site["hqa"],
                     json={"stage_id": tiles["id"], "all_locations": True, "location_ids": []})
    assert r.json()["all_locations"] is True
    client.patch(f"/api/v1/records/{rec['id']}", headers=site["hqa"],
                 json={"stage_id": tiles["id"], "all_locations": False, "location_ids": [f3]})

    # used stages / locations can be switched off but not deleted
    st = _structure(client, site)
    assert next(s for s in st["stages"] if s["id"] == tiles["id"])["used"] is True
    without = [s for s in st["stages"] if s["id"] != tiles["id"]]
    assert client.put(f"/api/v1/projects/{pid}/stages", headers=hc, json=without).status_code in (409, 422)
    b1 = st["locations"][0]
    b1["units"] = [u for u in b1["units"] if u["id"] != f3]
    assert client.put(f"/api/v1/projects/{pid}/locations", headers=hc, json=st["locations"]).json()["detail"] == "location_in_use"

    # submitting and answering keeps stage + locations, and the stamp still verifies
    act(client, site["hqa"], rec["id"], "submit")
    stamp = act(client, site["hce"], rec["id"], "approve").json()["events"][-1]["stamp"]
    assert client.get(f"/api/v1/verify/{stamp}").json()["intact"] is True
    pdf = client.get(f"/api/v1/records/{rec['id']}/pdf?lang=ar", headers=site["hqa"])
    assert pdf.status_code == 200
    r1 = client.post(f"/api/v1/records/{rec2['id']}/revise", headers=site["hqa"])
    assert r1.status_code == 403  # rec2 is a draft; revisions start from an answered record


def test_new_project_with_type(client, site):
    hc = site["hc"]
    org = client.get("/api/v1/auth/me", headers=hc).json()["orgs"][0]["org"]["id"]
    roads = next(t for t in client.get(f"/api/v1/orgs/{org}/project-types", headers=hc).json() if t["name_en"] == "Roads")
    p = client.post("/api/v1/projects", headers=hc, json={"org_id": org, "code": "RD1", "name_ar": "طريق", "name_en": "Road",
                                                            "project_type_id": roads["id"]}).json()["project"]["id"]
    st = client.get(f"/api/v1/projects/{p}/structure", headers=hc).json()
    assert len(st["stages"]) == 7 and st["labels"]["unit_en"] == "Section" and len(st["locations"][0]["units"]) == 2
