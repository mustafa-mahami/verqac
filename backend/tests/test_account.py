from tests.test_records import site  # noqa: F401
from tests.test_team import token_of


def test_account_update_and_password_change(client, site):
    h = site["hqa"]
    me = client.get("/api/v1/auth/me", headers=h).json()["user"]
    r = client.patch("/api/v1/auth/me", headers=h, json={"full_name_ar": "سعد علوش", "full_name_en": "Saad Alloush", "locale": "en"})
    assert r.status_code == 200 and r.json()["full_name_en"] == "Saad Alloush" and r.json()["locale"] == "en"
    assert client.post("/api/v1/auth/password", headers=h,
                       json={"current_password": "wrong-one-123", "new_password": "a-new-password-1"}).json()["detail"] == "wrong_password"
    assert client.post("/api/v1/auth/password", headers=h,
                       json={"current_password": "a-strong-password", "new_password": "a-new-password-1"}).status_code == 204
    assert client.post("/api/v1/auth/login", json={"email": me["email"], "password": "a-strong-password"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": me["email"], "password": "a-new-password-1"}).status_code == 200


def test_admin_reset_link(client, site):
    hc, hqa = site["hc"], site["hqa"]
    org = client.get("/api/v1/auth/me", headers=hc).json()["orgs"][0]["org"]["id"]
    qa = client.get("/api/v1/auth/me", headers=hqa).json()["user"]
    # not an admin: refused; another organization's user: refused
    assert client.post(f"/api/v1/orgs/{org}/members/{site['ce']}/reset-link", headers=hc).status_code == 403
    assert client.post(f"/api/v1/orgs/{org}/members/{qa['id']}/reset-link", headers=hqa).status_code == 403
    r = client.post(f"/api/v1/orgs/{org}/members/{qa['id']}/reset-link", headers=hc)
    assert r.status_code == 200 and r.json()["emailed"] is False
    token = token_of(r.json()["link"])
    assert client.get(f"/api/v1/auth/reset/{token}").json()["email"] == qa["email"]
    assert client.post(f"/api/v1/auth/reset/{token}", json={"password": "short"}).status_code == 422
    assert client.post(f"/api/v1/auth/reset/{token}", json={"password": "reset-password-9"}).status_code == 204
    # used once only; the new password works
    assert client.post(f"/api/v1/auth/reset/{token}", json={"password": "reset-password-8"}).status_code == 410
    assert client.post("/api/v1/auth/login", json={"email": qa["email"], "password": "reset-password-9"}).status_code == 200
    # a new link makes the previous unused one stop working
    t1 = token_of(client.post(f"/api/v1/orgs/{org}/members/{qa['id']}/reset-link", headers=hc).json()["link"])
    t2 = token_of(client.post(f"/api/v1/orgs/{org}/members/{qa['id']}/reset-link", headers=hc).json()["link"])
    assert client.get(f"/api/v1/auth/reset/{t1}").status_code == 410 and client.get(f"/api/v1/auth/reset/{t2}").status_code == 200


def test_forgot_does_not_reveal_accounts(client):
    a = client.post("/api/v1/auth/forgot", json={"email": "nobody@nowhere.example.com"})
    assert a.status_code == 202 and a.json() == {"mail_enabled": False}
