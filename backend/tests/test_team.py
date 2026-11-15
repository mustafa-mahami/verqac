"""Phase 1: parties, invitations and project team."""
import itertools

from tests.conftest import register

_n = itertools.count()


def project(client, headers, org_id, **extra):
    code = f"T{next(_n)}"
    r = client.post("/api/v1/projects", json={"org_id": org_id, "code": code, "name_ar": "مشروع",
                                              "name_en": "Project", **extra}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["project"]["id"]


def token_of(link: str) -> str:
    return link.rsplit("/", 1)[-1]


def auth(r):
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def accept_new(client, link, email_name, org=("مكتب الاستشارات", "Consult Office")):
    return client.post(f"/api/v1/invitations/{token_of(link)}/accept", json={
        "full_name_ar": "مهندس", "full_name_en": f"Eng {email_name}", "password": "a-strong-password",
        "org_name_ar": org[0], "org_name_en": org[1]})


def test_add_consultant_to_existing_project_and_accept(client):
    h, org, _ = register(client, name="Contr")
    pid = project(client, h, org)
    r = client.post(f"/api/v1/projects/{pid}/parties", headers=h,
                    json={"kind": "consultant", "placeholder_name": "مكتب الاستشارات", "email": "pm@consult.example.com"})
    assert r.status_code == 201, r.text
    invite = r.json()
    assert invite["email_sent"] is False and "/invite/" in invite["link"]

    # second consultant party is refused
    assert client.post(f"/api/v1/projects/{pid}/parties", headers=h,
                       json={"kind": "consultant", "placeholder_name": "x y"}).status_code == 409

    info = client.get(f"/api/v1/invitations/{token_of(invite['link'])}").json()
    assert info["status"] == "valid" and info["party_kind"] == "consultant" and info["user_exists"] is False
    assert info["role"]["code"] == "consultant_pm"

    r = accept_new(client, invite["link"], "pm")
    assert r.status_code == 200, r.text
    hc = auth(r)

    # the consultant PM now sees the project, as consultant_pm, with an active consultant party
    items = client.get("/api/v1/projects", headers=hc).json()
    assert [i["project"]["id"] for i in items] == [pid]
    assert items[0]["my_role"]["code"] == "consultant_pm"
    team = client.get(f"/api/v1/projects/{pid}/team", headers=hc).json()
    consultant = next(p for p in team["parties"] if p["kind"] == "consultant")
    assert consultant["status"] == "active" and consultant["org"]["name_en"] == "Consult Office"
    assert consultant["can_manage_team"] is True and team["can_manage_project"] is False

    # the link cannot be used twice
    assert accept_new(client, invite["link"], "pm2").status_code == 410


def test_consultant_cannot_manage_parties_or_contractor_team(client):
    h, org, _ = register(client, name="Contr")
    pid = project(client, h, org, consultant_name="Office")
    team = client.get(f"/api/v1/projects/{pid}/team", headers=h).json()
    cparty = next(p for p in team["parties"] if p["kind"] == "consultant")
    contractor = next(p for p in team["parties"] if p["kind"] == "contractor")
    link = client.post(f"/api/v1/projects/{pid}/parties/{cparty['id']}/invite", headers=h,
                       json={"email": "c1@office.example.com"}).json()["link"]
    hc = auth(accept_new(client, link, "c1"))

    assert client.post(f"/api/v1/projects/{pid}/parties", headers=hc,
                       json={"kind": "owner", "placeholder_name": "Owner"}).status_code == 403
    me = client.get("/api/v1/auth/me", headers=hc).json()["user"]["id"]
    role = next(r for r in client.get("/api/v1/roles", headers=hc).json() if r["code"] == "qa_engineer")
    assert client.post(f"/api/v1/projects/{pid}/members", headers=hc, json={
        "party_id": contractor["id"], "user_id": me, "role_id": role["id"]}).status_code == 403


def test_org_member_invite_then_added_to_project_with_disciplines(client):
    h, org, _ = register(client, name="Contr")
    pid = project(client, h, org)
    inv = client.post(f"/api/v1/orgs/{org}/invitations", headers=h, json={"email": "qa@contr.example.com"})
    assert inv.status_code == 201, inv.text
    assert [i["email"] for i in client.get(f"/api/v1/orgs/{org}/invitations", headers=h).json()] == \
        ["qa@contr.example.com"]
    r = client.post(f"/api/v1/invitations/{token_of(inv.json()['link'])}/accept", json={
        "full_name_ar": "مهندس جودة", "full_name_en": "QA Eng", "password": "a-strong-password"})
    assert r.status_code == 200, r.text
    hq = auth(r)
    assert client.get("/api/v1/projects", headers=hq).json() == []  # org member, not yet in the project

    members = client.get(f"/api/v1/orgs/{org}/members", headers=h).json()
    qa = next(m for m in members if m["user"]["email"] == "qa@contr.example.com")
    assert qa["org_role"] == "member"
    team = client.get(f"/api/v1/projects/{pid}/team", headers=h).json()
    contractor = next(p for p in team["parties"] if p["kind"] == "contractor")
    roles = {r["code"]: r for r in client.get("/api/v1/roles", headers=h).json()}
    discs = {d["code"]: d["id"] for d in client.get(f"/api/v1/orgs/{org}/disciplines", headers=h).json()}

    # a consultant role cannot be given to a contractor person
    assert client.post(f"/api/v1/projects/{pid}/members", headers=h, json={
        "party_id": contractor["id"], "user_id": qa["user"]["id"],
        "role_id": roles["consultant_engineer"]["id"]}).status_code == 422
    r = client.post(f"/api/v1/projects/{pid}/members", headers=h, json={
        "party_id": contractor["id"], "user_id": qa["user"]["id"], "role_id": roles["qa_engineer"]["id"],
        "discipline_ids": [discs["C"], discs["A"]]})
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert client.get("/api/v1/projects", headers=hq).json()[0]["my_role"]["code"] == "qa_engineer"

    # deactivate: the project disappears for that user (RLS follows is_active)
    assert client.patch(f"/api/v1/projects/{pid}/members/{mid}", headers=h,
                        json={"is_active": False}).status_code == 200
    assert client.get("/api/v1/projects", headers=hq).json() == []
    # cannot deactivate yourself
    me = next(m for m in client.get(f"/api/v1/projects/{pid}/team", headers=h).json()["members"]
              if m["role"]["code"] == "contractor_pm")
    assert client.patch(f"/api/v1/projects/{pid}/members/{me['id']}", headers=h,
                        json={"is_active": False}).status_code == 409


def test_invite_for_registered_email_requires_that_login(client):
    h, org, _ = register(client, name="Contr")
    hc2, _, consultant_email = register(client, kind="consultant", name="Cons")
    pid = project(client, h, org, consultant_name="Cons")
    team = client.get(f"/api/v1/projects/{pid}/team", headers=h).json()
    cparty = next(p for p in team["parties"] if p["kind"] == "consultant")
    link = client.post(f"/api/v1/projects/{pid}/parties/{cparty['id']}/invite", headers=h,
                       json={"email": consultant_email}).json()["link"]
    tok = token_of(link)

    assert client.get(f"/api/v1/invitations/{tok}").json()["user_exists"] is True
    assert accept_new(client, link, "x").status_code == 409            # must sign in instead
    h_other, _, _ = register(client, name="Other")
    assert client.post(f"/api/v1/invitations/{tok}/accept", headers=h_other, json={}).status_code == 403

    my_orgs = client.get(f"/api/v1/invitations/{tok}/my-orgs", headers=hc2).json()
    assert len(my_orgs) == 1 and my_orgs[0]["kind"] == "consultant"
    r = client.post(f"/api/v1/invitations/{tok}/accept", headers=hc2, json={"org_id": my_orgs[0]["id"]})
    assert r.status_code == 200, r.text
    team = client.get(f"/api/v1/projects/{pid}/team", headers=h).json()
    assert next(p for p in team["parties"] if p["kind"] == "consultant")["org"]["id"] == my_orgs[0]["id"]


def test_removed_party_invitation_stops_working(client):
    h, org, _ = register(client, name="Contr")
    pid = project(client, h, org)
    link = client.post(f"/api/v1/projects/{pid}/parties", headers=h, json={
        "kind": "owner", "placeholder_name": "البلدية", "email": "o@city.example.com"}).json()["link"]
    team = client.get(f"/api/v1/projects/{pid}/team", headers=h).json()
    owner = next(p for p in team["parties"] if p["kind"] == "owner")
    assert owner["pending_invite"]["email"] == "o@city.example.com"
    assert client.delete(f"/api/v1/projects/{pid}/parties/{owner['id']}", headers=h).status_code == 204
    assert client.get(f"/api/v1/invitations/{token_of(link)}").json()["status"] == "expired"
    assert accept_new(client, link, "o", org=("البلدية", "City")).status_code == 410
