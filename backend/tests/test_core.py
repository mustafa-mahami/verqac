import os
import uuid

from sqlalchemy import create_engine, text

from tests.conftest import register


def new_project(client, headers, org_id, code="P1", **extra):
    body = {"org_id": org_id, "code": code, "name_ar": "مشروع", "name_en": "Project", **extra}
    return client.post("/api/v1/projects", json=body, headers=headers)


def test_register_and_me(client):
    headers, org_id, email = register(client)
    me = client.get("/api/v1/auth/me", headers=headers).json()
    assert me["user"]["email"] == email
    assert me["orgs"][0]["org_role"] == "admin"
    discs = client.get(f"/api/v1/orgs/{org_id}/disciplines", headers=headers).json()
    assert [d["code"] for d in discs] == ["C", "A", "E", "M", "P", "G"]


def test_duplicate_email_rejected(client):
    _, _, email = register(client)
    r = client.post("/api/v1/auth/register-org", json={
        "org_kind": "contractor", "org_name_ar": "جهة", "org_name_en": "Dup", "full_name_ar": "مستخدم",
        "full_name_en": "U2", "email": email.upper(), "password": "a-strong-password"})
    assert r.status_code == 409


def test_login_refresh_logout(client):
    _, _, email = register(client)
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": email, "password": "a-strong-password"})
    assert r.status_code == 200
    r2 = client.post("/api/v1/auth/refresh")
    assert r2.status_code == 200 and r2.json()["access_token"]
    assert client.post("/api/v1/auth/logout").status_code == 204
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_reused_refresh_token_revokes_all_sessions(client):
    _, _, email = register(client)
    client.post("/api/v1/auth/login", json={"email": email, "password": "a-strong-password"})
    stolen = client.cookies.get("verqac_refresh")
    assert client.post("/api/v1/auth/refresh").status_code == 200   # rotates, `stolen` is now revoked
    current = client.cookies.get("verqac_refresh")
    # within the grace window (reload, second tab) the old token still works once more
    client.cookies.clear()
    client.cookies.set("verqac_refresh", stolen, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 200
    # after the window it is treated as stolen
    owner = create_engine(os.environ["VERQAC_MIGRATION_DATABASE_URL"])
    with owner.begin() as conn:
        conn.execute(text("UPDATE refresh_tokens SET rotated_at = rotated_at - interval '10 minutes' "
                          "WHERE rotated_at IS NOT NULL"))
    owner.dispose()
    client.cookies.clear()
    client.cookies.set("verqac_refresh", stolen, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401   # reuse detected
    client.cookies.clear()
    client.cookies.set("verqac_refresh", current, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh").status_code == 401   # every session revoked


def test_create_project_with_parties(client):
    headers, org_id, _ = register(client)
    r = new_project(client, headers, org_id, consultant_name="مكتب الاستشارات", owner_name="البلدية",
                    donor_name="جهة مانحة")
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["my_role"]["code"] == "contractor_pm"
    kinds = {p["kind"]: p for p in item["parties"]}
    assert kinds["contractor"]["status"] == "active"
    assert kinds["consultant"]["placeholder_name"] == "مكتب الاستشارات"
    assert kinds["owner"]["status"] == "invited"
    assert new_project(client, headers, org_id, code="p1").status_code == 409  # code unique, any case


def test_owner_org_cannot_create_projects(client):
    headers, org_id, _ = register(client, kind="owner", name="Owner")
    assert new_project(client, headers, org_id).status_code == 403


def test_other_org_cannot_see_project(client):
    """Tenant isolation through the API (design doc section 7: leak tests on every deploy)."""
    h1, org1, _ = register(client, name="Alpha")
    h2, org2, _ = register(client, name="Beta")
    pid = new_project(client, h1, org1, code="ALPHA1").json()["project"]["id"]

    assert client.get(f"/api/v1/projects/{pid}", headers=h2).status_code == 404
    assert all(i["project"]["id"] != pid for i in client.get("/api/v1/projects", headers=h2).json())
    # cannot create a project inside someone else's organization
    assert new_project(client, h2, org1, code="X1").status_code == 403
    assert client.get(f"/api/v1/projects/{pid}", headers=h1).status_code == 200


def test_rls_blocks_raw_sql(client):
    """Even a query with no WHERE clause returns only the user's rows: RLS in the database itself."""
    h1, org1, _ = register(client, name="Gamma")
    h2, _, _ = register(client, name="Delta")
    new_project(client, h1, org1, code="G1")
    uid2 = client.get("/api/v1/auth/me", headers=h2).json()["user"]["id"]

    app_engine = create_engine(os.environ["VERQAC_DATABASE_URL"])
    with app_engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.user_id', :u, true), set_config('app.bypass', 'off', true)"),
                     {"u": uid2})
        projects = conn.execute(text("SELECT code FROM projects")).scalars().all()
        orgs = conn.execute(text("SELECT id FROM organizations")).scalars().all()
        users = conn.execute(text("SELECT email FROM users")).scalars().all()
    with app_engine.begin() as conn:  # no user at all: nothing
        assert conn.execute(text("SELECT count(*) FROM projects")).scalar() == 0
    app_engine.dispose()
    assert "G1" not in projects
    assert len(orgs) == 1 and len(users) == 1


def test_audit_log_is_append_only(client):
    h1, org1, _ = register(client, name="Audit")
    new_project(client, h1, org1, code="AU1")
    app_engine = create_engine(os.environ["VERQAC_DATABASE_URL"])
    with app_engine.connect() as conn:
        for sql in ("UPDATE audit_log SET action = 'x'", "DELETE FROM audit_log"):
            try:
                conn.execute(text(sql))
                raise AssertionError(f"allowed: {sql}")
            except Exception as e:  # noqa: BLE001
                assert "permission denied" in str(e)
                conn.rollback()
    app_engine.dispose()


def test_unauthenticated_and_bad_token(client):
    assert client.get("/api/v1/projects").status_code == 401
    bad = {"Authorization": f"Bearer {uuid.uuid4()}"}
    assert client.get("/api/v1/projects", headers=bad).status_code == 401


def test_failed_login_is_audited(client):
    _, _, email = register(client, name="Fail")
    client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
    owner = create_engine(os.environ["VERQAC_MIGRATION_DATABASE_URL"])
    with owner.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM audit_log WHERE action = 'login_failed' "
                              "AND changes->>'email' = :e"), {"e": email}).scalar()
    owner.dispose()
    assert n == 1
