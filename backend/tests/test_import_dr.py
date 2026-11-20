import json
from datetime import date, timedelta

from sqlalchemy import select

from app.core.db import session_scope
from app.models.core import User
from app.scripts.import_dr import TrialRun, floor_ar, main
from tests.test_daily import _structure
from tests.test_records import act, site  # noqa: F401


def test_stage_limited_to_some_floors(client, site):
    pid = site["pid"]
    st = _structure(client, site)
    stg, floors = st["stages"][0], st["locations"][0]["units"]
    d1 = date.today() - timedelta(days=2)
    rid = client.post(f"/api/v1/projects/{pid}/daily-reports", headers=site["hqa"], json={"report_date": d1.isoformat()}).json()["id"]
    client.put(f"/api/v1/records/{rid}/daily", headers=site["hqa"],
               json={"works": [{"stage_id": stg["id"], "location_ids": [floors[0]["id"]], "progress": 100}]})
    act(client, site["hqa"], rid, "submit")
    act(client, site["hce"], rid, "approve")
    n = len(floors)
    assert client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()["stages"][stg["id"]] == round(100 / n, 1)
    # the stage applies to two floors only: 1 of 2 done
    stages = st["stages"]
    stages[0]["location_ids"] = [floors[0]["id"], floors[1]["id"]]
    r = client.put(f"/api/v1/projects/{pid}/stages", headers=site["hc"], json=stages)
    assert r.status_code == 200 and r.json()["stages"][0]["location_ids"] == [floors[0]["id"], floors[1]["id"]]
    assert client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()["stages"][stg["id"]] == 50
    # all floors ticked = no limit; a whole-project stage keeps none
    stages[0]["location_ids"] = []
    assert client.put(f"/api/v1/projects/{pid}/stages", headers=site["hc"], json=stages).json()["stages"][0]["location_ids"] is None


