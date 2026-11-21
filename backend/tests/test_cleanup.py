from sqlalchemy import func, select

from app.core.db import session_scope
from tests.test_records import new_sub, site, submit  # noqa: F401 (fixture)


def test_cleanup_deletes_unused_and_switches_off_the_rest(client, site):
    from app.models.core import ProjectMember, User
    from app.scripts.cleanup_users import apply, plan
    submit(client, site, new_sub(client, site))  # the QA engineer is now in the history
    emails = {k: client.get("/api/v1/auth/me", headers=site[k]).json()["user"]["email"] for k in ("hc", "hqa", "hee")}
    with session_scope(bypass=True) as db:
        rows = [r for r in plan(db, {emails["hc"]}) if r["user"].email in emails.values()]
        by = {r["user"].email: r for r in rows}
        assert emails["hc"] not in by  # kept
        assert by[emails["hqa"]]["action"] == "deactivate" and by[emails["hqa"]]["refs"] > 0
        assert by[emails["hee"]]["action"] == "delete"
        apply(db, rows)
    with session_scope(bypass=True) as db:
        qa = db.scalar(select(User).where(User.email == emails["hqa"]))
        assert qa is not None and qa.is_active is False
        assert not db.scalar(select(func.count()).select_from(ProjectMember).where(ProjectMember.user_id == qa.id,
                                                                                  ProjectMember.is_active))
        assert db.scalar(select(User).where(User.email == emails["hee"])) is None
    # the switched-off account cannot sign in; the kept one still works
    assert client.post("/api/v1/auth/login", json={"email": emails["hqa"], "password": "a-strong-password"}).status_code in (401, 403)
    assert client.get(f"/api/v1/projects/{site['pid']}/records", headers=site["hc"]).status_code == 200


def test_merge_placeholder_into_real_account(client, site):
    from app.models.core import User
    from app.models.records import Record
    from app.scripts.merge_users import merge
    rec = new_sub(client, site)
    submit(client, site, rec)
    rid = rec["id"]
    real = client.get("/api/v1/auth/me", headers=site["hee"]).json()["user"]["email"]
    with session_scope(bypass=True) as db:
        qa_email = client.get("/api/v1/auth/me", headers=site["hqa"]).json()["user"]["email"]
        src = db.scalar(select(User).where(User.email == qa_email))
        src.email = "odoo-t-u9@import.verqac.invalid"  # stand in for an imported placeholder
        db.flush()
        dst = db.scalar(select(User).where(User.email == real))
        counts = merge(db, src, dst)
        assert counts.get("records.created_by") and counts.get("record_events.actor_id")
    with session_scope(bypass=True) as db:
        assert db.scalar(select(User).where(User.email == "odoo-t-u9@import.verqac.invalid")) is None
        r = db.get(Record, rid)
        assert db.get(User, r.created_by).email == real


def test_revert_test_answers(client, site):
    from app.models.core import Project, User
    from app.models.records import Record, RecordEvent
    from app.scripts.revert_answers import main
    from tests.test_records import act
    rec = new_sub(client, site)
    submit(client, site, rec)
    assert act(client, site["hce"], rec["id"], "approve").status_code == 200
    ce = client.get("/api/v1/auth/me", headers=site["hce"]).json()["user"]["email"]
    with session_scope(bypass=True) as db:
        code = db.get(Project, site["pid"]).code
    main(["--project", code, "--by", ce])  # trial
    with session_scope(bypass=True) as db:
        assert db.get(Record, rec["id"]).state_category == "approved"
    main(["--project", code, "--by", ce, "--commit"])
    with session_scope(bypass=True) as db:
        r = db.get(Record, rec["id"])
        assert r.state_category == "submitted" and r.answered_at is None and r.answered_by is None
        uid = db.scalar(select(User.id).where(User.email == ce))
        assert not db.scalar(select(func.count()).select_from(RecordEvent).where(RecordEvent.record_id == r.id,
                                                                                 RecordEvent.actor_id == uid))
    assert act(client, site["hce"], rec["id"], "approve").status_code == 200  # it can be answered again


