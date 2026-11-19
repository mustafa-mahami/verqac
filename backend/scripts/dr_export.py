#!/usr/bin/env python3
"""Export one project (or several) from the Odoo `dr` module (Project Quality / QA-QC KPIs) for Verqac.

Runs anywhere with Python 3.8+ and no extra packages: it talks to Odoo over XML-RPC.
The password (better: an Odoo API key, from Preferences > Account Security) is asked when it runs
and is never written to disk.

    python3 dr_export.py --url https://erp.example.com --db mydb --user me@example.com
        lists the projects with how many records each one has, then stops
    python3 dr_export.py --url ... --db ... --user ... --project 12
        writes dr_export_<project>.zip: data.json + the attachments (PDFs, photos)
    add --no-files to leave the attachments out (a quick first run to check the data)

Nothing in Odoo is changed: the script only reads.
"""
import argparse
import base64
import getpass
import json
import sys
import xmlrpc.client
import zipfile
from datetime import datetime

# model -> how its rows belong to the project: "project" (project_id) or (parent model, link field)
MODELS = [
    ("submit.submit", "project"),
    ("inspection.inspection", "project"),
    ("rfi.rfi", "project"),
    ("quality.quality", "project"),
    ("dr.test.result.line", ("quality.quality", "test_id")),
    ("site.instruction", "project"),
    ("site.instruction.line", ("site.instruction", "instruction_id")),
    ("documents.documents", "project"),
    ("dr.dr", "project"),
    ("teamc.teamc", ("dr.dr", "teamc_id")),
    ("teams.teams", ("dr.dr", "teams_id")),
    ("subcont.subcont", ("dr.dr", "subcont_id")),
    ("materials.materials", ("dr.dr", "mater_id")),
    ("equip.equip", ("dr.dr", "equip_id")),
    ("work.work", ("dr.dr", "work_id")),
    ("worknd.worknd", ("dr.dr", "work_id")),
    ("dr.schedule.stage", "project"),
    ("dr.schedule.location", "project"),
    ("dr.schedule.cell", "project"),
    ("dr.schedule.snapshot", "project"),
    ("dr.schedule.rule", "project"),
    ("dr.qa.kpi.target", "kpi"),
    ("dr.concrete.class", "any"),
    ("dr.material.type", "any"),
]
# record models whose attachments (PDF / photos) go with them
FILE_MODELS = ["submit.submit", "inspection.inspection", "rfi.rfi", "quality.quality", "site.instruction",
               "documents.documents", "dr.dr"]
SKIP_TYPES = {"binary", "one2many", "html_binary"}
SKIP_FIELDS = {"message_ids", "message_follower_ids", "activity_ids", "website_message_ids", "message_main_attachment_id",
               "__last_update", "display_name"}
BATCH = 200


class Odoo:
    def __init__(self, url, db, user, password):
        self.url, self.db = url.rstrip("/"), db
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
        self.version = common.version().get("server_version", "?")
        self.uid = common.authenticate(db, user, password, {})
        if not self.uid:
            sys.exit("Login failed: check the database name, the user and the password / API key.")
        self.pw = password
        self.obj = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)

    def call(self, model, method, *args, **kw):
        return self.obj.execute_kw(self.db, self.uid, self.pw, model, method, list(args), kw)

    def has_model(self, model):
        return bool(self.call("ir.model", "search", [("model", "=", model)]))

    def fields(self, model):
        info = self.call(model, "fields_get", attributes=["type", "store", "relation", "selection", "string"])
        keep = {k: v for k, v in info.items()
                if v.get("store", True) and v["type"] not in SKIP_TYPES and k not in SKIP_FIELDS}
        return keep, info

    def read_all(self, model, domain, fields):
        ids = self.call(model, "search", domain, order="id")
        rows = []
        for i in range(0, len(ids), BATCH):
            rows += self.call(model, "read", ids[i:i + BATCH], fields=fields)
        return rows


