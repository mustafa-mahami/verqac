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
