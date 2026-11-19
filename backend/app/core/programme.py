"""Planned progress from the time programme, and reading programmes from Excel, MS Project and Primavera P6.

A cell (stage x location, or the stage alone when it covers the whole project) is planned linearly between its
start and finish: half its days = 50 %. Stage and project % are weighted exactly like the actual progress.
"""
import csv
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

LATE_MARGIN = 10.0  # % points behind plan before a cell counts as late
AHEAD_MARGIN = 5.0


def _d(v, mdy: bool = False) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    if not s:
        return None
    # ISO first (2026-12-01, 2026-12-01T08:00:00), then day-first and month-first forms, then free text
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        return date(int(m[1]), int(m[2]), int(m[3]))
    s = re.sub(r"^[A-Za-z؀-ۿ]{2,}\.?\s+", "", s)  # "Mon 12/1/26", "الاثنين 1/12/2026"
    s = re.sub(r"\s+\d{1,2}:\d{2}.*$", "", s)  # time of day
    s = s.rstrip("*AaPp ")
    numeric = ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y") if mdy else ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y")
    for fmt in (*numeric, "%d.%m.%Y", "%d-%b-%y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def cell_planned(start: date, finish: date, day: date) -> float:
    if day < start:
        return 0.0
    if day >= finish:
        return 100.0
    return round(((day - start).days + 1) / ((finish - start).days + 1) * 100, 1)


def plan_cells(lines: list[dict]) -> dict[tuple[str, str | None], tuple[date, date]]:
    out: dict = {}
    for x in lines or []:
        s, f = _d(x.get("start")), _d(x.get("finish"))
        if not x.get("stage_id") or s is None or f is None:
            continue
        key = (str(x["stage_id"]), str(x["location_id"]) if x.get("location_id") else None)
        if key in out:  # several lines on one cell: the earliest start and the latest finish
            s, f = min(s, out[key][0]), max(f, out[key][1])
        out[key] = (s, max(s, f))
    return out


def planned_at(cells: dict, stages: list, units: list, day: date) -> tuple[float, dict[str, float]]:
    """Project % and stage % planned on that day (same weighting as the actual progress)."""
    total_w = sum(float(s.weight) for s in stages) or 0
    project, per_stage = 0.0, {}
    for s in stages:
        sid = str(s.id)
        from app.models.structure import stage_units
        su = stage_units(s, units)
        if s.scope == "whole" or not su:
            c = cells.get((sid, None))
            pct = cell_planned(*c, day) if c else 0.0
        else:
            vals = [cell_planned(*cells[(sid, str(u.id))], day) if (sid, str(u.id)) in cells else 0.0 for u in su]
            pct = sum(vals) / len(vals)
        per_stage[sid] = round(pct, 1)
        if total_w:
            project += float(s.weight) * pct / total_w
    return round(project, 1), per_stage


def series(cells: dict, stages: list, units: list, until: date | None = None) -> list[dict]:
    """Planned project % week by week from the first start to the last finish."""
    if not cells:
        return []
    first = min(s for s, _ in cells.values())
    last = max(f for _, f in cells.values())
    if until:
        last = max(last, until)
    out, d = [], first
    while d < last:
        out.append({"day": d.isoformat(), "planned": planned_at(cells, stages, units, d)[0]})
        d += timedelta(days=7)
    out.append({"day": last.isoformat(), "planned": planned_at(cells, stages, units, last)[0]})
    return out


def status(planned: float, actual: float) -> str:
    if actual >= 100:
        return "done"
    if planned <= 0 and actual <= 0:
        return "not_started"
    if actual + LATE_MARGIN < planned:
        return "late"
    if actual > planned + AHEAD_MARGIN:
        return "ahead"
    return "on_track"


# ----------------------------------------------------------------------------- reading files
NAME_H = ("stage", "المرحلة", "task name", "name", "activity name", "activity", "اسم المهمة", "المهمة", "النشاط", "اسم النشاط", "task")
LOC_H = ("location", "الموقع", "floor", "الطابق")
WBS_H = ("wbs name", "wbs", "summary", "outline", "path")
LEVEL_H = ("outline level", "level", "المستوى")
START_H = ("start", "البداية", "start date", "planned start", "early start", "baseline start", "تاريخ البداية", "بداية")
FINISH_H = ("finish", "النهاية", "finish date", "end", "end date", "planned finish", "early finish", "baseline finish",
            "تاريخ النهاية", "نهاية")


def _h(v) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip().lower().replace("(*)", "").replace("*", "")).strip()


def _pick(headers: list[str], names: tuple) -> int | None:
    for n in names:  # exact first, in order of preference
        if n in headers:
            return headers.index(n)
    for i, h in enumerate(headers):
        if any(h.startswith(n) for n in names if len(n) > 3):
            return i
    return None