def _export(tmp_path, today):
    u = lambda i, n: [i, n]  # noqa: E731
    day = (today - timedelta(days=5)).isoformat()
    data = {
        "meta": {"db": "t", "projects": [50], "exported_at": "x"},
        "projects": [{"id": 50, "name": "AAUP", "date_start": (today - timedelta(days=30)).isoformat()}],
        "users": [{"id": 5, "name": "م. فراس", "login": "f@x.ps"}, {"id": 6, "name": "م. سعد", "login": "s@x.ps"}],
        "models": {
            "dr.schedule.stage": [{"id": 1, "name": "Structure", "scope": "floor", "weight": 60, "sequence": 1, "active": True},
                                  {"id": 2, "name": "Paint", "scope": "floor", "weight": 30, "sequence": 2, "active": True},
                                  {"id": 3, "name": "Elevator", "scope": "building", "weight": 10, "sequence": 3, "active": True}],
            "dr.schedule.location": [{"id": 10, "name": "Ground floor", "level": 0, "active": True, "floorx_ids": [100]},
                                     {"id": 11, "name": "Floor 1", "level": 1, "active": True, "floorx_ids": [101]}],
            "dr.schedule.cell": [{"stage_id": u(1, "S"), "location_id": u(10, "G"), "progress": 100, "actual_start": day, "actual_finish": day},
                                 {"stage_id": u(1, "S"), "location_id": u(11, "F1"), "progress": 50, "actual_start": day, "actual_last": day},
                                 {"stage_id": u(2, "P"), "location_id": u(10, "G"), "progress": 100, "actual_start": day, "actual_finish": day},
                                 {"stage_id": u(3, "E"), "location_id": False, "progress": 0}],
            "dr.schedule.rule": [{"stage_id": u(1, "S"), "action_id": u(7, "Concrete Cast"), "workx_id": False}],
            "submit.submit": [
                {"id": 1, "name": "SH-C-001", "submitalrev": "R0", "status": "revise_and_resubmit", "category": "civil",
                 "submitaldate": day, "submitalanswerdate": day, "submitalname": "Raft", "submitaltye": u(1, "Shop Drawings"),
                 "submitby": u(5, "م. فراس"), "submitto": u(6, "م. سعد"), "submitalsupervnote": "......", "internalnote": "ملاحظة"},
                {"id": 2, "name": "SH-C-001", "submitalrev": "r1", "status": "approved_as_noted", "category": "civil",
                 "submitaldate": day, "submitaltime": "1:00pm", "submitalanswerdate": day, "submitalname": "Raft",
                 "submitaltye": u(2, "As built drawing"), "submitby": u(5, "م. فراس"), "submitto": u(6, "م. سعد")},
                {"id": 3, "name": "SH-C-001", "submitalrev": "r1", "status": "cancelled", "category": "civil", "submitaldate": day}],
            "inspection.inspection": [{"id": 1, "name": "IR-C-001", "inspectionrev": "r0", "status": "approved", "category": "civil",
                                       "date": day, "inspectiondate": day, "inspectiontime": "09:00", "inspectionanswerdate": day,
                                       "floorselect": u(101, "1st"), "inspectionaction": u(7, "Concrete Cast"),
                                       "inspectionsubmitby": u(5, "م. فراس"), "inspectionsubmitto": u(6, "م. سعد")}],
            "rfi.rfi": [{"id": 1, "name": "RFI-C-001", "rfirev": "r0", "status": "answered", "category": "civil", "rfidate": day,
                         "rfianswerdate": day, "rfisubject": "سؤال", "rfisubmitby": u(5, "م. فراس"), "rfisubmitto": u(6, "م. سعد")}],
            "site.instruction": [{"id": 1, "name": "6", "status": "closed", "category": "civil", "instruction_date": day,
                                  "close_date": day, "action_done_date": day, "site_subject": "تعشيش",
                                  "submit_from": u(900, "Eng Q"), "submit_to": u(901, "م. معتز")}],
            "site.instruction.line": [{"instruction_id": u(1, "6"), "description": "معالجة التعشيش"}],
            "quality.quality": [{"id": 1, "name": "CC-1", "status": "submitted", "category": "civil", "date": day, "submitaldate": day,
                                 "final_result": "pass", "acceptance_method": "all", "material_type_id": u(1, "Concrete")}],
            "dr.test.result.line": [{"test_id": u(1, "CC-1"), "parameter": "Slump", "value_kind": "number", "value": 10, "max_value": 12}],
            "dr.material.type": [{"id": 1, "code": "CON"}],
            "dr.dr": [{"id": 1, "name": "001", "date": day, "status": "signed", "weather": u(1, "Sunny"), "wind": u(1, "No Wind"),
                       "work": u(1, "Working Day"), "temperature": "20-25", "submitby": u(5, "م. فراس")},
                      {"id": 2, "name": "002", "date": (today - timedelta(days=4)).isoformat(), "status": "draft"}],
            "teams.teams": [{"teams_id": u(1, "001"), "staff": u(1, "Site Engineer"), "value": 2, "wtime": "8"}],
            "equip.equip": [{"equip_id": u(1, "001"), "euiplist": u(1, "Tower Crane"), "qty": 1}],
            "work.work": [{"work_id": u(1, "001"), "schedule_stage_id": u(1, "S"), "schedule_location_id": u(11, "F1"),
                           "actiondone": u(7, "Concrete Cast"), "itemname": "slab", "qty": 30, "progress_pct": 0,
                           "laborno": 4, "labortime": 8, "subcontselec": u(3, "Company Labors")},
                          {"work_id": u(1, "001"), "itemname": "formwork", "laborno": 3, "labortime": 6, "subcontselec": u(3, "Company Labors")},
                          {"work_id": u(1, "001"), "itemname": "blocks", "laborno": 5, "subcontselec": u(4, "Block team")}],
        },
    }
    f = tmp_path / "data.json"
    f.write_text(json.dumps(data, ensure_ascii=False))
    return str(f)