def list_projects(o):
    projects = o.call("project.project", "search_read", [], fields=["id", "name"], order="name", context={"active_test": False})
    print(f"\n{'id':>6}  {'submittals':>10} {'inspections':>11} {'daily':>6}  project")
    for p in projects:
        n = {m: o.call(m, "search_count", [("project_id", "=", p["id"])]) for m in ("submit.submit", "inspection.inspection", "dr.dr")}
        if any(n.values()):
            print(f"{p['id']:>6}  {n['submit.submit']:>10} {n['inspection.inspection']:>11} {n['dr.dr']:>6}  {p['name']}")
    print("\nRun again with --project <id> (several: --project 12,15).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True, help="Odoo address, e.g. https://erp.magcc.ps")
    ap.add_argument("--db", required=True, help="Odoo database name")
    ap.add_argument("--user", required=True, help="Odoo login (e-mail)")
    ap.add_argument("--project", help="project id(s), comma separated; leave out to list the projects")
    ap.add_argument("--no-files", action="store_true", help="leave the attachments out")
    ap.add_argument("--out", help="output file (default dr_export_<project>.zip)")
    a = ap.parse_args()
    o = Odoo(a.url, a.db, a.user, getpass.getpass("Odoo password or API key (not shown): "))
    print(f"Connected to Odoo {o.version}, database {a.db}.")
    if not a.project:
        list_projects(o)
        return
    pids = [int(x) for x in a.project.split(",")]
    projects = o.call("project.project", "read", pids)
    data = {"meta": {"exported_at": datetime.now().isoformat(timespec="seconds"), "odoo": o.version, "db": a.db,
                     "url": a.url, "projects": pids, "format": 1},
            "projects": projects, "models": {}, "fields": {}, "users": [], "attachments": []}
    mods = o.call("ir.module.module", "search_read", [("name", "=", "dr")], fields=["latest_version", "installed_version"])
    data["meta"]["dr_version"] = mods[0].get("installed_version") or mods[0].get("latest_version") if mods else None
    ids_of = {}
    users = set()
    for model, scope in MODELS:
        if not o.has_model(model):
            print(f"  {model:28} not in this database, skipped")
            continue
        keep, info = o.fields(model)
        if scope == "project":
            domain = [("project_id", "in", pids)]
        elif scope == "kpi":
            domain = ["|", ("project_id", "in", pids), ("project_id", "=", False)] if "project_id" in info else []
        elif scope == "any":
            domain = []
        else:
            parent, link = scope
            domain = [(link, "in", ids_of.get(parent, []))]
        if "active" in info:
            domain = ["|", ("active", "=", True), ("active", "=", False)] + domain
        rows = o.read_all(model, domain, list(keep))
        ids_of[model] = [r["id"] for r in rows]
        data["models"][model] = rows
        data["fields"][model] = {k: {x: v.get(x) for x in ("type", "relation", "selection", "string")} for k, v in keep.items()}
        for k, v in keep.items():
            if v.get("relation") == "res.users":
                for r in rows:
                    x = r.get(k)
                    if isinstance(x, list) and x and isinstance(x[0], int):
                        users.add(x[0])
        print(f"  {model:28} {len(rows):>6}")
    if users:
        data["users"] = o.call("res.users", "read", sorted(users), fields=["id", "name", "login", "email", "active"],
                               context={"active_test": False})
    # attachments of the records (chatter files and the PDF fields stored as attachments)
    total = 0
    for model in FILE_MODELS:
        ids = ids_of.get(model) or []
        for i in range(0, len(ids), 500):
            rows = o.call("ir.attachment", "search_read",
                          [("res_model", "=", model), ("res_id", "in", ids[i:i + 500]), "|", ("res_field", "=", False), ("res_field", "!=", False)],
                          fields=["id", "name", "mimetype", "file_size", "res_model", "res_id", "res_field", "create_date", "create_uid"])
            data["attachments"] += rows
            total += sum(r.get("file_size") or 0 for r in rows)
    print(f"  attachments: {len(data['attachments'])} files, {total / 1048576:.1f} MB")
    out = a.out or f"dr_export_{'_'.join(map(str, pids))}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        if not a.no_files:
            for n, att in enumerate(data["attachments"], 1):
                got = o.call("ir.attachment", "read", [att["id"]], fields=["datas"])
                raw = base64.b64decode(got[0]["datas"]) if got and got[0].get("datas") else b""
                att["path"] = f"files/{att['id']}" if raw else None
                if raw:
                    z.writestr(att["path"], raw)
                if n % 50 == 0:
                    print(f"  downloaded {n} / {len(data['attachments'])}")
        z.writestr("data.json", json.dumps(data, ensure_ascii=False, default=str))
    print(f"\nDone: {out}")


if __name__ == "__main__":
    main()