def _month_first(values) -> bool:
    """Written dates like 12/1/26: month first only when a second number above 12 says so (US exports)."""
    mdy = False
    for v in values:
        m = re.search(r"(\d{1,2})[/-](\d{1,2})[/-]\d{2,4}", str(v or "")) if not isinstance(v, (date, datetime)) else None
        if m:
            if int(m[1]) > 12:
                return False
            if int(m[2]) > 12:
                mdy = True
    return mdy


def _from_table(rows: list[list]) -> list[dict]:
    """Rows of a sheet: find the header row (it has a name and a start column), read the tasks under it."""
    for hi, row in enumerate(rows[:30]):
        hs = [_h(v) for v in row]
        name, start, finish = _pick(hs, NAME_H), _pick(hs, START_H), _pick(hs, FINISH_H)
        if name is None or start is None or finish is None:
            continue
        loc, wbs, lvl = _pick(hs, LOC_H), _pick(hs, WBS_H), _pick(hs, LEVEL_H)
        mdy = _month_first([r[i] for r in rows[hi + 1:] for i in (start, finish) if i < len(r)])
        out, stack = [], []
        for r in rows[hi + 1:]:
            get = (lambda i: r[i] if i is not None and i < len(r) else None)  # noqa: E731
            n = str(get(name) or "").strip()
            if not n:
                continue
            raw = str(r[name]) if name < len(r) and r[name] is not None else ""
            level = None
            if lvl is not None:
                try:
                    level = int(float(get(lvl)))
                except (TypeError, ValueError):
                    level = None
            elif raw[:1] == " ":  # MS Project exports indent names
                level = (len(raw) - len(raw.lstrip(" "))) // 3 + 1
            path = []
            if level is not None:
                stack[level - 1:] = [n]
                path = stack[:-1]
            if wbs is not None and get(wbs):
                path = [*path, str(get(wbs)).strip()]
            s, f = _d(get(start), mdy), _d(get(finish), mdy)
            out.append({"name": n, "location": str(get(loc) or "").strip() or None, "path": path,
                        "start": s.isoformat() if s else None, "finish": f.isoformat() if f else None})
        return out
    return []


def _xlsx(data: bytes) -> list[dict]:
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        out = _from_table(rows)
        if out:
            return out
    return []


def _csv(data: bytes) -> list[dict]:
    text = data.decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t") if text.strip() else csv.excel
    return _from_table([list(r) for r in csv.reader(io.StringIO(text), dialect)])


def _msp_xml(data: bytes) -> list[dict]:
    root = ET.fromstring(data)
    ns = {"p": root.tag.split("}")[0].strip("{")} if root.tag.startswith("{") else {}
    q = (lambda t: f"p:{t}" if ns else t)  # noqa: E731
    out, stack = [], []
    for t in root.iter(f"{{{ns['p']}}}Task" if ns else "Task"):
        name = (t.findtext(q("Name"), namespaces=ns) or "").strip()
        lvl = int(t.findtext(q("OutlineLevel"), default="0", namespaces=ns) or 0)
        if not name or lvl == 0:
            continue
        stack[lvl - 1:] = [name]
        if t.findtext(q("Summary"), default="0", namespaces=ns) == "1":
            continue
        s, f = _d(t.findtext(q("Start"), namespaces=ns)), _d(t.findtext(q("Finish"), namespaces=ns))
        out.append({"name": name, "location": None, "path": stack[:-1],
                    "start": s.isoformat() if s else None, "finish": f.isoformat() if f else None})
    return out


def _xer(data: bytes) -> list[dict]:
    text = data.decode("utf-8", errors="replace") if b"\x00" not in data[:200] else data.decode("utf-16", errors="replace")
    tables: dict[str, list[dict]] = {}
    cur, fields = None, []
    for line in text.splitlines():
        parts = line.split("\t")
        if parts[0] == "%T":
            cur, fields = parts[1].strip(), []
            tables[cur] = []
        elif parts[0] == "%F":
            fields = [x.strip() for x in parts[1:]]
        elif parts[0] == "%R" and cur:
            tables[cur].append(dict(zip(fields, parts[1:])))
    wbs = {w.get("wbs_id"): w for w in tables.get("PROJWBS", [])}

    def path(wid):
        out = []
        while wid in wbs and len(out) < 20:
            w = wbs[wid]
            if w.get("proj_node_flag") == "Y":
                break
            out.insert(0, w.get("wbs_name", ""))
            wid = w.get("parent_wbs_id")
        return out

    out = []
    for t in tables.get("TASK", []):
        s = _d(t.get("target_start_date") or t.get("early_start_date") or t.get("act_start_date"))
        f = _d(t.get("target_end_date") or t.get("early_end_date") or t.get("act_end_date"))
        out.append({"name": (t.get("task_name") or "").strip(), "location": None, "path": path(t.get("wbs_id")),
                    "start": s.isoformat() if s else None, "finish": f.isoformat() if f else None})
    return [x for x in out if x["name"]]