def test_import_trial_then_commit(client, site, tmp_path, capsys):
    pid, code = site["pid"], site["code"]
    _structure(client, site)
    me = client.get("/api/v1/auth/me", headers=site["hc"]).json()["user"]["email"]
    f = _export(tmp_path, date.today())
    main([f, "--project", code, "--as", me])  # trial: nothing written
    out = capsys.readouterr().out
    assert "TRIAL RUN" in out and "Progress after the import: 75.0%" in out
    assert client.get(f"/api/v1/projects/{pid}/structure", headers=site["hc"]).json()["stages"][0]["name_en"] != "Paint"
    main([f, "--project", code, "--as", me, "--commit"])
    s = client.get(f"/api/v1/projects/{pid}/structure", headers=site["hc"]).json()
    assert [x["name_ar"] for x in s["stages"]] == ["الهيكل الإنشائي", "الدهان", "المصاعد"]
    assert [u["name_ar"] for u in s["locations"][0]["units"]] == ["الطابق الأرضي", "الطابق الأول"]
    ground = s["locations"][0]["units"][0]["id"]
    assert s["stages"][1]["location_ids"] == [ground] and s["stages"][2]["scope"] == "whole"
    p = client.get(f"/api/v1/projects/{pid}/progress", headers=site["hk"]).json()
    assert p["project"] == 75.0 and p["stages"][s["stages"][1]["id"]] == 100  # paint: one floor of one
    # submittals: a revision chain, the cancelled copy kept apart, the reply and the resubmission
    regs = client.get(f"/api/v1/projects/{pid}/records", headers=site["hc"], params={"type": "submittal"}).json()
    items = regs["items"] if isinstance(regs, dict) else regs
    assert sorted((x["number"], x["rev_no"]) for x in items) == [("SH-C-001", 1), ("SH-C-001", 1)]  # latest revisions
    from app.models.records import Record
    with session_scope(bypass=True) as db:
        r0 = db.scalar(select(Record.id).where(Record.number == "SH-C-001", Record.rev_no == 0, Record.project_id == pid))
    d = client.get(f"/api/v1/records/{r0}", headers=site["hc"]).json()
    assert d["state"]["category"] == "revise_and_resubmit" and d["response_comment"] is None and d["resubmitted_at"]
    assert d["submitted_by"]["full_name_ar"] == "م. فراس" and d["answered_by"]["full_name_ar"] == "م. سعد"
    with session_scope(bypass=True) as db:
        ph = db.scalar(select(User).where(User.full_name_ar == "م. فراس"))
        assert ph.is_active is False and ph.password_hash == "!"
    # nobody can log in as a placeholder
    assert client.post("/api/v1/auth/login", json={"email": ph.email, "password": "a-strong-password"}).status_code in (401, 422)
    # daily report: weather, crew, the schedule % and the draft
    drs = client.get(f"/api/v1/projects/{pid}/records", headers=site["hc"], params={"type": "daily_report"}).json()
    drs = drs["items"] if isinstance(drs, dict) else drs
    assert sorted(x["state"]["category"] for x in drs) == ["approved", "draft"]
    first = next(x for x in drs if x["state"]["category"] == "approved")
    dd = client.get(f"/api/v1/records/{first['id']}/daily", headers=site["hc"]).json()
    assert dd["weather"] == "sunny" and dd["temp_min"] == 20 and dd["crew"][0]["count"] == 2 and dd["equipment"][0]["name"] == "Tower Crane"
    assert any(w["progress"] == 100 for w in dd["works"])
    # importing again replaces everything (no duplicates)
    main([f, "--project", code, "--as", me, "--commit"])
    again = client.get(f"/api/v1/projects/{pid}/records", headers=site["hc"], params={"type": "submittal"}).json()
    assert len(again["items"] if isinstance(again, dict) else again) == 2


