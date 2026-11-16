"""Notifications, inbox, assignment, organization user suspension, invitation into a project team."""
from tests.test_records import _join_org, act, new_sub, site, submit  # noqa: F401  (site is a fixture)
from tests.test_team import auth, token_of


def notes(client, h):
    return client.get("/api/v1/notifications", headers=h).json()


def inbox(client, h):
    return client.get("/api/v1/inbox", headers=h).json()


def test_submit_notifies_only_the_discipline(client, site):
    rec = submit(client, site, new_sub(client, site))
    civil, elec, pm = notes(client, site["hce"]), notes(client, site["hee"]), notes(client, site["hk"])
    assert civil["unread"] == 1 and rec["number"] in civil["items"][0]["title_ar"]
    assert elec["unread"] == 0
    assert pm["unread"] == 1  # the consultant PM covers every discipline
    assert notes(client, site["hqa"])["unread"] == 0  # the actor is not told about his own action

    act(client, site["hce"], rec["id"], "revise", comment="ملاحظات")
    qa = notes(client, site["hqa"])
    assert qa["unread"] == 1 and qa["items"][0]["event"] == "revise"
    client.post("/api/v1/notifications/read", headers=site["hqa"], json={"all": True})
    assert notes(client, site["hqa"])["unread"] == 0


def test_inbox_reasons(client, site):
    draft = new_sub(client, site)
    sent = submit(client, site, new_sub(client, site))
    assert {(i["number"], i["reason"]) for i in inbox(client, site["hqa"])} == {(draft["number"], "draft")}
    assert [i["reason"] for i in inbox(client, site["hce"]) if i["id"] == sent["id"]] == ["reply"]
    assert all(i["id"] != sent["id"] for i in inbox(client, site["hee"]))  # other discipline
    act(client, site["hce"], sent["id"], "reject", comment="غير مطابق")
    assert any(i["id"] == sent["id"] and i["reason"] == "returned" for i in inbox(client, site["hqa"]))
    assert all(i["id"] != sent["id"] for i in inbox(client, site["hce"]))


def test_assignment(client, site):
    korg = client.get("/api/v1/auth/me", headers=site["hk"]).json()["orgs"][0]["org"]["id"]
    team = client.get(f"/api/v1/projects/{site['pid']}/team", headers=site["hk"]).json()
    consultant = next(p for p in team["parties"] if p["kind"] == "consultant")
    roles = {x["code"]: x["id"] for x in client.get("/api/v1/roles", headers=site["hk"]).json()}
    kdisc = {d["code"]: d["id"] for d in client.get(f"/api/v1/orgs/{korg}/disciplines", headers=site["hk"]).json()}
    h2, u2 = _join_org(client, site["hk"], korg, "civilB")
    client.post(f"/api/v1/projects/{site['pid']}/members", headers=site["hk"], json={
        "party_id": consultant["id"], "user_id": u2, "role_id": roles["consultant_engineer"], "discipline_ids": [kdisc["C"]]})

    rec = submit(client, site, new_sub(client, site))
    d = client.get(f"/api/v1/records/{rec['id']}", headers=site["hk"]).json()
    assert d["can_assign"] and {u["id"] for u in d["assign_candidates"]} == {site["ce"], u2}
    assert client.get(f"/api/v1/records/{rec['id']}", headers=site["hce"]).json()["can_assign"] is False
    r = client.post(f"/api/v1/records/{rec['id']}/assign", headers=site["hk"], json={"user_id": u2})
    assert r.status_code == 200 and r.json()["assigned_to"]["id"] == u2
    assert any(i["id"] == rec["id"] and i["assigned_to_me"] for i in inbox(client, h2))
    assert all(i["id"] != rec["id"] for i in inbox(client, site["hce"]))  # off his list, still visible
    assert client.get(f"/api/v1/records/{rec['id']}", headers=site["hce"]).status_code == 200
    assert notes(client, h2)["items"][0]["event"] == "assign"
    # not an engineer of this discipline
    ee = client.get("/api/v1/auth/me", headers=site["hee"]).json()["user"]["id"]
    assert client.post(f"/api/v1/records/{rec['id']}/assign", headers=site["hk"], json={"user_id": ee}).status_code == 422


def test_no_engineer_warning(client, site):
    m = client.post(f"/api/v1/projects/{site['pid']}/records", headers=site["hc"], json={
        "title": "مضخات", "discipline_id": site["cdisc"]["M"]}).json()
    c = new_sub(client, site)
    assert m["no_discipline_engineer"] is True and c["no_discipline_engineer"] is False


