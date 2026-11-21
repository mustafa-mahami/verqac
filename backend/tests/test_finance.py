from datetime import date, timedelta

from tests.test_records import act, site  # noqa: F401 (fixture)


def _app(client, s, claimed="100000", **kw):
    r = client.post(f"/api/v1/projects/{s['pid']}/records", headers=s["hc"], json={
        "record_type": "payment", "title": "الدفعة الأولى",
        "custom": {"period_from": "2026-01-01", "period_to": "2026-01-31", "claimed": claimed}, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_payments_certification_and_cashflow(client, site):
    pid = site["pid"]
    # money is for the project managers and the owner: not the QA engineer nor the consultant's engineers
    assert client.get(f"/api/v1/projects/{pid}/finance", headers=site["hqa"]).status_code == 404
    assert client.get(f"/api/v1/projects/{pid}/finance", headers=site["hce"]).status_code == 404
    assert client.post(f"/api/v1/projects/{pid}/records", headers=site["hqa"],
                       json={"record_type": "payment", "title": "x"}).status_code == 403
    f = client.put(f"/api/v1/projects/{pid}/finance/settings", headers=site["hc"], json={"contract_value": 1000000, "currency": "ils"})
    assert f.status_code == 200 and f.json()["currency"] == "ILS"
    # the contractor claims, the consultant certifies (with retention) and the amount to pay
    ipc = _app(client, site)
    assert ipc["number"].endswith("IPC-001") or "IPC" in ipc["number"]
    assert act(client, site["hc"], ipc["id"], "submit").status_code == 200
    # the contractor cannot write the certified amounts, nor certify
    assert client.put(f"/api/v1/records/{ipc['id']}/certification", headers=site["hc"], json={"certified": "1"}).status_code == 403
    assert act(client, site["hk"], ipc["id"], "certify").json()["detail"] == "payment_amounts_required"
    r = client.put(f"/api/v1/records/{ipc['id']}/certification", headers=site["hk"], json={"certified": "95,000", "payable": "85500"})
    assert r.status_code == 200 and r.json()["custom"]["certified"] == "95000"
    assert client.put(f"/api/v1/records/{ipc['id']}/certification", headers=site["hk"], json={"certified": "abc"}).status_code == 422
    assert client.put(f"/api/v1/records/{ipc['id']}/certification", headers=site["hk"],
                      json={"certified": "95000", "payable": "96000"}).json()["detail"] == "payable_exceeds_certified"
    # certified on paper earlier: its real date
    old = (date.today() - timedelta(days=200)).isoformat()
    r = act(client, site["hk"], ipc["id"], "certify", answered_on=old).json()
    assert r["state"]["code"] == "certified" and r["answered_at"][:10] == old
    # what was paid: the advance and the certified application
    today = date.today()
    client.post(f"/api/v1/projects/{pid}/finance/receipts", headers=site["hc"],
                json={"day": (today - timedelta(days=60)).isoformat(), "amount": 100000, "kind": "advance"})
    # the money is received by the contractor: supervision sees it, does not record it
    body = {"day": today.isoformat(), "amount": 50000, "kind": "payment", "record_id": ipc["id"]}
    assert client.post(f"/api/v1/projects/{pid}/finance/receipts", headers=site["hk"], json=body).json()["detail"] == "cannot_record_payment"
    assert client.get(f"/api/v1/projects/{pid}/finance", headers=site["hk"]).json()["can_pay"] is False
    f = client.post(f"/api/v1/projects/{pid}/finance/receipts", headers=site["hc"], json=body).json()
    app = next(x for x in f["applications"] if x["id"] == ipc["id"])
    assert app["paid"] == 50000 and app["remaining"] == 35500
    assert client.post(f"/api/v1/projects/{pid}/finance/receipts", headers=site["hc"], json={
        "day": today.isoformat(), "amount": 40000, "kind": "payment", "record_id": ipc["id"]}).json()["detail"] == "payment_exceeds_payable"
    t = f["totals"]
    assert t["certified"] == 95000 and t["payable"] == 85500 and t["paid"] == 150000 and t["advance"] == 100000
    assert t["unpaid"] == 35500
    assert [p["value"] for p in f["paid"]] == [100000, 150000] and f["certified"][-1]["value"] == 95000 and f["payable"][-1]["value"] == 85500
    assert client.post(f"/api/v1/projects/{pid}/finance/receipts", headers=site["hc"],
                       json={"day": (today + timedelta(days=2)).isoformat(), "amount": 1}).status_code == 422
    # a receipt entered by mistake is cancelled with a reason: it stays listed, and counts for nothing
    rid = next(x["id"] for x in f["receipts"] if x["kind"] == "payment")
    url = f"/api/v1/projects/{pid}/finance/receipts/{rid}/void"
    assert client.post(url, headers=site["hc"], json={"reason": ""}).status_code == 422
    v = client.post(url, headers=site["hc"], json={"reason": "مبلغ خاطئ"}).json()
    gone = next(x for x in v["receipts"] if x["id"] == rid)
    assert len(v["receipts"]) == 2 and gone["void_reason"] == "مبلغ خاطئ" and gone["void_at"] and gone["void_by"]
    assert next(x for x in v["applications"] if x["id"] == ipc["id"])["remaining"] == 85500 and v["totals"]["paid"] == 100000
    assert client.post(url, headers=site["hc"], json={"reason": "مرة أخرى"}).status_code == 409
    # the consultant PM reads it too
    assert client.get(f"/api/v1/projects/{pid}/finance", headers=site["hk"]).status_code == 200
    # a returned application is claimed again as a revision, without the earlier certified amounts
    ipc2 = _app(client, site, claimed="200000")
    act(client, site["hc"], ipc2["id"], "submit")
    client.put(f"/api/v1/records/{ipc2['id']}/certification", headers=site["hk"], json={"certified": "10"})
    assert act(client, site["hk"], ipc2["id"], "return", comment="الكميات زائدة").status_code == 200
    r1 = client.post(f"/api/v1/records/{ipc2['id']}/revise", headers=site["hc"]).json()
    assert "certified" not in r1["custom"] and r1["custom"]["claimed"] == "200000"


def test_org_admin_sees_money_whatever_the_project_role(client, site):
    """The contractor's organization admin, on the project as QA engineer, still sees and records payments."""
    from app.core.db import session_scope
    from app.models.core import OrgMember, ProjectMember, Role
    from sqlalchemy import select
    pid = site["pid"]
    me = client.get("/api/v1/auth/me", headers=site["hc"]).json()["user"]["id"]
    with session_scope(bypass=True) as db:
        qa = db.scalar(select(Role).where(Role.org_id.is_(None), Role.code == "qa_engineer"))
        m = db.scalar(select(ProjectMember).where(ProjectMember.project_id == pid, ProjectMember.user_id == me))
        m.role_id = qa.id
        assert db.scalar(select(OrgMember.org_role).where(OrgMember.user_id == me)) == "admin"
    assert client.get(f"/api/v1/projects/{pid}/finance", headers=site["hc"]).status_code == 200
    r = client.post(f"/api/v1/projects/{pid}/records", headers=site["hc"],
                    json={"record_type": "payment", "title": "دفعة", "custom": {"claimed": "10"}})
    assert r.status_code == 201, r.text
    # an ordinary QA engineer still does not
    assert client.get(f"/api/v1/projects/{pid}/finance", headers=site["hqa"]).status_code == 404