def test_floor_names():
    assert floor_ar("Floor 3") == "الطابق الثالث" and floor_ar("Basement 1") == "التسوية الأولى"
    assert floor_ar("Roof") == "السطح" and floor_ar("Floor 25") == "الطابق 25"
    assert TrialRun.__doc__


def test_import_attachments(client, site, tmp_path, capsys):
    code = site["code"]
    _structure(client, site)
    me = client.get("/api/v1/auth/me", headers=site["hc"]).json()["user"]["email"]
    f = _export(tmp_path, date.today())
    main([f, "--project", code, "--as", me, "--commit"])
    data = json.loads(open(f, encoding="utf-8").read())
    (tmp_path / "files").mkdir()
    (tmp_path / "files" / "7").write_bytes(b"%PDF-1.4 sheet")
    (tmp_path / "files" / "8").write_bytes(b"\xff\xd8 photo")
    data["attachments"] = [
        {"id": 7, "name": "sheet.pdf", "mimetype": "application/pdf", "res_model": "submit.submit", "res_id": 1,
         "res_field": "pdf_file", "path": "files/7", "create_date": "2025-01-02 10:00:00"},
        {"id": 8, "name": "site.jpg", "mimetype": "image/jpeg", "res_model": "dr.dr", "res_id": 1, "res_field": False, "path": "files/8"},
        {"id": 9, "name": "gone.pdf", "res_model": "submit.submit", "res_id": 999, "path": None}]
    (tmp_path / "data.json").write_text(json.dumps(data, ensure_ascii=False))
    main([str(tmp_path), "--attachments", "--project", code, "--as", me])  # trial: nothing moved
    assert "TRIAL RUN" in capsys.readouterr().out and (tmp_path / "files" / "7").exists()
    main([str(tmp_path), "--attachments", "--project", code, "--as", me, "--commit"])
    out = capsys.readouterr().out
    assert "attached (submission)" in out and "attached (photo)" in out and "no record" in out
    assert not (tmp_path / "files" / "7").exists()  # moved into the storage
    from app.models.records import Record
    with session_scope(bypass=True) as db:
        r0 = db.scalar(select(Record.id).where(Record.number == "SH-C-001", Record.rev_no == 0, Record.project_id == site["pid"]))
    d = client.get(f"/api/v1/records/{r0}", headers=site["hc"]).json()
    att = d["attachments"][0]
    assert att["filename"] == "sheet.pdf" and att["kind"] == "submission"
    assert client.get(f"/api/v1/files/{att['file_id']}", headers=site["hc"]).content == b"%PDF-1.4 sheet"
    # again: nothing new
    main([str(tmp_path), "--attachments", "--project", code, "--as", me, "--commit"])
    assert "already attached" in capsys.readouterr().out


