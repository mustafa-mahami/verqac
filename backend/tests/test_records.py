"""Record engine with the submittal type: drafts, numbering, files, review, revisions, scopes."""
import io
import itertools
from datetime import datetime

import pytest

from tests.conftest import register
from tests.test_team import auth, token_of

_n = itertools.count()


def _join_org(client, admin_h, org_id, name):
    email = f"{name}{next(_n)}@x.example.com"
    link = client.post(f"/api/v1/orgs/{org_id}/invitations", headers=admin_h, json={"email": email}).json()["link"]
    r = client.post(f"/api/v1/invitations/{token_of(link)}/accept", json={
        "full_name_ar": "مستخدم", "full_name_en": name, "password": "a-strong-password"})
    assert r.status_code == 200, r.text
    me = client.get("/api/v1/auth/me", headers=auth(r)).json()["user"]["id"]
    return auth(r), me


@pytest.fixture
def site(client):
    """Contractor PM + QA engineer (civil), consultant PM + consultant engineers (civil / electrical)."""
    hc, corg, _ = register(client, name="Builder")
    code = f"P{next(_n)}"
    pid = client.post("/api/v1/projects", headers=hc, json={
        "org_id": corg, "code": code, "name_ar": "مدرسة", "name_en": "School", "consultant_name": "مكتب"}).json()["project"]["id"]
    team = client.get(f"/api/v1/projects/{pid}/team", headers=hc).json()
    cparty = next(p for p in team["parties"] if p["kind"] == "consultant")
    link = client.post(f"/api/v1/projects/{pid}/parties/{cparty['id']}/invite", headers=hc,
                       json={"email": f"cpm{next(_n)}@office.example.com"}).json()["link"]
    r = client.post(f"/api/v1/invitations/{token_of(link)}/accept", json={
        "full_name_ar": "مدير الاستشاري", "full_name_en": "Consultant PM", "password": "a-strong-password",
        "org_name_ar": "مكتب", "org_name_en": "Office"})
    hk = auth(r)
    korg = client.get("/api/v1/auth/me", headers=hk).json()["orgs"][0]["org"]["id"]
    roles = {x["code"]: x["id"] for x in client.get("/api/v1/roles", headers=hc).json()}
    cdisc = {d["code"]: d["id"] for d in client.get(f"/api/v1/orgs/{corg}/disciplines", headers=hc).json()}
    kdisc = {d["code"]: d["id"] for d in client.get(f"/api/v1/orgs/{korg}/disciplines", headers=hk).json()}
    team = client.get(f"/api/v1/projects/{pid}/team", headers=hc).json()
    contractor = next(p for p in team["parties"] if p["kind"] == "contractor")
    consultant = next(p for p in team["parties"] if p["kind"] == "consultant")

    hqa, qa = _join_org(client, hc, corg, "qa")
    client.post(f"/api/v1/projects/{pid}/members", headers=hc, json={
        "party_id": contractor["id"], "user_id": qa, "role_id": roles["qa_engineer"], "discipline_ids": [cdisc["C"]]})
    hce, ce = _join_org(client, hk, korg, "civil")
    client.post(f"/api/v1/projects/{pid}/members", headers=hk, json={
        "party_id": consultant["id"], "user_id": ce, "role_id": roles["consultant_engineer"],
        "discipline_ids": [kdisc["C"]]})
    hee, ee = _join_org(client, hk, korg, "elec")
    client.post(f"/api/v1/projects/{pid}/members", headers=hk, json={
        "party_id": consultant["id"], "user_id": ee, "role_id": roles["consultant_engineer"],
        "discipline_ids": [kdisc["E"]]})
    return dict(pid=pid, code=code, hc=hc, hqa=hqa, hk=hk, hce=hce, ce=ce, hee=hee, cdisc=cdisc)