def test_revert_daily_report_approval_recounts_progress(client, site):
    from datetime import date, timedelta

    from app.models.core import Project
    from app.scripts.revert_answers import main
    from tests.test_daily import _structure
    from tests.test_records import act
    pid = site["pid"]
    st = _structure(client, site)
    d1 = (date.today() - timedelta(days=1)).isoformat()
    rid = client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"], json={"report_date": d1}).json()["id"]
    client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"], json={
        "works": [{"stage_id": st["stages"][3]["id"], "all_locations": True, "description": "بلوك", "progress": 50}]})
    act(client, site["hqa"], rid, "submit")
    assert act(client, site["hce"], rid, "approve").status_code == 200
    assert client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()["project"] > 0
    ce = client.get("/api/v1/auth/me", headers=site["hce"]).json()["user"]["email"]
    with session_scope(bypass=True) as db:
        code = db.get(Project, pid).code
    main(["--project", code, "--by", ce, "--commit"])
    assert client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()["project"] == 0
    assert client.get(f"/api/v1/records/{rid}", headers=site["hqa"]).json()["state"]["category"] == "submitted"


def test_claim_placeholder_as_a_working_account(client, site, tmp_path):
    import json
    import uuid

    from app.models.core import OrgMember, ProjectMember, ProjectParty, User
    from app.scripts.claim_users import main
    with session_scope(bypass=True) as db:
        party = db.scalar(select(ProjectParty).where(ProjectParty.project_id == uuid.UUID(site["pid"]),
                                                     ProjectParty.kind == "consultant"))
        role = db.scalar(select(ProjectMember.role_id).where(ProjectMember.project_id == uuid.UUID(site["pid"]),
                                                             ProjectMember.party_id == party.id))
        for k in ("u77", "p88"):
            u = User(id=uuid.uuid4(), email=f"odoo-t-{k}@import.verqac.invalid", password_hash="!", full_name_ar="م. سامر",
                     full_name_en="Samer", is_active=False)
            db.add(u)
            db.flush()
            db.add(ProjectMember(project_id=uuid.UUID(site["pid"]), user_id=u.id, party_id=party.id, role_id=role, is_active=False))
        org = party.org_id
    (tmp_path / "data.json").write_text(json.dumps({"users": [{"id": 77, "login": "Samer@Madar.example", "name": "x"}]}))
    main([str(tmp_path), "--person", "u77+p88"])  # trial
    with session_scope(bypass=True) as db:
        assert db.scalar(select(User).where(User.email == "samer@madar.example")) is None
    main([str(tmp_path), "--person", "u77+p88", "--commit"])
    with session_scope(bypass=True) as db:
        u = db.scalar(select(User).where(User.email == "samer@madar.example"))
        assert u.is_active and db.scalar(select(ProjectMember.is_active).where(ProjectMember.user_id == u.id))
        assert db.scalar(select(func.count()).select_from(User).where(User.email.like("odoo-t-%"))) == 0
        assert db.scalar(select(OrgMember.id).where(OrgMember.user_id == u.id, OrgMember.org_id == org))


def test_team_hides_imported_people_who_never_joined(client, site):
    import uuid

    from app.models.core import ProjectMember, User
    with session_scope(bypass=True) as db:
        m = db.scalar(select(ProjectMember).where(ProjectMember.project_id == uuid.UUID(site["pid"])))
        u = User(id=uuid.uuid4(), email="odoo-t-u5@import.verqac.invalid", password_hash="!", full_name_ar="قديم",
                 full_name_en="Old", is_active=False)
        db.add(u)
        db.flush()
        db.add(ProjectMember(project_id=m.project_id, user_id=u.id, party_id=m.party_id, role_id=m.role_id, is_active=False))
    team = client.get(f"/api/v1/projects/{site['pid']}/team", headers=site["hc"]).json()
    assert team["members"] and all("import.verqac.invalid" not in x["user"]["email"] for x in team["members"])
