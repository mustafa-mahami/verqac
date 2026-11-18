import io
from datetime import date, timedelta

from openpyxl import Workbook, load_workbook

from tests.test_daily import _structure
from tests.test_records import act, site  # noqa: F401


def _prg(client, s):
    r = client.post(f"/api/v1/projects/{s['pid']}/programme", headers=s["hqa"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_programme_cycle_approval_and_plan(client, site):
    s, pid = site, site["pid"]
    st = _structure(client, s)
    structure = st["stages"][0]
    floors = st["locations"][0]["units"]
    today = date.today()
    rid = _prg(client, s)
    assert client.post(f"/api/v1/projects/{pid}/programme", headers=s["hqa"]).status_code == 409  # one per project
    # floor cycle: the structure starts 20 days ago, 10 days a floor, the next floor 10 days later
    start = today - timedelta(days=20)
    lines = [{"stage_id": structure["id"], "location_id": f["id"],
              "start": (start + timedelta(days=10 * i)).isoformat(), "finish": (start + timedelta(days=10 * i + 9)).isoformat()}
             for i, f in enumerate(floors)]
    r = client.put(f"/api/v1/records/{rid}/programme", headers=s["hqa"],
                   json={"lines": lines, "cycles": [{"stage_id": structure["id"], "start": start.isoformat(), "duration": 10, "lag": 10}],
                         "source": "cycle"})
    assert r.status_code == 200, r.text
    assert r.json()["start"] == start.isoformat() and len(r.json()["lines"]) == len(floors)
    # nothing planned until supervision approves
    assert client.get(f"/api/v1/projects/{pid}/progress", headers=s["hc"]).json()["planned"] is None
    act(client, s["hqa"], rid, "submit")
    assert act(client, s["hce"], rid, "approve").status_code == 200
    p = client.get(f"/api/v1/projects/{pid}/progress", headers=s["hc"]).json()
    # floors 1 and 2 done by plan (2 of 6 floors), floor 3 started today (1/10): structure ~ (100+100+10)/6
    assert p["planned_stages"][structure["id"]] == 35.0
    assert p["planned"] == round(20 * 35 / 100, 1) and p["spi"] == 0.0
    late = {c["location_id"] for c in p["late"]}
    assert floors[0]["id"] in late and floors[1]["id"] in late and floors[3]["id"] not in late
    assert p["plan_curve"][0]["day"] == start.isoformat()
    assert client.get(f"/api/v1/records/{rid}/pdf?lang=ar", headers=s["hce"]).status_code == 200
    # the update: a new revision from the approved one, same lines; the first stays the baseline
    summ = client.get(f"/api/v1/projects/{pid}/programme", headers=s["hc"]).json()
    assert summ["baseline_id"] == rid and summ["current_id"] == rid and not summ["can_create"]
    r2 = client.post(f"/api/v1/records/{rid}/revise", headers=s["hqa"])
    assert r2.status_code == 201, r2.text
    rid2 = r2.json()["id"]
    lines2 = client.get(f"/api/v1/records/{rid2}/programme", headers=s["hqa"]).json()["lines"]
    assert len(lines2) == len(floors)
    for x in lines2:  # a month later for every floor
        x["start"] = (date.fromisoformat(x["start"]) + timedelta(days=30)).isoformat()
        x["finish"] = (date.fromisoformat(x["finish"]) + timedelta(days=30)).isoformat()
    client.put(f"/api/v1/records/{rid2}/programme", headers=s["hqa"], json={"lines": lines2})
    act(client, s["hqa"], rid2, "submit")
    act(client, s["hce"], rid2, "approve")
    p = client.get(f"/api/v1/projects/{pid}/progress", headers=s["hc"]).json()
    assert p["programme_id"] == rid2 and p["baseline_id"] == rid
    assert p["planned"] == 0 and p["planned_baseline"] == 7.0 and p["baseline_curve"]


def test_programme_import_template_and_match(client, site):
    s, pid = site, site["pid"]
    st = _structure(client, s)
    rid = _prg(client, s)
    # the template has a row per cell; fill two of them
    r = client.get(f"/api/v1/projects/{pid}/programme/template?lang=ar", headers=s["hqa"])
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb.active
    assert ws.cell(1, 1).value == "المرحلة" and ws.max_row > 6
    ws.cell(2, 3).value, ws.cell(2, 4).value = date(2026, 12, 1), date(2026, 12, 20)
    buf = io.BytesIO()
    wb.save(buf)
    rows = client.post(f"/api/v1/records/{rid}/programme/import", headers=s["hqa"],
                       files={"file": ("p.xlsx", buf.getvalue())}).json()
    first = rows[0]
    assert first["stage_id"] == st["stages"][0]["id"] and first["location_id"] == st["locations"][0]["units"][0]["id"]
    assert first["start"] == "2026-12-01"
    # an MS Project style export: outline levels give the floor, names give the stage (English names here)
    wb = Workbook()
    ws = wb.active
    floor = st["locations"][0]["units"][1]
    ws.append(["ID", "Task Name", "Duration", "Start", "Finish", "Outline Level"])
    ws.append([1, floor["name_en"], "20 days", "Mon 12/1/26", "Fri 12/26/26", 1])
    ws.append([2, st["stages"][0]["name_en"], "20 days", "Mon 12/1/26", "Fri 12/26/26", 2])
    buf = io.BytesIO()
    wb.save(buf)
    rows = client.post(f"/api/v1/records/{rid}/programme/import", headers=s["hqa"],
                       files={"file": ("msp.xlsx", buf.getvalue())}).json()
    task = rows[1]
    assert task["stage_id"] == st["stages"][0]["id"] and task["location_id"] == floor["id"]
    assert task["start"] == "2026-12-01" and task["finish"] == "2026-12-26"
    # MS Project XML and Primavera XER
    xml = f"""<?xml version="1.0"?><Project xmlns="http://schemas.microsoft.com/project"><Tasks>
      <Task><Name>P</Name><OutlineLevel>0</OutlineLevel></Task>
      <Task><Name>{floor['name_ar']}</Name><OutlineLevel>1</OutlineLevel><Summary>1</Summary></Task>
      <Task><Name>{st['stages'][0]['name_ar']}</Name><OutlineLevel>2</OutlineLevel><Summary>0</Summary>
        <Start>2026-12-01T08:00:00</Start><Finish>2026-12-10T17:00:00</Finish></Task></Tasks></Project>"""
    rows = client.post(f"/api/v1/records/{rid}/programme/import", headers=s["hqa"],
                       files={"file": ("p.xml", xml.encode())}).json()
    assert rows[0]["location_id"] == floor["id"] and rows[0]["finish"] == "2026-12-10"
    xer = "\n".join(["ERMHDR\t19.12", "%T\tPROJWBS", "%F\twbs_id\tparent_wbs_id\twbs_name\tproj_node_flag",
                     "%R\t1\t\tP\tY", f"%R\t2\t1\t{floor['name_en']}\tN",
                     "%T\tTASK", "%F\ttask_id\twbs_id\ttask_name\ttarget_start_date\ttarget_end_date",
                     f"%R\t10\t2\t{st['stages'][0]['name_en']} works\t2026-12-01 08:00\t2026-12-15 17:00"])
    rows = client.post(f"/api/v1/records/{rid}/programme/import", headers=s["hqa"],
                       files={"file": ("p.xer", xer.encode())}).json()
    assert rows[0]["stage_id"] == st["stages"][0]["id"] and rows[0]["location_id"] == floor["id"]
    assert client.post(f"/api/v1/records/{rid}/programme/import", headers=s["hqa"],
                       files={"file": ("p.pdf", b"%PDF")}).status_code == 422


def test_programme_exports(client, site):
    s, pid = site, site["pid"]
    st = _structure(client, s)
    rid = _prg(client, s)
    floors = st["locations"][0]["units"]
    lines = [{"stage_id": st["stages"][0]["id"], "location_id": f["id"], "start": f"2026-12-{1 + i * 3:02d}", "finish": f"2026-12-{3 + i * 3:02d}"}
             for i, f in enumerate(floors)]
    client.put(f"/api/v1/records/{rid}/programme", headers=s["hqa"], json={"lines": lines})
    r = client.get(f"/api/v1/records/{rid}/programme/xlsx?lang=ar", headers=s["hqa"])
    assert r.status_code == 200
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Programme", "Gantt"] and wb["Programme"].max_row == 1 + len(floors)
    # the export imports back onto the same cells
    rows = client.post(f"/api/v1/records/{rid}/programme/import", headers=s["hqa"], files={"file": ("x.xlsx", r.content)}).json()
    assert {(x["stage_id"], x["location_id"], x["start"]) for x in rows} == {(x["stage_id"], x["location_id"], x["start"]) for x in lines}
    pdf = client.get(f"/api/v1/records/{rid}/pdf?lang=ar", headers=s["hqa"])
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