def test_fix_dates_and_answer_on_paper(client, site, tmp_path, capsys):
    pid, code = site["pid"], site["code"]
    _structure(client, site)
    me = client.get("/api/v1/auth/me", headers=site["hc"]).json()["user"]["email"]
    today = date.today()
    f = _export(tmp_path, today)
    data = json.loads(open(f, encoding="utf-8").read())
    made, edited = today - timedelta(days=60), today - timedelta(days=10)
    # submitted on paper 60 days ago, never answered in Odoo, its date edited 10 days ago
    data["models"]["inspection.inspection"].append(
        {"id": 2, "name": "IR-C-822", "inspectionrev": "r0", "status": "submitted", "category": "civil", "date": edited.isoformat(),
         "inspectiondate": edited.isoformat(), "create_date": f"{made.isoformat()} 06:03:53", "inspectionname": "HPL",
         "inspectionsubmitby": [5, "م. فراس"], "inspectionsubmitto": [6, "م. سعد"]})
    open(f, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False))
    main([f, "--project", code, "--as", me, "--commit"])
    from app.models.records import Record
    with session_scope(bypass=True) as db:
        rid = db.scalar(select(Record.id).where(Record.number == "IR-C-822", Record.project_id == pid))
    d = client.get(f"/api/v1/records/{rid}", headers=site["hc"]).json()
    assert d["submitted_at"][:10] == made.isoformat() and d["requested_for"][:10] == made.isoformat() and d["imported"]
    # an import made before the fix: dates moved back, deadline removed, files renamed -> --fix corrects in place
    with session_scope(bypass=True) as db:
        r = db.get(Record, rid)
        from datetime import datetime, time
        from zoneinfo import ZoneInfo
        r.submitted_at = datetime.combine(edited, time(8), ZoneInfo("Asia/Hebron"))
        r.requested_for = datetime.combine(edited, time(9), ZoneInfo("Asia/Hebron"))
    main([f, "--fix", "--project", code, "--as", me])
    assert "TRIAL RUN" in capsys.readouterr().out
    main([f, "--fix", "--project", code, "--as", me, "--commit"])
    assert "submission dates corrected" in capsys.readouterr().out
    assert client.get(f"/api/v1/records/{rid}", headers=site["hc"]).json()["submitted_at"][:10] == made.isoformat()
    # supervision enters the paper answer with its real day
    hce = site["hce"]
    paper = made + timedelta(days=1)
    bad = client.post(f"/api/v1/records/{rid}/transitions", headers=hce,
                      json={"action": "reject", "comment": "x", "answered_on": (today + timedelta(days=2)).isoformat()})
    assert bad.status_code == 422 and bad.json()["detail"] == "answered_on_range"
    r = client.post(f"/api/v1/records/{rid}/transitions", headers=hce,
                    json={"action": "reject", "comment": "1- تنظيف HPL", "answered_on": paper.isoformat()})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["answered_at"][:10] == paper.isoformat() and d["performed_at"][:10] == paper.isoformat()
    assert d["resubmit_due_at"][:10] >= today.isoformat()  # the contractor's time counts from now
    # only imported records take a past answer date
    from tests.test_records import new_sub, submit
    s2 = new_sub(client, site)
    submit(client, site, s2)
    r = client.post(f"/api/v1/records/{s2['id']}/transitions", headers=hce, json={"action": "approve", "answered_on": today.isoformat()})
    assert r.status_code == 403


