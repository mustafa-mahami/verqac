from tests.test_records import new_sub, site  # noqa: F401


def _roles(client, s, h):
    return {r["code"]: r for r in client.get(f"/api/v1/projects/{s['pid']}/roles", headers=h).json()}


def _qa_member(client, s):
    team = client.get(f"/api/v1/projects/{s['pid']}/team", headers=s["hc"]).json()
    return next(m for m in team["members"] if m["role"]["code"] == "qa_engineer")


def test_project_roles(client, site):
    s, base = site, f"/api/v1/projects/{site['pid']}/roles"
    roles = _roles(client, s, s["hc"])
    assert roles["site_engineer"]["can_edit"] and not roles["consultant_engineer"]["can_edit"]
    # the contractor names a surveyor with the site engineer's permissions
    r = client.post(base, headers=s["hc"], json={"name_ar": "مساح", "name_en": "Surveyor",
                                                 "base_role_id": roles["site_engineer"]["id"]})
    assert r.status_code == 201, r.text
    surveyor = r.json()
    assert surveyor["custom"] and surveyor["base_code"] == "site_engineer" and surveyor["party_kind"] == "contractor"
    # never the consultant's powers: a contractor role cannot be based on a consultant role, and the other way
    assert client.post(base, headers=s["hc"], json={"name_ar": "x", "name_en": "x",
                       "base_role_id": roles["consultant_engineer"]["id"]}).status_code == 403
    assert client.post(base, headers=s["hk"], json={"name_ar": "x", "name_en": "x",
                       "base_role_id": roles["site_engineer"]["id"]}).status_code == 403
    # the consultant does not edit the contractor's roles, but sees them
    assert client.patch(f"{base}/{surveyor['id']}", headers=s["hk"], json={"name_ar": "y"}).status_code == 403
    assert _roles(client, s, s["hk"])[surveyor["code"]]["name_ar"] == "مساح"
    # give it to the QA engineer: he now has the site engineer's permissions (no submittals)
    m = _qa_member(client, s)
    r = client.patch(f"/api/v1/projects/{s['pid']}/members/{m['id']}", headers=s["hc"], json={"role_id": surveyor["id"]})
    assert r.status_code == 200 and r.json()["role"]["name_ar"] == "مساح" and r.json()["role"]["base_code"] == "site_engineer"
    r = client.post(f"/api/v1/projects/{s['pid']}/records", headers=s["hqa"], json={
        "title": "x", "discipline_id": s["cdisc"]["C"], "details": {"manufacturer": "x"}})
    assert r.status_code == 403
    # in use: cannot be deleted
    assert client.delete(f"{base}/{surveyor['id']}", headers=s["hc"]).status_code == 409
    # rename a platform role for this project only, and hide one
    r = client.patch(f"{base}/{roles['qa_engineer']['id']}", headers=s["hc"], json={"name_ar": "مراقب الجودة"})
    assert r.status_code == 200 and r.json()["name_ar"] == "مراقب الجودة"
    assert client.get(f"/api/v1/projects/{s['pid']}/team", headers=s["hk"]).status_code == 200
    r = client.patch(f"{base}/{roles['document_controller']['id']}", headers=s["hc"], json={"hidden": True})
    assert r.json()["hidden"] is True
    r = client.patch(f"/api/v1/projects/{s['pid']}/members/{m['id']}", headers=s["hc"],
                     json={"role_id": roles["document_controller"]["id"]})
    assert r.status_code == 422 and r.json()["detail"] == "role_hidden"
    # platform roles are hidden, never deleted; a free project role is deleted
    assert client.delete(f"{base}/{roles['qa_engineer']['id']}", headers=s["hc"]).status_code == 409
    client.patch(f"/api/v1/projects/{s['pid']}/members/{m['id']}", headers=s["hc"], json={"role_id": roles["qa_engineer"]["id"]})
    assert client.delete(f"{base}/{surveyor['id']}", headers=s["hc"]).status_code == 204
    assert surveyor["code"] not in _roles(client, s, s["hc"])
    # the rename shows on the member
    assert _qa_member(client, s)["role"]["name_ar"] == "مراقب الجودة"