def test_suspend_and_reactivate_org_user(client, site):
    corg = client.get("/api/v1/auth/me", headers=site["hc"]).json()["orgs"][0]["org"]["id"]
    members = client.get(f"/api/v1/orgs/{corg}/members", headers=site["hc"]).json()
    qa = next(m for m in members if m["user"]["full_name_en"] == "qa")
    assert qa["projects"][0]["code"] == site["code"] and qa["projects"][0]["role"]["code"] == "qa_engineer"

    r = client.patch(f"/api/v1/orgs/{corg}/members/{qa['user']['id']}", headers=site["hc"], json={"is_active": False})
    assert r.status_code == 200
    assert client.get("/api/v1/projects", headers=site["hqa"]).status_code == 401  # even with a valid access token
    assert client.post("/api/v1/auth/login", json={"email": qa["user"]["email"],
                                                   "password": "a-strong-password"}).status_code == 403
    me = client.get("/api/v1/auth/me", headers=site["hc"]).json()["user"]["id"]
    assert client.patch(f"/api/v1/orgs/{corg}/members/{me}", headers=site["hc"], json={"is_active": False}).status_code == 409

    client.patch(f"/api/v1/orgs/{corg}/members/{qa['user']['id']}", headers=site["hc"], json={"is_active": True})
    r = client.post("/api/v1/auth/login", json={"email": qa["user"]["email"], "password": "a-strong-password"})
    assert r.status_code == 200
    # back in the organization, but project access is given again from the project team
    assert client.get("/api/v1/projects", headers=auth(r)).json() == []


def test_invite_new_colleague_from_project_team(client, site):
    korg = client.get("/api/v1/auth/me", headers=site["hk"]).json()["orgs"][0]["org"]["id"]
    team = client.get(f"/api/v1/projects/{site['pid']}/team", headers=site["hk"]).json()
    consultant = next(p for p in team["parties"] if p["kind"] == "consultant")
    roles = {x["code"]: x["id"] for x in client.get("/api/v1/roles", headers=site["hk"]).json()}
    kdisc = {d["code"]: d["id"] for d in client.get(f"/api/v1/orgs/{korg}/disciplines", headers=site["hk"]).json()}
    r = client.post(f"/api/v1/projects/{site['pid']}/parties/{consultant['id']}/invite-member", headers=site["hk"],
                    json={"email": "mech@office.example.com", "role_id": roles["consultant_engineer"],
                          "discipline_ids": [kdisc["M"]]})
    assert r.status_code == 201, r.text
    info = client.get(f"/api/v1/invitations/{token_of(r.json()['link'])}").json()
    assert info["project"]["id"] == site["pid"]
    acc = client.post(f"/api/v1/invitations/{token_of(r.json()['link'])}/accept", json={
        "full_name_ar": "مهندس ميكانيك", "full_name_en": "Mech", "password": "a-strong-password"})
    assert acc.status_code == 200, acc.text
    items = client.get("/api/v1/projects", headers=auth(acc)).json()
    assert items[0]["project"]["id"] == site["pid"] and items[0]["my_role"]["code"] == "consultant_engineer"
    # the contractor cannot invite people into the consultant's organization
    assert client.post(f"/api/v1/projects/{site['pid']}/parties/{consultant['id']}/invite-member", headers=site["hc"],
                       json={"email": "x@y.example.com", "role_id": roles["consultant_engineer"]}).status_code == 403


def test_notification_channels_and_mahami_payload(client, site, monkeypatch):
    s = client.get(f"/api/v1/projects/{site['pid']}/settings", headers=site["hc"]).json()
    assert s["notify"] == {"email": False, "mahami": False} and s["mahami_available"] is False
    r = client.put(f"/api/v1/projects/{site['pid']}/settings", headers=site["hc"],
                   json={"notify": {"email": False, "mahami": True}})
    assert r.json()["notify"]["mahami"] is True

    sent = []
    import app.core.notify as notify
    monkeypatch.setattr(notify, "mahami_enabled", lambda: True)
    monkeypatch.setattr(notify, "_post_mahami", lambda payload: sent.append(payload))
    rec = submit(client, site, new_sub(client, site))
    ce_email = client.get("/api/v1/auth/me", headers=site["hce"]).json()["user"]["email"]
    assert len(sent) == 1 and ce_email in sent[0]["emails"] and sent[0]["url"].endswith(f"/records/{rec['id']}")