def test_photo_captions_and_letterheads(client, site, tmp_path, capsys):
    code = site["code"]
    _structure(client, site)
    me = client.get("/api/v1/auth/me", headers=site["hc"]).json()["user"]["email"]
    f = _export(tmp_path, date.today())
    data = json.loads(open(f, encoding="utf-8").read())
    data["models"]["dr.dr"][0]["image_1_desc"] = "8th floor painting work"
    main([f, "--project", code, "--as", me, "--commit"])
    (tmp_path / "files").mkdir()
    for n in ("1", "2", "3"):
        (tmp_path / "files" / n).write_bytes(b"\xff\xd8 photo " + n.encode())
    rid = data["models"]["dr.dr"][0]["id"]
    data["attachments"] = [
        {"id": 1, "name": "image_1", "mimetype": "image/jpeg", "res_model": "dr.dr", "res_id": rid, "res_field": "image_1", "path": "files/1"},
        {"id": 2, "name": "logo_image", "mimetype": "image/png", "res_model": "dr.dr", "res_id": rid, "res_field": "logo_image", "path": "files/2"},
        {"id": 3, "name": "image_2", "mimetype": "image/jpeg", "res_model": "dr.dr", "res_id": rid, "res_field": "image_2", "path": "files/3"}]
    (tmp_path / "data.json").write_text(json.dumps(data, ensure_ascii=False))
    main([str(tmp_path), "--attachments", "--project", code, "--as", me, "--commit"])
    out = capsys.readouterr().out
    assert "letterhead skipped" in out, out
    from app.models.core import ProjectParty
    from app.models.records import Attachment, Record, StoredFile
    with session_scope(bypass=True) as db:
        rec = db.scalar(select(Record).where(Record.legacy_ref == f"odoo:dr.dr:{rid}", Record.project_id == site["pid"]))
        caps = sorted((a.caption or "") for a in db.scalars(select(Attachment).where(Attachment.record_id == rec.id)))
        assert caps == ["", "8th floor painting work"], out
        # an import made before: the letterhead came in as a photo and captions were not kept
        party = db.scalar(select(ProjectParty.id).where(ProjectParty.project_id == site["pid"], ProjectParty.kind == "contractor"))
        from app.core import storage
        dest = storage._root() / f"{site['pid']}/odoo-2"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"logo")
        lf = StoredFile(project_id=site["pid"], storage_key=f"{site['pid']}/odoo-2", filename="logo_image.png",
                        content_type="image/png", size=4, sha256="x", uploaded_by=rec.submitted_by)
        db.add(lf)
        db.flush()
        db.add(Attachment(record_id=rec.id, file_id=lf.id, kind="photo", party_id=party))
        for a in db.scalars(select(Attachment).where(Attachment.record_id == rec.id)):
            a.caption = None
        rec_id = rec.id
    main([f, "--fix", "--project", code, "--as", me, "--commit"])
    out = capsys.readouterr().out
    assert "letterheads removed" in out and "photo captions added" in out and not dest.exists()
    main([f, "--fix", "--project", code, "--as", me])  # again: nothing left to correct
    out = capsys.readouterr().out
    assert "removed" not in out and "added" not in out and "renamed" not in out and "corrected" not in out, out
    d = client.get(f"/api/v1/records/{rec_id}", headers=site["hc"]).json()
    assert len(d["attachments"]) == 2
    one = next(a for a in d["attachments"] if a["caption"])
    assert one["caption"] == "8th floor painting work"
    # a caption is written by the party that attached the photo
    r = client.patch(f"/api/v1/records/{rec_id}/attachments/{one['id']}", json={"caption": "  الطابق الثامن - دهان "}, headers=site["hc"])
    assert r.status_code == 200, r.text
    assert any(a["caption"] == "الطابق الثامن - دهان" for a in r.json()["attachments"])
    r = client.patch(f"/api/v1/records/{rec_id}/attachments/{one['id']}", json={"caption": "x"}, headers=site["hk"])
    assert r.status_code == 403


def test_labour_from_work_lines(client, site, tmp_path, capsys):
    code = site["code"]
    _structure(client, site)
    me = client.get("/api/v1/auth/me", headers=site["hc"]).json()["user"]["email"]
    f = _export(tmp_path, date.today())
    main([f, "--project", code, "--as", me, "--commit"])
    from app.models.daily import DailyReport
    with session_scope(bypass=True) as db:
        drs = db.scalars(select(DailyReport).where(DailyReport.project_id == site["pid"])).all()
        lab = sorted((c["name"], c["count"], c["hours"]) for d in drs for c in d.crew if c["group"] == "labour")
        assert lab == [("Block team", 5, None), ("Company Labors", 7, 8.0)]
        assert all(c.get("auto") for d in drs for c in d.crew if c["group"] == "labour")
        assert {w.get("team") for d in drs for w in d.works} >= {"Company Labors", "Block team"}
        for d in drs:  # an import made before: no team on the work lines, no labour
            d.crew = [c for c in d.crew if c["group"] != "labour"]
            d.works = [{k: v for k, v in w.items() if k not in ("team", "team_en", "sub", "hours")} for w in d.works]
    main([f, "--fix", "--project", code, "--as", me, "--commit"])
    out = capsys.readouterr().out
    assert "daily reports: team on work lines" in out and "daily reports: labour from work lines" in out
    with session_scope(bypass=True) as db:
        drs = db.scalars(select(DailyReport).where(DailyReport.project_id == site["pid"])).all()
        assert sum(c["count"] for d in drs for c in d.crew if c["group"] == "labour") == 12
    main([f, "--fix", "--project", code, "--as", me])
    assert "labour" not in capsys.readouterr().out