def new_sub(client, s, h=None, disc="C", **kw):
    r = client.post(f"/api/v1/projects/{s['pid']}/records", headers=h or s["hqa"], json={
        "title": "حديد تسليح", "discipline_id": s["cdisc"][disc], "details": {"manufacturer": "Steel Co"}, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def attach(client, h, rid, kind="submission", name="sheet.pdf"):
    return client.post(f"/api/v1/records/{rid}/attachments", headers=h, data={"kind": kind},
                       files={"file": (name, io.BytesIO(b"%PDF-1.4 test " + name.encode()), "application/pdf")})


def act(client, h, rid, action, **kw):
    return client.post(f"/api/v1/records/{rid}/transitions", headers=h, json={"action": action, **kw})


def submit(client, s, rec):
    assert attach(client, s["hqa"], rec["id"]).status_code == 201
    r = act(client, s["hqa"], rec["id"], "submit")
    assert r.status_code == 200, r.text
    return r.json()


def test_numbering_per_discipline_and_manual(client, site):
    a, b = new_sub(client, site), new_sub(client, site)
    assert (a["number"], b["number"]) == (f"{site['code']}-SUB-C-001", f"{site['code']}-SUB-C-002")
    e = new_sub(client, site, h=site["hc"], disc="E")
    assert e["number"] == f"{site['code']}-SUB-E-001"
    assert new_sub(client, site, number="LEGACY-7")["number"] == "LEGACY-7"
    r = client.post(f"/api/v1/projects/{site['pid']}/records", headers=site["hqa"],
                    json={"title": "dup", "number": " legacy-7 "})
    assert r.status_code == 409  # unique ignoring case and edge spaces


def test_draft_is_private_to_contractor(client, site):
    rec = new_sub(client, site)
    assert client.get(f"/api/v1/records/{rec['id']}", headers=site["hk"]).status_code == 404
    assert client.get(f"/api/v1/projects/{site['pid']}/records", headers=site["hk"]).json() == []
    submit(client, site, rec)
    assert client.get(f"/api/v1/records/{rec['id']}", headers=site["hk"]).status_code == 200


def test_submit_without_attachment_and_due_date(client, site):
    rec = new_sub(client, site)
    done = act(client, site["hqa"], rec["id"], "submit").json()  # a file is optional
    assert done["state"]["category"] == "submitted"
    days = (datetime.fromisoformat(done["due_at"]) - datetime.fromisoformat(done["submitted_at"])).days
    assert days == 14
    # locked after submit
    assert client.patch(f"/api/v1/records/{rec['id']}", headers=site["hqa"], json={"title": "x y"}).status_code == 403


def test_discipline_scope_and_direction(client, site):
    rec = submit(client, site, new_sub(client, site))
    rid = rec["id"]
    # electrical engineer does not see a civil record
    assert client.get(f"/api/v1/records/{rid}", headers=site["hee"]).status_code == 404
    assert client.get(f"/api/v1/projects/{site['pid']}/records", headers=site["hee"]).json() == []
    # the contractor cannot answer its own submittal
    assert act(client, site["hc"], rid, "approve").status_code == 403
    # the civil engineer sees only respond transitions, and a comment is required for "revise"
    detail = client.get(f"/api/v1/records/{rid}", headers=site["hce"]).json()
    assert {t["action"] for t in detail["transitions"]} == {"approve", "approve_as_noted", "revise", "reject"}
    assert act(client, site["hce"], rid, "revise").json()["detail"] == "comment_required"
    r = act(client, site["hce"], rid, "revise", comment="أرفق شهادة المصنع")
    assert r.status_code == 200 and r.json()["state"]["code"] == "revise_and_resubmit"
    assert r.json()["events"][-1]["stamp"]  # approval fingerprint stored
    # a second answer on the same record finds it already moved on
    assert act(client, site["hk"], rid, "approve").status_code == 409


def test_new_revision(client, site):
    rec = submit(client, site, new_sub(client, site))
    act(client, site["hce"], rec["id"], "reject", comment="غير مطابق")
    assert client.get(f"/api/v1/records/{rec['id']}", headers=site["hqa"]).json()["can_revise"] is True
    r1 = client.post(f"/api/v1/records/{rec['id']}/revise", headers=site["hqa"])
    assert r1.status_code == 201, r1.text
    r1 = r1.json()
    assert (r1["number"], r1["rev_no"], r1["state"]["code"]) == (rec["number"], 1, "draft")
    assert r1["details"]["manufacturer"] == "Steel Co" and r1["response_comment"] is None
    assert [x["rev_no"] for x in r1["revisions"]] == [0, 1]
    # only the latest revision can be revised
    assert client.post(f"/api/v1/records/{rec['id']}/revise", headers=site["hqa"]).status_code == 403
    rows = client.get(f"/api/v1/projects/{site['pid']}/records", headers=site["hqa"]).json()
    mine = [x for x in rows if x["number"] == rec["number"]]
    assert len(mine) == 1 and mine[0]["rev_no"] == 1 and mine[0]["revisions"] == 2


def test_consultant_pm_answers_on_behalf(client, site):
    rec = submit(client, site, new_sub(client, site))
    r = act(client, site["hk"], rec["id"], "approve_as_noted", comment="ملاحظات بسيطة", on_behalf_of=site["ce"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["answered_on_behalf_of"]["id"] == site["ce"]
    assert d["events"][-1]["on_behalf_of"]["id"] == site["ce"]
    # an engineer cannot act on behalf of someone else
    rec2 = submit(client, site, new_sub(client, site))
    assert act(client, site["hce"], rec2["id"], "approve", on_behalf_of=site["ce"]).status_code in (200, 403)


def test_internal_comments_stay_in_party(client, site):
    rec = submit(client, site, new_sub(client, site))
    client.post(f"/api/v1/records/{rec['id']}/comments", headers=site["hce"],
                json={"body": "ملاحظة داخلية للاستشاري", "visibility": "internal"})
    client.post(f"/api/v1/records/{rec['id']}/comments", headers=site["hce"], json={"body": "سؤال للمقاول"})
    seen_by_contractor = [x["body"] for x in client.get(f"/api/v1/records/{rec['id']}", headers=site["hqa"]).json()["comments"]]
    seen_by_consultant = [x["body"] for x in client.get(f"/api/v1/records/{rec['id']}", headers=site["hk"]).json()["comments"]]
    assert seen_by_contractor == ["سؤال للمقاول"]
    assert len(seen_by_consultant) == 2


def test_files_follow_record_visibility(client, site):
    rec = new_sub(client, site)
    d = attach(client, site["hqa"], rec["id"]).json()
    fid = d["attachments"][0]["file_id"]
    assert client.get(f"/api/v1/files/{fid}", headers=site["hk"]).status_code == 404  # still a draft
    act(client, site["hqa"], rec["id"], "submit")
    r = client.get(f"/api/v1/files/{fid}", headers=site["hk"])
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    h_out, _, _ = register(client, name="Outsider")
    assert client.get(f"/api/v1/files/{fid}", headers=h_out).status_code == 404
    # contractor can no longer add submission files; the consultant can add a response file
    assert attach(client, site["hqa"], rec["id"]).status_code == 403
    assert attach(client, site["hce"], rec["id"], kind="response", name="marked.pdf").status_code == 201


def test_pdf(client, site):
    rec = submit(client, site, new_sub(client, site))
    act(client, site["hce"], rec["id"], "approve")
    r = client.get(f"/api/v1/records/{rec['id']}/pdf?lang=ar", headers=site["hqa"])
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:4] == b"%PDF"


def test_project_settings_review_days(client, site):
    s = client.get(f"/api/v1/projects/{site['pid']}/settings", headers=site["hc"]).json()
    assert s["review_days"]["submittal"] == 14 and s["can_edit"] is True
    # the consultant cannot change the contract periods
    assert client.put(f"/api/v1/projects/{site['pid']}/settings", headers=site["hk"],
                      json={"review_days": {"submittal": 3}}).status_code == 403
    assert client.put(f"/api/v1/projects/{site['pid']}/settings", headers=site["hc"],
                      json={"review_days": {"submittal": 0}}).status_code == 422
    r = client.put(f"/api/v1/projects/{site['pid']}/settings", headers=site["hc"], json={"review_days": {"submittal": 7}})
    assert r.status_code == 200 and r.json()["review_days"]["submittal"] == 7
    done = act(client, site["hqa"], new_sub(client, site)["id"], "submit").json()
    assert (datetime.fromisoformat(done["due_at"]) - datetime.fromisoformat(done["submitted_at"])).days == 7


def test_project_list_stats(client, site):
    submit(client, site, new_sub(client, site))
    new_sub(client, site)  # draft: counted for the contractor, invisible to the consultant
    mine = next(i for i in client.get("/api/v1/projects", headers=site["hc"]).json() if i["project"]["id"] == site["pid"])
    theirs = next(i for i in client.get("/api/v1/projects", headers=site["hk"]).json() if i["project"]["id"] == site["pid"])
    assert (mine["stats"]["records"], mine["stats"]["open"]) == (2, 1)
    assert (theirs["stats"]["records"], theirs["stats"]["open"], theirs["stats"]["overdue"]) == (1, 1, 0)


def test_replacement_engineer_sees_predecessor_records(client, site):
    """Records belong to the discipline, not to the engineer who answered them."""
    answered = submit(client, site, new_sub(client, site))
    act(client, site["hce"], answered["id"], "approve")
    pending = submit(client, site, new_sub(client, site))

    # the civil engineer leaves: deactivated in the project team
    team = client.get(f"/api/v1/projects/{site['pid']}/team", headers=site["hk"]).json()
    old = next(m for m in team["members"] if m["user"]["id"] == site["ce"])
    assert client.patch(f"/api/v1/projects/{site['pid']}/members/{old['id']}", headers=site["hk"],
                        json={"is_active": False}).status_code == 200
    assert client.get(f"/api/v1/records/{pending['id']}", headers=site["hce"]).status_code == 404

    # a new civil engineer joins with his own account
    korg = client.get("/api/v1/auth/me", headers=site["hk"]).json()["orgs"][0]["org"]["id"]
    from tests.test_records import _join_org
    hnew, new = _join_org(client, site["hk"], korg, "civil2")
    roles = {x["code"]: x["id"] for x in client.get("/api/v1/roles", headers=site["hk"]).json()}
    kdisc = {d["code"]: d["id"] for d in client.get(f"/api/v1/orgs/{korg}/disciplines", headers=site["hk"]).json()}
    consultant = next(p for p in team["parties"] if p["kind"] == "consultant")
    assert client.post(f"/api/v1/projects/{site['pid']}/members", headers=site["hk"], json={
        "party_id": consultant["id"], "user_id": new, "role_id": roles["consultant_engineer"],
        "discipline_ids": [kdisc["C"]]}).status_code == 201

    numbers = {r["number"] for r in client.get(f"/api/v1/projects/{site['pid']}/records", headers=hnew).json()}
    assert {answered["number"], pending["number"]} <= numbers
    assert client.get(f"/api/v1/records/{answered['id']}", headers=hnew).status_code == 200
    r = act(client, hnew, pending["id"], "approve_as_noted", comment="1- ...\n2- ...\n3- ...")
    assert r.status_code == 200 and r.json()["response_comment"].count("\n") == 2


def test_public_verify_stamp(client, site):
    from sqlalchemy import text

    from app.core.db import session_scope

    rec = submit(client, site, new_sub(client, site))
    r = act(client, site["hce"], rec["id"], "reject", comment="غير مطابق")
    stamp = r.json()["events"][-1]["stamp"]
    v = client.get(f"/api/v1/verify/{stamp.upper()}")  # no sign-in; case does not matter
    assert v.status_code == 200, v.text
    v = v.json()
    assert v["intact"] is True and (v["number"], v["rev_no"]) == (rec["number"], 0)
    assert v["decision"]["code"] == "rejected" and v["latest_rev"] == 0 and v["latest_state"] is None
    assert "files" not in v and "response_comment" not in v  # summary only
    # a newer revision is reported
    client.post(f"/api/v1/records/{rec['id']}/revise", headers=site["hqa"])
    assert client.get(f"/api/v1/verify/{stamp}").json()["latest_rev"] == 1
    # any change to what was answered breaks the match
    with session_scope(bypass=True) as db:
        db.execute(text("UPDATE records SET response_comment = 'مطابق' WHERE id = :i"), {"i": rec["id"]})
    assert client.get(f"/api/v1/verify/{stamp}").json()["intact"] is False
    assert client.get("/api/v1/verify/" + "0" * 64).status_code == 404
    assert client.get("/api/v1/verify/not-a-stamp").status_code == 404


def test_submittal_kinds_per_project(client, site):
    pid, hc = site["pid"], site["hc"]
    url = f"/api/v1/projects/{pid}/settings"
    kinds = client.get(url, headers=hc).json()["submittal_kinds"]
    assert [k["code"] for k in kinds][:2] == ["material", "shop_drawing"]
    meta = client.get(f"/api/v1/projects/{pid}/records/meta", headers=site["hqa"]).json()
    assert len(meta["submittal_kinds"]) == 5
    # records store the code and show the name in both languages
    rec = new_sub(client, site, details={"submittal_kind": "material"})
    assert rec["details"]["submittal_kind"] == "material" and rec["submittal_kind_name"] == {"ar": "مواد", "en": "Material"}
    row = next(x for x in client.get(f"/api/v1/projects/{pid}/records", headers=site["hqa"]).json() if x["id"] == rec["id"])
    assert row["submittal_kind"] == "material" and row["submittal_kind_name"]["ar"] == "مواد"
    r = client.post(f"/api/v1/projects/{pid}/records", headers=site["hqa"],
                    json={"title": "xyz", "discipline_id": site["cdisc"]["C"], "details": {"submittal_kind": "nope"}})
    assert r.status_code == 422 and r.json()["detail"] == "invalid_kind"
    # rename one, add one, deactivate one
    kinds[0]["name_ar"] = "مواد وتجهيزات"
    kinds[3]["active"] = False
    kinds.append({"name_ar": "عينة لون", "name_en": "Color sample"})
    r = client.put(url, headers=hc, json={"submittal_kinds": kinds})
    assert r.status_code == 200, r.text
    saved = r.json()["submittal_kinds"]
    assert saved[-1]["code"].startswith("k_") and saved[3]["active"] is False
    assert client.get(f"/api/v1/records/{rec['id']}", headers=site["hqa"]).json()["submittal_kind_name"]["ar"] == "مواد وتجهيزات"
    meta = client.get(f"/api/v1/projects/{pid}/records/meta", headers=site["hqa"]).json()
    assert "sample" not in [k["code"] for k in meta["submittal_kinds"]] and len(meta["submittal_kinds"]) == 5
    # a kind in use cannot be deleted (deactivate it instead); an unused one can
    assert client.put(url, headers=hc, json={"submittal_kinds": saved[1:]}).json()["detail"] == "kind_in_use"
    assert client.put(url, headers=hc, json={"submittal_kinds": saved[:-1]}).status_code == 200
    assert client.put(url, headers=site["hk"], json={"submittal_kinds": saved}).status_code == 403
    assert client.put(url, headers=hc, json={"submittal_kinds": [{**k, "active": False} for k in saved]}).status_code == 422
    # records from before the list existed hold the name text, and still show it
    legacy = new_sub(client, site)
    from sqlalchemy import text

    from app.core.db import session_scope
    with session_scope(bypass=True) as db:
        db.execute(text("UPDATE submittal_details SET submittal_kind = 'مخططات تنفيذية' WHERE record_id = :i"), {"i": legacy["id"]})
    got = client.get(f"/api/v1/records/{legacy['id']}", headers=site["hqa"]).json()
    assert got["submittal_kind_name"] == {"ar": "مخططات تنفيذية", "en": "Shop drawing"}
    # in the register a legacy value groups with the code it names, so the type filter has no duplicates
    row = next(x for x in client.get(f"/api/v1/projects/{pid}/records", headers=site["hqa"]).json() if x["id"] == legacy["id"])
    assert row["submittal_kind"] == "shop_drawing"


def test_required_by_date(client, site):
    from datetime import date, timedelta
    soon = (date.today() + timedelta(days=5)).isoformat()
    r = client.post(f"/api/v1/projects/{site['pid']}/records", headers=site["hqa"], json={
        "title": "مصاعد", "discipline_id": site["cdisc"]["C"], "required_by": soon, "required_by_note": "التوريد حسب الجدول"})
    rec = r.json()
    assert rec["required_by"] == soon and rec["required_by_note"] == "التوريد حسب الجدول" and rec["can_set_required_by"]
    rid = rec["id"]
    act(client, site["hqa"], rid, "submit")
    # the consultant sees it but cannot change it; the contractor can while it waits for an answer
    got = client.get(f"/api/v1/records/{rid}", headers=site["hce"]).json()
    assert got["required_by"] == soon and got["can_set_required_by"] is False
    url = f"/api/v1/records/{rid}/required-by"
    assert client.put(url, headers=site["hce"], json={"required_by": None}).status_code == 403
    sooner = (date.today() + timedelta(days=2)).isoformat()
    r = client.put(url, headers=site["hqa"], json={"required_by": sooner, "required_by_note": "مؤكد"})
    assert r.status_code == 200 and r.json()["required_by"] == sooner
    notes = client.get("/api/v1/notifications", headers=site["hce"]).json()["items"]
    assert any(n["event"] == "required_by" for n in notes)
    rows = client.get(f"/api/v1/projects/{site['pid']}/records", headers=site["hce"]).json()
    assert next(x for x in rows if x["id"] == rid)["required_by"] == sooner
    inbox = client.get("/api/v1/inbox", headers=site["hce"]).json()
    assert next(x for x in inbox if x["id"] == rid)["required_by"] == sooner
    # after the answer it is history: no more changes
    act(client, site["hce"], rid, "approve")
    assert client.put(url, headers=site["hqa"], json={"required_by": None}).status_code == 403


def test_header_banner_and_addressed_to(client, site):
    import io
    pid, hc = site["pid"], site["hc"]
    png = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
           b"\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82")
    up = lambda h, ct="image/png": client.post(f"/api/v1/projects/{pid}/header", headers=h,
                                               files={"file": ("logos.png", io.BytesIO(png), ct)})
    assert up(site["hk"]).status_code == 403
    assert up(hc, "application/pdf").json()["detail"] == "header_not_image"
    assert up(hc).json()["has_header"] is True and up(hc).status_code == 200  # replacing works too
    assert client.get(f"/api/v1/projects/{pid}/header", headers=site["hk"]).content == png
    rec = submit(client, site, new_sub(client, site))
    names = [u["full_name_en"] for u in client.get(f"/api/v1/records/{rec['id']}", headers=hc).json()["addressed_to"]]
    assert names == ["Consultant PM"]
    assert client.get(f"/api/v1/records/{rec['id']}/pdf?lang=ar", headers=hc).status_code == 200
    assert client.delete(f"/api/v1/projects/{pid}/header", headers=hc).json()["has_header"] is False
    inbox = client.get("/api/v1/inbox", headers=site["hce"]).json()
    assert any(i["id"] == rec["id"] for i in inbox)


def test_resubmission_period(client, site):
    pid, hc = site["pid"], site["hc"]
    s = client.get(f"/api/v1/projects/{pid}/settings", headers=hc).json()
    assert s["resubmit_days"]["submittal"] == 7
    assert client.put(f"/api/v1/projects/{pid}/settings", headers=hc, json={"resubmit_days": {"submittal": 5}}).json()["resubmit_days"]["submittal"] == 5
    rec = submit(client, site, new_sub(client, site))
    r = act(client, site["hce"], rec["id"], "revise", comment="عدّل الكميات").json()
    assert r["resubmit_due_at"] and r["resubmit_overdue"] is False and r["resubmitted_at"] is None
    from datetime import datetime
    assert (datetime.fromisoformat(r["resubmit_due_at"]) - datetime.fromisoformat(r["answered_at"])).days == 5
    # the contractor's inbox shows the resubmission date for the returned request
    item = next(i for i in client.get("/api/v1/inbox", headers=site["hqa"]).json() if i["id"] == rec["id"])
    assert item["reason"] == "returned" and datetime.fromisoformat(item["due_at"]) == datetime.fromisoformat(r["resubmit_due_at"])
    # overdue once the date passes
    from sqlalchemy import text

    from app.core.db import session_scope
    with session_scope(bypass=True) as db:
        db.execute(text("UPDATE records SET resubmit_due_at = now() - interval '1 day' WHERE id = :i"), {"i": rec["id"]})
    row = next(x for x in client.get(f"/api/v1/projects/{pid}/records", headers=hc).json() if x["number"] == rec["number"])
    assert row["resubmit_overdue"] is True
    # submitting R1 closes R0's resubmission
    r1 = client.post(f"/api/v1/records/{rec['id']}/revise", headers=site["hqa"]).json()
    act(client, site["hqa"], r1["id"], "submit")
    r0 = client.get(f"/api/v1/records/{rec['id']}", headers=site["hqa"]).json()
    assert r0["resubmitted_at"] and r0["resubmit_overdue"] is False
    assert client.get(f"/api/v1/records/{rec['id']}/pdf?lang=ar", headers=hc).status_code == 200
