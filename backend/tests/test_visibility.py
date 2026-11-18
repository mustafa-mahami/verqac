from tests.test_records import act, attach, new_sub, site  # noqa: F401


def _ids(client, s, h):
    return {r["id"] for r in client.get(f"/api/v1/projects/{s['pid']}/records?type=submittal", headers=h).json()}


def test_contractor_staff_see_their_disciplines(client, site):
    s = site
    elec = new_sub(client, s, h=s["hc"], disc="E", title="لوحات كهرباء")  # by the contractor PM
    assert attach(client, s["hc"], elec["id"]).status_code == 201
    assert act(client, s["hc"], elec["id"], "submit").status_code == 200
    civil = new_sub(client, s, title="حديد")  # by the civil QA engineer
    # default: a civil engineer of the contractor does not see an electrical submittal of his company
    assert elec["id"] not in _ids(client, s, s["hqa"])
    assert client.get(f"/api/v1/records/{elec['id']}", headers=s["hqa"]).status_code == 404
    assert civil["id"] in _ids(client, s, s["hqa"])  # his own discipline (and his own draft)
    assert {elec["id"], civil["id"]} <= _ids(client, s, s["hc"])  # the manager sees all
    # the consultant electrical engineer sees it, the civil one does not
    assert elec["id"] in _ids(client, s, s["hee"]) and elec["id"] not in _ids(client, s, s["hce"])
    # the project opens it: staff see every request of their company
    r = client.put(f"/api/v1/projects/{s['pid']}/settings", headers=s["hc"], json={"party_sees_all": True})
    assert r.status_code == 200 and r.json()["party_sees_all"] is True
    assert elec["id"] in _ids(client, s, s["hqa"])
    assert client.get(f"/api/v1/records/{elec['id']}", headers=s["hqa"]).status_code == 200
    # still discipline based for the other party
    assert elec["id"] not in _ids(client, s, s["hce"])