def read_file(filename: str, data: bytes) -> list[dict]:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext in ("xlsx", "xlsm"):
        return _xlsx(data)
    if ext in ("csv", "txt"):
        return _csv(data)
    if ext == "xml":
        return _msp_xml(data)
    if ext == "xer":
        return _xer(data)
    raise ValueError("programme_file_type")


# ----------------------------------------------------------------------------- matching names
_AR = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": ""})
_ORD = {"اول": "1", "first": "1", "1st": "1", "ثاني": "2", "second": "2", "2nd": "2", "ثالث": "3", "third": "3", "3rd": "3",
        "رابع": "4", "fourth": "4", "4th": "4", "خامس": "5", "fifth": "5", "5th": "5", "سادس": "6", "sixth": "6", "6th": "6",
        "سابع": "7", "seventh": "7", "ثامن": "8", "eighth": "8", "تاسع": "9", "ninth": "9", "عاشر": "10", "tenth": "10"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower().translate(_AR)
    s = re.sub(r"[ً-ٟ]", "", s)  # harakat
    s = re.sub(r"[^\w\s]", " ", s)
    words = [w[2:] if w.startswith("ال") and len(w) > 3 else w for w in s.split()]
    return " " + " ".join(_ORD.get(w, w) for w in words) + " "


def _best(text: str, names: list[tuple[str, object]]):
    """The candidate whose (normalised) name appears in the text, the longest one winning."""
    best, size = None, 0
    for n, obj in names:
        k = norm(n)
        if len(k.strip()) >= 2 and k in text and len(k) > size:
            best, size = obj, len(k)
    return best


def match(rows: list[dict], stages: list, topics: list, units: list) -> list[dict]:
    st_names = [(n, s) for s in stages for n in (s.name_ar, s.name_en)]
    tp_names = [(n, t) for t in topics for n in (t.name_ar, t.name_en)]
    by_stage = {s.id: s for s in stages}
    loc_names = [(n, u) for u in units for n in (u.name_ar, u.name_en)]
    out = []
    for r in rows:
        text = norm(" ".join([*(r.get("path") or []), r.get("name") or ""]))
        st = _best(text, st_names)
        if st is None:
            tp = _best(text, tp_names)
            st = by_stage.get(tp.stage_id) if tp is not None else None
        loc = None
        if st is not None and st.scope != "whole":
            loc = _best(norm(r["location"]) if r.get("location") else text, loc_names)
        out.append({**r, "stage_id": str(st.id) if st else None, "location_id": str(loc.id) if loc else None})
    return out


# ----------------------------------------------------------------------------- critical path (same network as the UI)
def total_float(lines: list[dict], cycles: list[dict], units: list[str], whole: set[str]) -> dict[tuple, int]:
    """Total float in days of every cell ((stage, location | None) -> days); 0 or less = critical."""
    cells = plan_cells(lines)
    if not cells or not cycles:
        return {}
    nodes = {k: {"s": s.toordinal(), "f": f.toordinal()} for k, (s, f) in cells.items()}

    def cells_of(stage):
        keys = [(stage, None)] if stage in whole else [(stage, u) for u in units]
        return [k for k in keys if k in nodes]

    edges = []
    for c in cycles:
        sid = str(c["stage_id"])
        mine = cells_of(sid)
        fs = (c.get("link") or "fs") == "fs"
        if sid not in whole:
            for a, b in zip(mine, mine[1:]):
                edges.append((a, b, "F" if fs else "S", (c.get("lag") or 0) + 1 if fs else (c.get("lag") or 0)))
        pred = str(c["pred"]) if c.get("pred") else None
        if not pred:
            continue
        d, rel = c.get("pred_days") or 0, c.get("rel") or "after_end"
        on = "F" if rel.endswith("end") else "S"
        k = d + 1 if rel == "after_end" else d if rel == "after_start" else -d
        theirs = cells_of(pred)
        if not theirs or not mine:
            continue
        if sid not in whole and pred not in whole:
            for u in units:
                if (pred, u) in nodes and (sid, u) in nodes:
                    edges.append(((pred, u), (sid, u), on, k))
        elif sid not in whole:
            edges.append((theirs[0], mine[0], on, k))
        else:
            pick = max(theirs, key=lambda x: nodes[x]["f"]) if on == "F" else min(theirs, key=lambda x: nodes[x]["s"])
            edges.append((pick, mine[0], on, k))
    end = max(n["f"] for n in nodes.values())
    lf = {k: end for k in nodes}
    for _ in range(500):
        changed = False
        for p, s, on, k in edges:
            ls = lf[s] - (nodes[s]["f"] - nodes[s]["s"])
            v = ls - k if on == "F" else ls - k + (nodes[p]["f"] - nodes[p]["s"])
            if v < lf[p]:
                lf[p], changed = v, True
        if not changed:
            break
    return {k: lf[k] - nodes[k]["f"] for k in nodes}
