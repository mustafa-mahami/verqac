"""Import a project exported from the Odoo `dr` module (scripts/dr_export.py) into a Verqac project.

    python -m app.scripts.import_dr dr_export_50.zip --project AAUP --as ceo@example.com
        a trial run: everything is written inside one transaction, checked, reported, then rolled back
    python -m app.scripts.import_dr /data/files/odoo-import/50 --attachments --project AAUP --as ceo@example.com [--commit]
        the attachments only (a folder made by dr_export.py --files-dir, on the files volume): each file is moved
        into the platform's storage and attached to its record; running it again adds only what is missing
    ... --commit
        the real import (back up the database first)

The Verqac project is replaced: its records, daily reports, programme, progress and structure are deleted,
then its stages and floors are rebuilt from the Odoo schedule and everything is imported. People of the Odoo
records become inactive placeholder accounts (no login) so every record keeps who submitted and answered it.
Re-running replaces again, so a corrected export can simply be imported once more.
"""
import argparse
import json
import re
import sys
import uuid
import zipfile
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update

TZ = ZoneInfo("Asia/Hebron")
CHANNEL = "import"
PLACEHOLDER_HASH = "!"  # not a valid argon2 hash: nobody can log in with it
APPROVED_DR = {"submitted", "signed"}  # old daily reports: count as approved (decided with the user)

# ----------------------------------------------------------------------------- vocabulary
DISC = {"civil": "C", "electrical": "E", "mechanical": "M", "plumbing": "P", "general": "G", "safety": "G"}
REVIEW = {"approved": "approved", "approved_as_noted": "approved_as_noted", "revise_and_resubmit": "revise_and_resubmit",
          "rejected": "rejected", "cancelled": "cancelled", "submitted": "submitted", "draft": "draft"}
INSPECTION = {"approved": "accepted", "approved_as_noted": "accepted_with_comments", "revise_and_resubmit": "rejected",
              "rejected": "rejected", "cancelled": "cancelled", "submitted": "submitted", "draft": "draft"}
KINDS = {"shop drawings": "shop_drawing", "material": "material", "general": "document"}
WEATHER = {"sunny": "sunny", "clear": "sunny", "cloudy": "cloudy", "hot": "hot", "very hot": "hot", "rainy": "rain",
           "partial rain": "rain", "cold": "cold", "storm": "storm", "fog": "fog", "dust": "dust", "snow": "snow"}
WIND = {"no wind": "calm", "light wind": "calm", "fair": "calm", "windy": "moderate", "windly": "moderate",
        "strong wind": "strong"}
STAGES_AR = {
    "structure": "الهيكل الإنشائي", "block walls": "الطوب", "mep first fix": "التمديدات الكهروميكانيكية الأولى",
    "plaster": "القصارة", "insulation": "العزل", "tiles": "البلاط", "false ceiling / gypsum": "الأسقف المستعارة / الجبس",
    "aluminum & steel works": "أعمال الألمنيوم والحديد", "doors": "الأبواب", "paint": "الدهان",
    "mep second / final fix": "التشطيبات الكهروميكانيكية النهائية", "facade stone cladding": "تكسية الحجر للواجهات",
    "curtain wall & alucobond": "الواجهات الزجاجية والألوكوبوند", "elevator": "المصاعد",
    "site & external works": "الموقع والأعمال الخارجية",
    "fit-out (counters, partitions, joinery)": "التجهيزات الداخلية (كاونترات، قواطع، نجارة)",
    "staircases (finishes)": "تشطيبات الأدراج"}
ORDINAL = ["", "الأول", "الثاني", "الثالث", "الرابع", "الخامس", "السادس", "السابع", "الثامن", "التاسع", "العاشر",
           "الحادي عشر", "الثاني عشر", "الثالث عشر", "الرابع عشر", "الخامس عشر", "السادس عشر", "السابع عشر",
           "الثامن عشر", "التاسع عشر", "العشرون"]


def floor_ar(name: str) -> str:
    n = name.strip().lower()
    if m := re.fullmatch(r"floor\s*(\d+)", n):
        k = int(m.group(1))
        return f"الطابق {ORDINAL[k]}" if k < len(ORDINAL) else f"الطابق {k}"
    if m := re.fullmatch(r"basement\s*(\d*)", n):
        fem = {1: "الأولى", 2: "الثانية", 3: "الثالثة", 4: "الرابعة", 5: "الخامسة"}
        return f"التسوية {fem.get(int(m.group(1)), m.group(1))}" if m.group(1) else "التسوية"
    return {"ground floor": "الطابق الأرضي", "roof": "السطح", "foundations": "الأساسات",
            "foundation": "الأساسات"}.get(n, name.strip())


# ----------------------------------------------------------------------------- helpers
def m2o(v):
    return v if isinstance(v, list) and v else None


def m2o_id(v):
    return v[0] if isinstance(v, list) and v else None


def m2o_name(v) -> str | None:
    return str(v[1]).strip() if isinstance(v, list) and len(v) > 1 and v[1] else None


def txt(v, n: int | None = None) -> str | None:
    """Text, or None for empty / filler ('.....', '-----')."""
    if v in (None, False):
        return None
    s = str(v).strip()
    if s.startswith("<"):  # html
        s = re.sub(r"<br\s*/?>|</p>", "\n", s)
        s = re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ").replace("&amp;", "&").strip()
    if not s or not re.search(r"[\w؀-ۿ]", s):
        return None
    return s[:n] if n else s


def d(v) -> date | None:
    return date.fromisoformat(v[:10]) if v else None


def clock(v) -> time | None:
    """'10:00', '9:00 am', '1:00pm', '11:30AM' -> time; anything else None."""
    s = str(v or "").strip().lower().replace(".", ":")
    m = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", s)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3) == "pm" and h < 12:
        h += 12
    if m.group(3) == "am" and h == 12:
        h = 0
    if m.group(3) is None and 1 <= h <= 6:  # '1:00' on a site means the afternoon
        h += 12
    return time(h, mi) if h < 24 and mi < 60 else None


def at(day: date | None, t: time | None = None, default: time = time(10, 0)) -> datetime | None:
    return datetime.combine(day, t or default, TZ) if day else None


def true_day(r: dict, day: date | None, answered: date | None) -> date | None:
    """The submission day, unless Odoo's date was edited afterwards: a request never answered whose date is days
    after the record was created, or an answer older than the date, was submitted on the day it was created."""
    made = d(r.get("create_date"))
    if day is None or made is None or (day - made).days <= 3:
        return day
    if answered is None and r.get("status") in ("submitted", None):
        return made
    if answered is not None and answered < day:
        return min(made, answered)
    return day


def num(v) -> float | None:
    if v in (None, False, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    return float(m.group(0).replace(",", ".")) if m else None


def rev_of(v) -> int:
    m = re.search(r"\d+", str(v or "0"))
    return int(m.group(0)) if m else 0


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")[:30] or "kind"


# ----------------------------------------------------------------------------- the import
class TrialRun(Exception):
    """Raised at the end of a trial run so the whole transaction rolls back."""


class Importer:
    def __init__(self, db, data: dict, project, actor, log):
        self.db, self.data, self.p, self.actor, self.log = db, data, project, actor, log
        self.M = data["models"]
        self.report: Counter = Counter()
        self.warnings: list[str] = []
        self.users: dict = {}  # odoo key -> verqac user id
        self.disc: dict = {}

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    # ---- the project as it is
    def setup(self):
        from app.models.core import Discipline, ProjectParty
        from app.models.records import RecordType, Workflow, WorkflowState
        db = self.db
        parties = {x.kind: x for x in db.scalars(select(ProjectParty).where(ProjectParty.project_id == self.p.id,
                                                                            ProjectParty.status != "removed"))}
        if "contractor" not in parties or "consultant" not in parties:
            sys.exit("The Verqac project needs its contractor and consultant parties.")
        self.contractor, self.consultant = parties["contractor"], parties["consultant"]
        self.disc = {x.code: x.id for x in db.scalars(select(Discipline).where(Discipline.org_id == self.p.owner_org_id))}
        self.kdisc = {x.code: x.id for x in db.scalars(select(Discipline).where(Discipline.org_id == self.consultant.org_id))} \
            if self.consultant.org_id else {}
        self.types = {t.code: t for t in db.scalars(select(RecordType).where(RecordType.org_id.is_(None)))}
        self.states = {}
        for code, rt in self.types.items():
            wf = db.get(Workflow, rt.workflow_id)
            self.states[code] = {s.code: s for s in db.scalars(select(WorkflowState).where(WorkflowState.workflow_id == wf.id))}

    def existing(self) -> dict:
        from app.models.daily import DailyReport
        from app.models.records import Record, RecordType
        from app.models.structure import ProjectLocation, ProjectStage
        db = self.db
        rows = db.execute(select(RecordType.code, func.count()).join(Record, Record.record_type_id == RecordType.id)
                          .where(Record.project_id == self.p.id).group_by(RecordType.code)).all()
        return {"records": dict(rows),
                "daily_reports": db.scalar(select(func.count()).select_from(DailyReport).where(DailyReport.project_id == self.p.id)),
                "stages": db.scalar(select(func.count()).select_from(ProjectStage).where(ProjectStage.project_id == self.p.id)),
                "locations": db.scalar(select(func.count()).select_from(ProjectLocation).where(ProjectLocation.project_id == self.p.id))}

    def wipe(self):
        from app.models.daily import ProgressCell, ProgressSnapshot
        from app.models.lab import ConcreteClass
        from app.models.records import Record
        from app.models.structure import ProjectLocation, ProjectStage, ProjectStageTopic
        db, pid = self.db, self.p.id
        db.execute(delete(Record).where(Record.project_id == pid))  # details, events, comments, daily, lab, programme follow
        if db.scalar(select(func.count()).select_from(Record).where(Record.project_id == pid)):
            sys.exit("The project's records could not be deleted (database migration 0023 missing?). Nothing was changed.")
        db.execute(delete(ProgressCell).where(ProgressCell.project_id == pid))
        db.execute(delete(ProgressSnapshot).where(ProgressSnapshot.project_id == pid))
        db.execute(delete(ConcreteClass).where(ConcreteClass.project_id == pid))
        db.execute(delete(ProjectStageTopic).where(ProjectStageTopic.project_id == pid))
        db.execute(delete(ProjectStage).where(ProjectStage.project_id == pid))
        db.execute(delete(ProjectLocation).where(ProjectLocation.project_id == pid, ProjectLocation.parent_id.is_not(None)))
        db.execute(delete(ProjectLocation).where(ProjectLocation.project_id == pid))
        db.flush()

    # ---- structure: the Odoo schedule's stages and floors
    def structure(self):
        from app.models.structure import ProjectLocation, ProjectStage
        db = self.db
        self.stage = {}  # odoo stage id -> verqac stage
        stages = sorted(self.M.get("dr.schedule.stage", []), key=lambda r: (r.get("sequence") or 0, r["id"]))
        for i, r in enumerate(stages):
            en = r["name"].strip()
            s = ProjectStage(id=uuid.uuid4(), project_id=self.p.id, name_en=en, name_ar=STAGES_AR.get(en.lower(), en),
                             scope="whole" if r.get("scope") == "building" else "per_location",
                             weight=Decimal(str(round(r.get("weight") or 0, 2))), sort=(i + 1) * 10,
                             is_active=bool(r.get("active", True)))
            db.add(s)
            self.stage[r["id"]] = s
        total = sum(float(s.weight) for s in self.stage.values() if s.is_active)
        if abs(total - 100) > 0.01:
            self.warn(f"stage weights add up to {total:g}, not 100")
        group = ProjectLocation(id=uuid.uuid4(), project_id=self.p.id, kind="group", name_ar="المبنى", name_en="Building", sort=10)
        db.add(group)
        db.flush()
        self.loc = {}  # odoo location id -> verqac unit
        self.floorx = {}  # odoo daily-report floor name id -> verqac unit
        locs = sorted([r for r in self.M.get("dr.schedule.location", []) if r.get("active", True)],
                      key=lambda r: (r.get("level") or 0, r.get("sequence") or 0))
        for i, r in enumerate(locs):
            u = ProjectLocation(id=uuid.uuid4(), project_id=self.p.id, parent_id=group.id, kind="unit",
                                name_ar=floor_ar(r["name"]), name_en=r["name"].strip(), sort=(i + 1) * 10)
            db.add(u)
            self.loc[r["id"]] = u
            for fx in r.get("floorx_ids") or []:
                self.floorx[fx] = u
        # the floors each stage applies to: the Odoo schedule has a cell only where it applies
        where = defaultdict(set)
        for c in self.M.get("dr.schedule.cell", []):
            u = self.loc.get(m2o_id(c.get("location_id")))
            if u is not None:
                where[m2o_id(c.get("stage_id"))].add(u.id)
        for sid, st in self.stage.items():
            if st.scope == "per_location" and where.get(sid) and len(where[sid]) < len(self.loc):
                st.location_ids = sorted(where[sid], key=lambda x: next(u.sort for u in self.loc.values() if u.id == x))
                self.report["stages limited to some floors"] += 1
        db.flush()
        # inspections: the daily-report action / work type -> stage rules
        self.rules = []
        for r in self.M.get("dr.schedule.rule", []):
            st = self.stage.get(m2o_id(r.get("stage_id")))
            if st is not None:
                self.rules.append((m2o_id(r.get("action_id")), m2o_id(r.get("workx_id")), st))
        self.report["stages"] = len(self.stage)
        self.report["floors"] = len(self.loc)

    def stage_for(self, action_id, work_id):
        best = None
        for a, w, st in self.rules:
            if a and w and a == action_id and w == work_id:
                return st
            if (a and not w and a == action_id) or (w and not a and w == work_id):
                best = best or st
        return best

    # ---- people
    def people(self):
        """Odoo users and partners -> inactive placeholder members of the party they acted for."""
        from app.models.core import ProjectMember, Role, User
        db = self.db
        roles = {r.code: r.id for r in db.scalars(select(Role).where(Role.org_id.is_(None), Role.project_id.is_(None)))}
        side: dict = defaultdict(Counter)  # key -> party votes
        names: dict = {}
        discs: dict = defaultdict(set)

        def vote(v, party, cat=None):
            if not m2o(v):
                return
            key = ("u", v[0])
            side[key][party] += 1
            names[key] = m2o_name(v)
            if cat:
                discs[key].add(DISC.get(cat, "G"))

        # "Submitted to" is the supervision engineer who answers; "Recv Answer By" is the contractor's
        # employee who received the answer, so it is not used
        for m, by, to in (("submit.submit", "submitby", ("submitto",)),
                          ("inspection.inspection", "inspectionsubmitby", ("inspectionsubmitto",)),
                          ("rfi.rfi", "rfisubmitby", ("rfisubmitto",)),
                          ("quality.quality", "submitby", ("submitto",)),
                          ("dr.dr", "submitby", ("submitto",))):
            for r in self.M.get(m, []):
                vote(r.get(by), "contractor", r.get("category"))
                for f in to:
                    vote(r.get(f), "consultant", r.get("category"))
        for r in self.M.get("site.instruction", []):  # partners: the consultant issues, the contractor answers
            for f, party in (("submit_from", "consultant"), ("submit_to", "contractor")):
                if m2o(r.get(f)):
                    key = ("p", r[f][0])
                    side[key][party] += 1
                    names[key] = m2o_name(r[f])
                    discs[key].add(DISC.get(r.get("category"), "G"))
        logins = {u["id"]: u for u in self.data.get("users", [])}
        me = {i for i, u in logins.items() if (u.get("login") or "").lower() in ("__system__", "musleh", "admin")}
        made = 0
        for key, votes in side.items():
            if key[0] == "u" and key[1] in me:
                self.users[key] = self.actor.id
                continue
            party = votes.most_common(1)[0][0]
            login = (logins.get(key[1], {}).get("login") or "") if key[0] == "u" else ""
            place = f"odoo-{slug(self.data['meta'].get('db') or 'db')}-{key[0]}{key[1]}@import.verqac.invalid"
            existing = db.scalar(select(User).where(func.lower(User.email) == login.lower())) if "@" in login else None
            existing = existing or db.scalar(select(User).where(User.email == place))  # an earlier import
            if existing is not None:
                uid = existing.id
            else:
                name = names.get(key) or "?"
                u = User(id=uuid.uuid4(), email=place, password_hash=PLACEHOLDER_HASH,
                         full_name_ar=name[:200], full_name_en=name[:200], is_active=False)
                db.add(u)
                db.flush()
                uid = u.id
                made += 1
            self.users[key] = uid
            pt = self.contractor if party == "contractor" else self.consultant
            dmap = self.disc if party == "contractor" else self.kdisc
            role = roles["qa_engineer" if party == "contractor" else "consultant_engineer"]
            ds = [dmap[c] for c in sorted(discs[key]) if c in dmap]
            m = db.scalar(select(ProjectMember).where(ProjectMember.project_id == self.p.id, ProjectMember.user_id == uid))
            if m is None:
                db.add(ProjectMember(project_id=self.p.id, user_id=uid, party_id=pt.id, is_active=False, role_id=role, discipline_ids=ds))
            elif not m.is_active:  # a placeholder from an earlier import: follow this one
                m.party_id, m.role_id, m.discipline_ids = pt.id, role, ds
        db.flush()
        self.report["people (placeholders)"] = made

    def uid(self, v, kind="u"):
        return self.users.get((kind, v[0])) if m2o(v) else None

    # ---- records
    def _record(self, code, number, rev, title, state_code, *, discipline=None, description=None, by=None, to=None,
                submitted=None, answered=None, response=None, legacy=None, custom=None, party=None, group=None, **extra):
        from app.models.records import Record
        rt, st = self.types[code], self.states[code][state_code]
        rec = Record(id=uuid.uuid4(), project_id=self.p.id, record_type_id=rt.id, number=number[:60], rev_no=rev,
                     revision_group_id=group or uuid.uuid4(), title=(title or number)[:300], description=description,
                     state_id=st.id, state_category=st.category,
                     from_party_id=(party or self.contractor).id,
                     to_party_id=(self.contractor if party is self.consultant else self.consultant).id,
                     discipline_id=self.disc.get(DISC.get(discipline or "", "")) if discipline else None,
                     created_by=by or self.actor.id, legacy_ref=legacy, custom=custom or {}, **extra)
        if st.category != "draft":
            rec.submitted_by, rec.submitted_at = by or self.actor.id, submitted
        if st.category not in ("draft", "submitted", "cancelled") and answered:
            rec.answered_by, rec.answered_at, rec.response_comment = to or self.actor.id, answered, response
        rec.created_at = rec.updated_at = answered or submitted or datetime.now(UTC)
        self.db.add(rec)
        self.db.flush()  # details, lab results and events point at it (no ORM relationships to order the inserts)
        self.report[code] += 1
        return rec

    def _events(self, rec, code, *, submit_action="submit", answer_action="respond", closed_at=None):
        from app.models.records import RecordEvent
        sts = self.states[code]
        draft = next(s for s in sts.values() if s.is_initial)
        evs = []
        if rec.submitted_at:
            first = next(s for s in sts.values() if s.category == "submitted")
            evs.append(RecordEvent(record_id=rec.id, action=submit_action, from_state_id=draft.id, to_state_id=first.id,
                                   actor_id=rec.submitted_by, channel=CHANNEL, at=rec.submitted_at))
            if rec.answered_at:
                evs.append(RecordEvent(record_id=rec.id, action=answer_action, from_state_id=first.id, to_state_id=rec.state_id,
                                       actor_id=rec.answered_by, channel=CHANNEL, comment=rec.response_comment, at=rec.answered_at))
        elif rec.state_category == "cancelled":
            evs.append(RecordEvent(record_id=rec.id, action="cancel", from_state_id=draft.id, to_state_id=rec.state_id,
                                   actor_id=rec.created_by, channel=CHANNEL, at=rec.created_at))
        self.db.add_all(evs)

    def _due(self, rec, code, start, deadline=None):
        from app.api.records import periods
        from app.core.workcal import add_period
        if start is None:
            return
        rec.due_at = odoo_due(self.data, code, start, deadline)
        if rec.due_at is None:
            reply, _ = periods(self.p, self.types[code])
            rec.due_at = add_period(start, reply, self.cal)
        # no resubmission deadline: what Odoo left unresubmitted is history, not a debt to chase now

    def _comments(self, rec, r, author):
        from app.models.records import RecordComment
        for f in ("internalnote", "internalnotem"):
            body = txt(r.get(f))
            if body:
                self.db.add(RecordComment(record_id=rec.id, party_id=self.contractor.id, visibility="internal",
                                          author_id=author or self.actor.id, body=body, created_at=rec.created_at))

    def _groups(self, code, rows, number_of, rev_of_row, cancelled):
        """Revision chains: same number -> one group. A clash (same number and revision twice):
        a cancelled copy keeps its number in a group of its own; two live copies -> the second gets a new number."""
        out, seen, alone = [], defaultdict(dict), []
        for r in sorted(rows, key=lambda r: (norm(number_of(r)), rev_of_row(r), cancelled(r), r["id"])):
            n, k = number_of(r), rev_of_row(r)
            key = norm(n)
            if k in seen[key]:
                if cancelled(r) or cancelled(seen[key][k]):
                    alone.append((n, k, uuid.uuid4(), r))
                    self.report[f"{code}: cancelled duplicates kept apart"] += 1
                    continue
                suffix = 2
                while k in seen.get(f"{key}-{suffix}", {}):
                    suffix += 1
                new = f"{n}-{suffix}"
                self.warn(f"{code} {n} R{k}: twice in Odoo, both live; the second is imported as {new}")
                n, key = new, norm(new)
            seen[key][k] = r
            out.append((n, k, key, r))
        groups = {key: uuid.uuid4() for key in seen}
        return [(n, k, groups[key], r) for n, k, key, r in out] + alone

    def _chain(self, recs: list):
        """A revision answered 'revise and resubmit' was resubmitted when the next revision was submitted."""
        by = defaultdict(dict)
        for rec in recs:
            by[rec.revision_group_id][rec.rev_no] = rec
        for g in by.values():
            for k, rec in g.items():
                nxt = g.get(k + 1)
                if nxt is not None and nxt.submitted_at and rec.state_category in ("revise_and_resubmit", "rejected"):
                    rec.resubmitted_at = nxt.submitted_at

    def submittals(self):
        from app.models.records import SubmittalDetails
        from app.core.kinds import submittal_kinds
        rows = self.M.get("submit.submit", [])
        kinds = submittal_kinds(self.p)
        by_name = {k["name_en"].lower(): k["code"] for k in kinds}
        recs = []
        for n, k, g, r in self._groups("submittal", rows, lambda r: r["name"].strip(), lambda r: rev_of(r.get("submitalrev")),
                                       lambda r: r.get("status") == "cancelled"):
            kind_name = m2o_name(r.get("submitaltye"))
            kind = None
            if kind_name:
                kind = KINDS.get(kind_name.lower()) or by_name.get(kind_name.lower())
                if kind is None:
                    kind = slug(kind_name)
                    kinds.append({"code": kind, "name_ar": kind_name, "name_en": kind_name, "active": True})
                    by_name[kind_name.lower()] = kind
            sub = at(true_day(r, d(r.get("submitaldate")) or d(r.get("date")), d(r.get("submitalanswerdate"))),
                     clock(r.get("submitaltime")))
            ans = at(d(r.get("submitalanswerdate")), clock(r.get("submitalanswertime")), time(12, 0))
            by, to = self.uid(r.get("submitby")), self.uid(r.get("submitto"))
            rec = self._record("submittal", n, k, txt(r.get("submitalname")) or txt(r.get("submitalitdescrip")), REVIEW[r["status"]],
                               discipline=r.get("category"), description=txt(r.get("submitalnote")), by=by, to=to,
                               submitted=sub, answered=ans, response=txt(r.get("submitalsupervnote")),
                               legacy=f"odoo:submit.submit:{r['id']}", group=g,
                               custom={"odoo_description": txt(r.get("submitalitdescrip"))} if txt(r.get("submitalitdescrip")) and txt(r.get("submitalname")) else {})
            self._due(rec, "submittal", sub, d(r.get("deadline_date")))
            self.db.add(SubmittalDetails(record_id=rec.id, submittal_kind=kind, item=m2o_name(r.get("submitalitem")),
                                         manufacturer=m2o_name(r.get("submitalmanf")), supplier=m2o_name(r.get("submitalagent")),
                                         drawing_ref=txt(r.get("submitaldraw"), 200), boq_ref=txt(r.get("submitalboq"), 100),
                                         quantity=num(r.get("submitalqty")), unit=m2o_name(r.get("unitm"))))
            recs.append(rec)
            self.db.flush()
            self._events(rec, "submittal")
            self._comments(rec, r, by)
        self._chain(recs)
        self.p.settings = {**(self.p.settings or {}), "submittal_kinds": kinds}

    def inspections(self):
        from app.models.records import SubmittalDetails
        rows = self.M.get("inspection.inspection", [])
        recs = []
        for n, k, g, r in self._groups("inspection", rows, lambda r: r["name"].strip(), lambda r: rev_of(r.get("inspectionrev")),
                                       lambda r: r.get("status") == "cancelled"):
            answered = d(r.get("inspectionanswerdate"))
            rday = d(r.get("date"))
            fixed = true_day(r, rday, answered)
            day = d(r.get("inspectiondate")) or rday
            if fixed != rday and day == rday:  # the inspection date was edited together with the record date
                day = fixed
            asked = at(day, clock(r.get("inspectiontime")), time(9, 0))
            sub = at(fixed or day, None, time(8, 0))
            if asked and sub and sub > asked:
                sub = asked
            ans = at(d(r.get("inspectionanswerdate")), clock(r.get("inspectionanswertime")), time(13, 0))
            if ans and asked and ans < asked:
                ans = asked + timedelta(hours=2)
            unit = self.floorx.get(m2o_id(r.get("floorselect")))
            st = self.stage_for(m2o_id(r.get("inspectionaction")), m2o_id(r.get("inspectionitem")))
            place = txt(r.get("inspectionlocation"))
            floor_txt = m2o_name(r.get("floorselect")) if unit is None and m2o(r.get("floorselect")) else None
            desc = "\n".join(x for x in (txt(r.get("inspectionnote")), txt(r.get("inspectiondescrip")),
                                         f"الموقع: {place}" if place else None, f"الطابق (Odoo): {floor_txt}" if floor_txt else None) if x)
            by, to = self.uid(r.get("inspectionsubmitby")), self.uid(r.get("inspectionsubmitto"))
            state = INSPECTION[r["status"]]
            rec = self._record("inspection", n, k, txt(r.get("inspectionname")) or txt(r.get("inspectiondescrip")) or m2o_name(r.get("inspectionitem")),
                               state, discipline=r.get("category"), description=desc or None, by=by, to=to, submitted=sub,
                               answered=ans, response=txt(r.get("inspectionsupervnote")), legacy=f"odoo:inspection.inspection:{r['id']}",
                               group=g, requested_for=asked if state != "draft" else None,
                               stage_id=st.id if st else None, location_ids=[unit.id] if unit else None,
                               custom={k2: v for k2, v in (("odoo_type", m2o_name(r.get("inspectiontype"))),
                                                           ("odoo_action", m2o_name(r.get("inspectionaction")))) if v})
            if rec.answered_at:
                rec.performed_at = rec.answered_at
            self._due(rec, "inspection", max(x for x in (sub, asked) if x) if (sub or asked) else None)
            self.db.add(SubmittalDetails(record_id=rec.id, item=m2o_name(r.get("inspectionitem")),
                                         drawing_ref=txt(r.get("inspectiondraw"), 200), boq_ref=txt(r.get("inspectionboq"), 100)))
            recs.append(rec)
            self.db.flush()
            self._events(rec, "inspection")
            self._comments(rec, r, by)
            if unit is None and m2o(r.get("floorselect")):
                self.report["inspections: floor not matched"] += 1
            if st is None:
                self.report["inspections: no stage"] += 1
        self._chain(recs)

    def rfis(self):
        from app.models.records import SubmittalDetails
        def number(r):
            k = rev_of(r.get("rfirev"))
            return r["name"].strip() + (f"-R{k}" if k else "")
        for n, _k, _g, r in self._groups("rfi", self.M.get("rfi.rfi", []), number, lambda r: 0, lambda r: False):
            sub = at(true_day(r, d(r.get("rfidate")) or d(r.get("date")), d(r.get("rfianswerdate"))), clock(r.get("rfitime")))
            ans = at(d(r.get("rfianswerdate")) or d(r.get("rfidate2")), clock(r.get("rfianswertime")), time(12, 0))
            state = {"answered": "answered", "submitted": "submitted", "draft": "draft"}.get(r.get("status"), "submitted")
            by, to = self.uid(r.get("rfisubmitby")), self.uid(r.get("rfisubmitto"))
            rec = self._record("rfi", n, 0, txt(r.get("rfisubject")) or n, state, discipline=r.get("category"),
                               description=txt(r.get("rfidescrip")), by=by, to=to, submitted=sub, answered=ans,
                               response=txt(r.get("rfisupervnote")), legacy=f"odoo:rfi.rfi:{r['id']}")
            self._due(rec, "rfi", sub)
            self.db.add(SubmittalDetails(record_id=rec.id, drawing_ref=txt(r.get("rfidraw"), 200), boq_ref=txt(r.get("rfiboq"), 100)))
            self.db.flush()
            self._events(rec, "rfi", answer_action="answer")
            self._comments(rec, r, by)

    def ncrs(self):
        from app.models.records import RecordEvent
        lines = defaultdict(list)
        for x in self.M.get("site.instruction.line", []):
            lines[m2o_id(x.get("instruction_id"))].append(x)
        sts = self.states["ncr"]
        def number(r):
            return f"SI-{int(num(r['name'])):03d}" if num(r["name"]) is not None else r["name"].strip()
        for n, _k, _g, r in self._groups("ncr", self.M.get("site.instruction", []), number, lambda r: 0, lambda r: False):
            issued = at(d(r.get("instruction_date")), None, time(9, 0))
            acted = at(d(r.get("action_done_date")) or d(r.get("close_date")), None, time(12, 0))
            closed = at(d(r.get("close_date")) or d(r.get("action_done_date")), None, time(14, 0))
            items = [f"• {txt(x.get('description'))}" + (f" — {txt(x.get('notes'))}" if txt(x.get("notes")) else "")
                     for x in lines.get(r["id"], []) if txt(x.get("description"))]
            desc = "\n".join(x for x in (txt(r.get("site_subject_details")), "\n".join(items) or None) if x)
            by, to = self.uid(r.get("submit_from"), "p"), self.uid(r.get("submit_to"), "p")
            state = "closed" if r.get("status") == "closed" else "open"
            rec = self._record("ncr", n, 0, txt(r.get("site_subject")) or m2o_name(r.get("subject_id")) or n, state,
                               discipline=r.get("category"), description=desc or None, by=by, to=to, submitted=issued,
                               answered=acted if state == "closed" else None, response=txt(r.get("contractor_response")),
                               legacy=f"odoo:site.instruction:{r['id']}", party=self.consultant,
                               custom={**({"required_action": "\n".join(items)} if items else {}),
                                       **({"odoo_subject": m2o_name(r["subject_id"])} if m2o(r.get("subject_id")) else {})})
            self._due(rec, "ncr", issued)
            self.db.flush()
            if issued:
                ev = [RecordEvent(record_id=rec.id, action="issue", from_state_id=sts["draft"].id, to_state_id=sts["open"].id,
                                  actor_id=rec.submitted_by, channel=CHANNEL, at=issued)]
                if state == "closed" and acted:
                    ev += [RecordEvent(record_id=rec.id, action="propose_action", from_state_id=sts["open"].id,
                                       to_state_id=sts["action_proposed"].id, actor_id=rec.answered_by, channel=CHANNEL,
                                       comment=rec.response_comment, at=acted),
                           RecordEvent(record_id=rec.id, action="close", from_state_id=sts["action_proposed"].id,
                                       to_state_id=sts["closed"].id, actor_id=rec.submitted_by, channel=CHANNEL,
                                       at=max(closed or acted, acted))]
                self.db.add_all(ev)

    def tests(self):
        from app.core.lab import evaluate
        from app.models.lab import ConcreteClass, LabResult
        classes = {}
        for i, c in enumerate(self.M.get("dr.concrete.class", [])):
            if m2o_id(c.get("project_id")) not in (None, *self.data["meta"]["projects"]):
                continue
            cc = ConcreteClass(id=uuid.uuid4(), project_id=self.p.id, grade=(c.get("grade") or "?")[:30], name=txt(c.get("name"), 150),
                               specimen=c.get("specimen_type") or "cube", fck=Decimal(str(c.get("specified_strength") or 0)),
                               mean_margin=Decimal(str(c.get("mean_margin") or 0)), individual_rule=c.get("individual_rule") or "minus",
                               individual_margin=Decimal(str(c.get("individual_margin") or 4)), elements=txt(c.get("elements"), 300),
                               ref=txt(c.get("qmp_ref"), 150), sort=(i + 1) * 10, is_active=bool(c.get("active", True)))
            self.db.add(cc)
            classes[c["id"]] = cc
        mats = {m["id"]: m.get("code") for m in self.M.get("dr.material.type", [])}
        lines = defaultdict(list)
        for x in sorted(self.M.get("dr.test.result.line", []), key=lambda x: (x.get("sequence") or 0, x.get("id") or 0)):
            lines[m2o_id(x.get("test_id"))].append(x)
        recs = []
        for n, k, g, r in self._groups("test", self.M.get("quality.quality", []), lambda r: r["name"].strip(), lambda r: 0,
                                       lambda r: False):
            sub = at(d(r.get("submitaldate")) or d(r.get("date")), clock(r.get("submitaltime")))
            res = r.get("final_result") or r.get("qresult")
            state = "accepted" if res == "pass" else "retest" if res == "fail" else "submitted"
            ans = at(d(r.get("submitalanswerdate")) or d(r.get("decision_date")) or (d(r.get("submitaldate")) or d(r.get("date"))), None, time(14, 0)) \
                if state != "submitted" else None
            by, to = self.uid(r.get("submitby")), self.uid(r.get("submitto"))
            rec = self._record("test", n, k, txt(r.get("qsubmitalitdescrip")) or m2o_name(r.get("qsubmitaltye")) or n, state,
                               discipline=r.get("category"), description=txt(r.get("submitalnote")), by=by, to=to, submitted=sub,
                               answered=ans, response=txt(r.get("submitalsupervnote")) or txt(r.get("decision_note")),
                               legacy=f"odoo:quality.quality:{r['id']}", group=g)
            self._due(rec, "test", sub)
            ln = []
            for x in lines.get(r["id"], []):
                ok = x.get("value_kind") == "okng"
                ln.append({"sample": txt(x.get("sample"), 60), "parameter": (txt(x.get("parameter")) or "?")[:200],
                           "unit": txt(x.get("unit"), 30), "method": txt(x.get("standard"), 80), "age": x.get("age_days") or None,
                           "kind": "okng" if ok else "number", "value": None if ok else x.get("value"),
                           "text": txt(x.get("value_text"), 60), "min": x.get("min_value") or None, "max": x.get("max_value") or None,
                           "role": x.get("kpi_role") or None, "legible": True})
            cc = classes.get(m2o_id(r.get("concrete_class_id")))
            lab = LabResult(record_id=rec.id, material=mats.get(m2o_id(r.get("material_type_id"))) or None,
                            acceptance="concrete" if r.get("acceptance_method") == "concrete" else "all",
                            lab_name=m2o_name(r.get("qsubmitalagent")), lab_report_no=txt(r.get("lab_report_no"), 80),
                            sampling_date=d(r.get("sampling_date")), test_date=d(r.get("date")), report_date=d(r.get("report_date")),
                            grade=txt(r.get("grade"), 30), class_id=cc.id if cc else None,
                            fck=Decimal(str(r["specified_strength"])) if r.get("specified_strength") else None,
                            mean_margin=Decimal(str(r.get("mean_margin") or 0)),
                            individual_rule=r.get("individual_rule") or None,
                            individual_margin=Decimal(str(r["individual_margin"])) if r.get("individual_margin") else None,
                            element=txt(r.get("element"), 200), quantity=Decimal(str(r["quantity"])) if r.get("quantity") else None,
                            quantity_uom=txt(r.get("quantity_uom"), 20), specimen_count=r.get("specimen_count") or None,
                            specification=txt(r.get("specification"), 200), lab_conclusion=r.get("lab_conclusion") or None, lines=ln,
                            decision=r.get("failure_decision") or None, decision_note=txt(r.get("decision_note")))
            ev = evaluate({"lines": ln, "acceptance": lab.acceptance, "fck": lab.fck, "mean_margin": lab.mean_margin,
                           "individual_rule": lab.individual_rule, "individual_margin": lab.individual_margin})
            lab.result, lab.note = ev["result"], (ev["note"] or "")[:300]
            if lab.result and res and lab.result != res:
                self.warn(f"test {n}: Odoo says {res}, Verqac calculates {lab.result}")
            self.db.add(lab)
            recs.append(rec)
            self.db.flush()
            self._events(rec, "test")
            self._comments(rec, r, by)

    # ---- daily reports
    def daily(self):
        from app.api.daily import _strip
        from app.models.daily import DailyReport
        M = self.M
        kids = defaultdict(lambda: defaultdict(list))
        for model, link in (("teamc.teamc", "teamc_id"), ("teams.teams", "teams_id"), ("subcont.subcont", "subcont_id"),
                            ("materials.materials", "mater_id"), ("equip.equip", "equip_id"), ("work.work", "work_id"),
                            ("worknd.worknd", "work_id")):
            for x in M.get(model, []):
                kids[m2o_id(x.get(link))][model].append(x)
        by_day = defaultdict(list)
        for r in M.get("dr.dr", []):
            if r.get("date"):
                by_day[r["date"][:10]].append(r)
        self.dr_by_day = {}
        self.approved_dr = set()
        lists = defaultdict(set)
        for day_s, rs in sorted(by_day.items()):
            rs.sort(key=lambda r: (r.get("status") != "signed", r["id"]))
            r = rs[0]
            if len(rs) > 1:
                self.warn(f"daily report {day_s}: {len(rs)} in Odoo, merged into one")
            day = date.fromisoformat(day_s)
            crew, equipment, materials, works, planned = [], [], [], [], []
            for one in rs:
                k = kids[one["id"]]
                for model, group in (("teamc.teamc", "supervision"), ("teams.teams", "contractor"), ("subcont.subcont", "labour")):
                    for x in k[model]:
                        name = m2o_name(x.get("staff")) or txt(x.get("description"), 150)
                        cnt = int(x.get("value") or 0)
                        if not name or cnt <= 0 or one is not r and model != "subcont.subcont":
                            continue
                        crew.append({"group": group, "sub": None, "name": name[:150], "name_en": name[:150], "role": None,
                                     "role_en": None, "count": cnt, "hours": min(24.0, num(x.get("wtime")) or 0) or None})
                        lists[f"{group}_desc"].add(name[:150])
                for x in k["equip.equip"]:
                    name = m2o_name(x.get("euiplist")) or txt(x.get("name"), 150)
                    if name:
                        equipment.append({"name": name[:150], "count": int(x.get("qty") or 1), "hours": None, "idle_hours": None,
                                          "note": txt(x.get("description"), 300)})
                        lists["equipment"].add(name[:150])
                for x in k["materials.materials"]:
                    name = m2o_name(x.get("materiallist")) or txt(x.get("name"), 200) or txt(x.get("description"), 200)
                    if name:
                        materials.append({"material": name[:200], "qty": x.get("qty") or None, "unit": (m2o_name(x.get("unitm")) or "")[:20] or None,
                                          "supplier": None, "delivery_note": None, "submittal_id": None, "mir_id": None})
                for model, target in (("work.work", works), ("worknd.worknd", planned)):
                    for x in k[model]:
                        target.append(self._work(x))
            if not any(x["group"] == "labour" for x in crew):
                from app.api.daily import labour_from_works
                for x in labour_from_works(works):
                    crew.append(x)
                    lists["labour_desc"].add(x["name"])
            weather = WEATHER.get((m2o_name(r.get("weather")) or "").lower())
            wind = WIND.get((m2o_name(r.get("wind")) or "").lower())
            ws = (m2o_name(r.get("work")) or "").strip()
            status = "normal" if ws.lower() in ("working day", "") else "partial" if "partial" in ws.lower() else "stopped"
            tmin = tmax = None
            if r.get("temperature") and "-" in str(r["temperature"]):
                tmin, tmax = (float(x) for x in str(r["temperature"]).split("-", 1))
            state = "approved" if r.get("status") in APPROVED_DR else "draft"
            sub = at(d(r.get("submitaldate")) or day, clock(r.get("submitaltime")), time(16, 0))
            ans = at(d(r.get("submitalanswerdate")) or day + timedelta(days=1), clock(r.get("submitalanswertime")), time(9, 0))
            by, to = self.uid(r.get("submitby")), self.uid(r.get("submitto"))
            notes = "\n".join(x for x in (txt(r.get("description")), txt(r.get("submitalnote"))) if x) or None
            rec = self._record("daily_report", f"DR-{day_s}", 0, f"التقرير اليومي {day_s}", state, by=by, to=to,
                               submitted=sub, answered=ans, response=txt(r.get("submitalsupervnote")), legacy=f"odoo:dr.dr:{r['id']}",
                               custom={"odoo_no": str(r.get("name") or "").strip()})
            self._due(rec, "daily_report", sub)
            dr = DailyReport(record_id=rec.id, project_id=self.p.id, report_date=day, shift="day", work_status=status,
                             stop_reason=ws[:300] if status == "stopped" else None, weather=weather, wind=wind,
                             temp_min=Decimal(str(tmin)) if tmin is not None else None,
                             temp_max=Decimal(str(tmax)) if tmax is not None else None, crew=crew, equipment=equipment,
                             materials=materials, works=[_strip(w) for w in works], planned=[_strip(w) for w in planned],
                             delays=[], hse={"incidents": 0, "near_misses": 0, "toolbox": 0, "notes": None}, notes=notes)
            self.db.add(dr)
            self.db.flush()
            self._events(rec, "daily_report", answer_action="approve")
            self._comments(rec, r, by)
            self.dr_by_day[day] = dr
            if state == "approved":
                self.approved_dr.add(rec.id)
        # daily settings: counts mode, and the names used as lists
        from app.api.daily import daily_settings
        ds = daily_settings(self.p).model_dump()
        ds["crew"] = {"supervision": "counts", "contractor": "counts", "labour": "counts"}
        ds["actual_dates"] = True
        ds["lists"] = {k: [{"ar": n, "en": n, "role_ar": None, "role_en": None, "active": True} for n in sorted(v)][:300]
                       for k, v in lists.items()}
        self.p.settings = {**(self.p.settings or {}), "daily": ds}

    def _work(self, x) -> dict:
        st = self.stage.get(m2o_id(x.get("schedule_stage_id")))
        unit = self.loc.get(m2o_id(x.get("schedule_location_id"))) or self.floorx.get(m2o_id(x.get("floorselect")))
        bits = [m2o_name(x.get("actiondone")), m2o_name(x.get("workdone")), txt(x.get("itemname")), txt(x.get("description"))]
        seen, desc = set(), []
        for b in bits:
            if b and b.lower() not in seen:
                seen.add(b.lower())
                desc.append(b)
        if unit is None and m2o(x.get("floorselect")):
            desc.append(f"({m2o_name(x['floorselect'])})")
        pct = None  # the % comes from the Odoo schedule cells (they hold the final, corrected values)
        if st is None:
            self.report["work lines without stage"] += 1
        return {"stage_id": st.id if st else None, "topic_id": None,
                "location_ids": [unit.id] if unit and st is not None and st.scope != "whole" else [],
                "all_locations": False, "description": " – ".join(desc)[:1000] or None, "qty": x.get("qty") or None,
                "unit": (m2o_name(x.get("unitm")) or "")[:20] or None, "crew": int(x.get("laborno") or 0) or None,
                **team_of(x),
                "progress": pct if st is not None else None, "actual_start": None, "actual_finish": None}

    def progress_from_schedule(self):
        """The Odoo schedule's % and actual dates per floor x stage, set on the daily report of their date."""
        from app.api.daily import _strip
        days = sorted(d for d, dr in self.dr_by_day.items() if dr.record_id in self.approved_dr)  # only approved ones count
        if not days:
            return
        import bisect
        for c in self.M.get("dr.schedule.cell", []):
            pct = c.get("progress") or 0
            st = self.stage.get(m2o_id(c.get("stage_id")))
            if pct <= 0 or st is None:
                continue
            unit = self.loc.get(m2o_id(c.get("location_id")))
            if st.scope != "whole" and unit is None:
                self.report["schedule cells: floor not matched"] += 1
                continue
            begin, end = d(c.get("actual_start")), d(c.get("actual_finish"))
            when = end if pct >= 100 and end else d(c.get("actual_last")) or d(c.get("manual_progress_date")) or begin or days[-1]
            i = bisect.bisect_right(days, when) - 1
            day = days[max(i, 0)]
            dr = self.dr_by_day[day]
            if begin and begin > day:
                begin = day
            fin = end if pct >= 100 and end else None
            if fin and (fin > day or (begin and fin < begin)):
                fin = day
            line = {"stage_id": st.id, "topic_id": None, "location_ids": [unit.id] if unit and st.scope != "whole" else [],
                    "all_locations": False, "description": SCHEDULE_LINE, "qty": None, "unit": None, "crew": None,
                    "progress": round(min(100.0, pct), 1), "actual_start": begin, "actual_finish": fin if pct >= 100 else None}
            if pct >= 100 and fin is None:
                line["actual_finish"] = None
            dr.works = [*dr.works, _strip(line)]
            self.report["schedule cells with progress"] += 1
        self.db.flush()

    def run(self):
        from app.api.daily import rebuild_progress
        from app.core.workcal import calendar_for
        self.cal = calendar_for(self.db, self.p)
        self.setup()
        self.wipe()
        self.structure()
        self.people()
        self.submittals()
        self.inspections()
        self.rfis()
        self.ncrs()
        self.tests()
        self.daily()
        self.progress_from_schedule()
        if kpi_targets(self.data, self.p):
            self.report["KPI targets"] += 1
        first = min(self.dr_by_day) if self.dr_by_day else None
        start = d(self.data["projects"][0].get("date_start")) if self.data.get("projects") else None
        if self.p.start_date is None and (start or first):
            self.p.start_date = min(x for x in (start, first) if x)
        self.db.flush()
        rebuild_progress(self.db, self.p.id)
        self.db.flush()


IMAGE = ("image/jpeg", "image/png", "image/webp", "image/gif")
FIELD_NAMES = {"pdf_file", "file_field", "pdf_file_answer", "photo", "image", "datas"}
SKIP_FIELDS = {"logo_image"}  # the letterhead Odoo kept on every record: not a document of the record


# Odoo's reply periods (calendar days, project settings of dr): an imported record keeps the deadline it had there
ODOO_PERIOD = {"submittal": ("qa_submittal_review_days", 14), "inspection": ("qa_ir_response_days", 2),
               "rfi": ("qa_rfi_response_days", 7)}


def odoo_due(data: dict, code: str, start, deadline=None):
    """The record's own deadline, else its date + the project's period in Odoo, to the end of that day."""
    if code not in ODOO_PERIOD or start is None:
        return None
    if deadline is None:
        field, default = ODOO_PERIOD[code]
        n = int(((data.get("projects") or [{}])[0]).get(field) or default)
        deadline = start.astimezone(TZ).date() + timedelta(days=n)
    return datetime.combine(deadline, time(23, 59), TZ)


def kpi_targets(data: dict, project) -> bool:
    """The KPI targets set in Odoo (dr.qa.kpi.target: the company's, overridden by the project's) become the project's,
    unless the project already has its own."""
    from app.core import kpi
    if (project.settings or {}).get("kpi"):
        return False
    rows = data["models"].get("dr.qa.kpi.target", [])
    if not rows:
        return False
    odoo_pid = (data.get("meta", {}).get("projects") or [None])[0]
    pick = {}
    for r in sorted(rows, key=lambda r: bool(r.get("project_id"))):  # the project's line wins over the company's
        if r.get("project_id") and m2o_id(r["project_id"]) != odoo_pid:
            continue
        if r.get("code") in kpi.DEF:
            pick[r["code"]] = r
    targets = {}
    for code, r in pick.items():
        info = kpi.DEF[code][3] == "info"
        targets[code] = {"green": None if info else r.get("green_threshold"), "amber": None if info else r.get("amber_threshold"),
                         "qmp_ref": (txt(r.get("qmp_ref"), 60) or kpi.DEF[code][6]), "active": bool(r.get("active", True))}
    close = int(((data.get("projects") or [{}])[0]).get("qa_ncr_close_days") or kpi.DEFAULT_NCR_CLOSE_DAYS)
    project.settings = {**(project.settings or {}), "kpi": {"targets": targets, "ncr_close_days": close}}
    return True


SCHEDULE_LINE = "نسبة الإنجاز من جدول Odoo"


def team_of(x: dict) -> dict:
    """Who did an Odoo work line: its team ("Team Select") and the workers' hours."""
    n = int(x.get("laborno") or 0)
    team = (m2o_name(x.get("subcontselec")) or ("Labour" if n > 0 else "") or "")[:150] or None
    return {"team": team, "team_en": team, "sub": None, "hours": min(24.0, float(x.get("labortime") or 0)) or None}


def labour_of(lines: list[dict]) -> list[dict]:
    """Odoo's daily report kept the labour on each work line (team + number of workers):
    the day's labour is, per team, the workers of its lines added up."""
    teams: dict[str, dict] = {}
    for x in lines:
        n = int(x.get("laborno") or 0)
        if n <= 0:
            continue
        name = (m2o_name(x.get("subcontselec")) or "Labour")[:150]
        t = teams.setdefault(name, {"group": "labour", "sub": None, "name": name, "name_en": name, "role": None,
                                    "role_en": None, "count": 0, "hours": None})
        t["count"] += n
        h = min(24.0, float(x.get("labortime") or 0)) or None
        if h and (t["hours"] is None or h > t["hours"]):
            t["hours"] = h
    return list(teams.values())


def caption_of(att: dict, rows: dict) -> str | None:
    """Odoo's daily report keeps a description next to each of its four photos (image_1 → image_1_desc)."""
    field = att.get("res_field") or ""
    if att.get("res_model") != "dr.dr" or not field.startswith("image_"):
        return None
    r = rows.get(att.get("res_id")) or {}
    return (txt(r.get(f"{field}_desc"), 300) or None) if r else None
EXT = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}


def file_name(att: dict, rec) -> str:
    """Odoo names a file kept in a record field after the field ('pdf_file', 'image_2'): use the record's number instead."""
    name = (att.get("name") or "").strip()
    field = att.get("res_field") or ""
    if name and name not in FIELD_NAMES and name != field:
        return name[:255]
    ext = EXT.get(att.get("mimetype") or "", "")
    tail = "-answer" if field == "pdf_file_answer" else f"-photo{field[6:]}" if field.startswith("image_") else ""
    return f"{rec.number}-R{rec.rev_no}{tail}{ext}" if rec is not None else (name or "file") + ext


def _field_named(f, att: dict) -> bool:
    return f.filename in FIELD_NAMES or f.filename == (att.get("res_field") or None) or "." not in f.filename


def import_files(db, data: dict, root: str, project, actor, commit: bool) -> Counter:
    """Attach the exported Odoo files to the imported records (found by legacy_ref)."""
    import hashlib
    import os
    import shutil

    from app.core import storage
    from app.models.core import ProjectParty
    from app.models.daily import DailyReport
    from app.models.records import Attachment, Record, StoredFile
    rep: Counter = Counter()
    recs = {r.legacy_ref: r for r in db.scalars(select(Record).where(Record.project_id == project.id, Record.legacy_ref.is_not(None)))}
    # daily reports merged on import (two in Odoo on one day): their files go to the one report of that day
    by_day = {d.report_date: d.record_id for d in db.scalars(select(DailyReport).where(DailyReport.project_id == project.id))}
    dr_day = {r["id"]: d(r.get("date")) for r in data["models"].get("dr.dr", [])}
    parties = {x.kind: x.id for x in db.scalars(select(ProjectParty).where(ProjectParty.project_id == project.id,
                                                                              ProjectParty.status != "removed"))}
    have = {(x.record_id, x.file_id) for x in db.scalars(select(Attachment).join(Record, Record.id == Attachment.record_id)
                                                          .where(Record.project_id == project.id))}
    store = storage._root()
    dr_rows = {r["id"]: r for r in data["models"].get("dr.dr", [])}
    for att in data.get("attachments", []):
        if att.get("res_field") in SKIP_FIELDS:
            rep["letterhead skipped"] += 1
            continue
        src = os.path.join(root, att["path"]) if att.get("path") else None
        model, rid = att.get("res_model"), att.get("res_id")
        rec = recs.get(f"odoo:{model}:{rid}")
        rec_id = rec.id if rec else (by_day.get(dr_day.get(rid)) if model == "dr.dr" else None)
        if rec_id is None:
            rep["no record (not imported)"] += 1
            continue
        rec = rec or db.get(Record, rec_id)
        key = f"{project.id}/odoo-{att['id']}"
        dest = store / key
        f = db.scalar(select(StoredFile).where(StoredFile.storage_key == key))
        if f is None:
            path = src if src and os.path.exists(src) else (str(dest) if dest.exists() else None)
            if path is None:
                rep["file missing in the export"] += 1
                continue
            h, size = hashlib.sha256(), 0
            with open(path, "rb") as fh:
                while chunk := fh.read(1 << 20):
                    h.update(chunk)
                    size += len(chunk)
            if size == 0:
                rep["empty file"] += 1
                continue
            if commit and path != str(dest):
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(path, dest)  # same volume: a rename, nothing is copied
            f = StoredFile(id=uuid.uuid4(), project_id=project.id, storage_key=key, filename=file_name(att, rec),
                           content_type=(att.get("mimetype") or "application/octet-stream")[:120], size=size,
                           sha256=h.hexdigest(), uploaded_by=actor.id)
            db.add(f)
            db.flush()
            rep["files"] += 1
            rep["MB"] += round(size / 1048576)
        if _field_named(f, att) and (new := file_name(att, rec)) != f.filename:
            f.filename = new
            rep["files renamed"] += 1
        if (rec_id, f.id) in have:
            rep["already attached"] += 1
            continue
        mime = att.get("mimetype") or ""
        field = att.get("res_field") or ""
        kind = "response" if field == "pdf_file_answer" else "photo" if mime in IMAGE else "submission"
        party = parties["contractor"] if (model != "site.instruction" or kind == "response") else parties["consultant"]
        a = Attachment(record_id=rec_id, file_id=f.id, kind=kind, party_id=party, caption=caption_of(att, dr_rows))
        created = (att.get("create_date") or "")[:19]
        if created:
            a.created_at = datetime.fromisoformat(created).replace(tzinfo=UTC)
        db.add(a)
        have.add((rec_id, f.id))
        rep[f"attached ({kind})"] += 1
    db.flush()
    return rep


def fix_imported(db, data: dict, project, paths: list | None = None) -> Counter:
    """Correct an import in place (nothing else is touched, so work done since stays):
    submission dates Odoo had edited afterwards, no resubmission deadlines on imported history,
    no reminders already sent about it, files named after Odoo's fields, no letterhead "photos", photo captions.
    The files whose records are deleted are added to `paths` (to be removed from disk once committed)."""
    from app.api.records import RESUBMIT_STATES
    from app.models.records import Notification, Record, RecordEvent, StoredFile
    rep: Counter = Counter()
    recs = {r.legacy_ref: r for r in db.scalars(select(Record).where(Record.project_id == project.id, Record.legacy_ref.is_not(None)))}
    fields = {"submit.submit": ("submitaldate", "submitalanswerdate"), "rfi.rfi": ("rfidate", "rfianswerdate"),
              "inspection.inspection": ("date", "inspectionanswerdate")}
    for model, (f_day, f_ans) in fields.items():
        for r in data["models"].get(model, []):
            rec = recs.get(f"odoo:{model}:{r['id']}")
            if rec is None or rec.submitted_at is None:
                continue
            day = d(r.get(f_day)) or d(r.get("date"))
            fixed = true_day(r, day, d(r.get(f_ans)))
            if fixed is None or fixed == day:
                continue
            local = rec.submitted_at.astimezone(TZ)
            new = datetime.combine(fixed, local.time(), TZ)
            if model == "inspection.inspection" and rec.requested_for and rec.requested_for.astimezone(TZ).date() == day:
                rec.requested_for = datetime.combine(fixed, rec.requested_for.astimezone(TZ).time(), TZ)
            if rec.submitted_at == new:
                continue  # corrected already
            # the history (record_events) is append-only by design: it keeps what the import wrote
            rec.submitted_at = new
            rep["submission dates corrected"] += 1
    # reply deadlines as Odoo had them (its periods in calendar days, or the record's own deadline)
    code_of = {"submit.submit": "submittal", "inspection.inspection": "inspection", "rfi.rfi": "rfi"}
    rows = {f"odoo:{m}:{r['id']}": r for m in code_of for r in data["models"].get(m, [])}
    for ref, rec in recs.items():
        r = rows.get(ref)
        if r is None or rec.submitted_at is None:
            continue
        code = code_of[ref.split(":")[1]]
        start = max(x for x in (rec.submitted_at, rec.requested_for) if x) if code == "inspection" else rec.submitted_at
        due = odoo_due(data, code, start, d(r.get("deadline_date")))
        if due is not None and rec.due_at != due:
            rec.due_at = due
            rep["reply deadlines as in Odoo"] += 1
    for r in data["models"].get("site.instruction", []):
        rec = recs.get(f"odoo:site.instruction:{r['id']}")
        if rec is not None and m2o(r.get("subject_id")) and (rec.custom or {}).get("odoo_subject") != m2o_name(r["subject_id"]):
            rec.custom = {**(rec.custom or {}), "odoo_subject": m2o_name(r["subject_id"])}
            rep["NCR subjects from Odoo"] += 1
    # resubmission deadlines left by the import (answered on import, not since)
    for rec in recs.values():
        if rec.resubmit_due_at is None or rec.resubmitted_at is not None or rec.state_category not in RESUBMIT_STATES:
            continue
        last = db.scalar(select(RecordEvent).where(RecordEvent.record_id == rec.id).order_by(RecordEvent.at.desc(), RecordEvent.id.desc()).limit(1))
        if last is not None and last.channel == CHANNEL:
            rec.resubmit_due_at = None
            rep["resubmission deadlines removed"] += 1
    ids = [r.id for r in recs.values()]
    for i in range(0, len(ids), 1000):
        res = db.execute(update(Notification).where(Notification.record_id.in_(ids[i:i + 1000]), Notification.read_at.is_(None),
                                                     Notification.event.in_(("reply_soon", "reply_late", "resub_soon", "resub_late")))
                         .values(read_at=datetime.now(UTC)))
        rep["reminder notifications cleared"] += res.rowcount or 0
    by_key = {f"{project.id}/odoo-{a['id']}": a for a in data.get("attachments", [])}
    for f in db.scalars(select(StoredFile).where(StoredFile.project_id == project.id, StoredFile.storage_key.like(f"{project.id}/odoo-%"))):
        att = by_key.get(f.storage_key)
        if att is None or att.get("res_field") in SKIP_FIELDS or not _field_named(f, att):
            continue
        rec = recs.get(f"odoo:{att.get('res_model')}:{att.get('res_id')}")
        new = file_name(att, rec)
        if new != f.filename:
            f.filename = new
            rep["files renamed"] += 1
    # labour: Odoo kept it on the work lines (team + workers). The team goes on each work line, and the
    # day's labour is worked out from them (as for reports written in Verqac)
    from app.api.daily import labour_from_works
    from app.models.daily import DailyReport
    kids = defaultdict(list)
    for x in data["models"].get("work.work", []):
        kids[m2o_id(x.get("work_id"))].append(x)
    by_day = defaultdict(list)
    for r in data["models"].get("dr.dr", []):
        if r.get("date"):
            by_day[r["date"][:10]].append(r)
    names = set()
    for dr in db.scalars(select(DailyReport).where(DailyReport.project_id == project.id)):
        rs = sorted(by_day.get(dr.report_date.isoformat(), []), key=lambda r: (r.get("status") != "signed", r["id"]))
        odoo = [x for r in rs for x in kids[r["id"]]]  # in the order the import wrote them
        if not odoo:
            continue
        works = [dict(w) for w in dr.works or []]
        # the import wrote Odoo's lines first, then the schedule's % (lines of their own)
        same = len(works) >= len(odoo) and all(w.get("description") == SCHEDULE_LINE for w in works[len(odoo):])
        if same and any(w.get("team") is None and team_of(x)["team"] for w, x in zip(works, odoo)):
            for w, x in zip(works, odoo):
                if w.get("team") is None:
                    w.update(team_of(x))
            dr.works = works
            rep["daily reports: team on work lines"] += 1
        crew = list(dr.crew or [])
        hand = [c for c in crew if c.get("group") == "labour" and not c.get("auto")]
        was = sorted((c["name"], c["count"]) for c in labour_of(odoo))
        derived = labour_from_works(works)
        # the labour the import added (untouched since) becomes the worked-out one
        if (not hand or sorted((c["name"], c["count"]) for c in hand) == was) and derived and \
                sorted((c["name"], c["count"], c.get("auto")) for c in crew if c.get("group") == "labour") != \
                sorted((c["name"], c["count"], True) for c in derived):
            dr.crew = [c for c in crew if c.get("group") != "labour"] + derived
            names.update(x["name"] for x in derived)
            rep["daily reports: labour from work lines"] += 1
    if names:
        ds = dict((project.settings or {}).get("daily") or {})
        lists = dict(ds.get("lists") or {})
        have = {x.get("ar") for x in lists.get("labour_desc", [])}
        lists["labour_desc"] = list(lists.get("labour_desc", [])) + [
            {"ar": n, "en": n, "role_ar": None, "role_en": None, "active": True} for n in sorted(names - have)]
        project.settings = {**(project.settings or {}), "daily": {**ds, "lists": lists}}
    if kpi_targets(data, project):
        rep["KPI targets from Odoo"] += 1
    # the letterhead Odoo kept on every record came in as a photo: take it out (file and all)
    from app.core import storage
    from app.models.records import Attachment
    logos = {k for k, a in by_key.items() if a.get("res_field") in SKIP_FIELDS}
    dr_rows = {r["id"]: r for r in data["models"].get("dr.dr", [])}
    gone = []
    for at, f in db.execute(select(Attachment, StoredFile).join(StoredFile, StoredFile.id == Attachment.file_id)
                            .where(StoredFile.project_id == project.id, StoredFile.storage_key.like(f"{project.id}/odoo-%"))).all():
        if f.storage_key in logos:
            db.delete(at)
            gone.append(f)
            rep["letterheads removed"] += 1
        elif at.caption is None and (cap := caption_of(by_key.get(f.storage_key, {}), dr_rows)):
            at.caption = cap
            rep["photo captions added"] += 1
    db.flush()
    for f in gone:
        if db.scalar(select(Attachment.id).where(Attachment.file_id == f.id).limit(1)) is None:
            if paths is not None:
                paths.append(str(storage._root() / f.storage_key))
            db.delete(f)
    db.flush()
    return rep


def main(argv=None):
    from app.core.db import session_scope
    from app.models.core import Project, User
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file", help="dr_export_<id>.zip (or its data.json)")
    ap.add_argument("--project", required=True, help="the Verqac project code")
    ap.add_argument("--as", dest="actor", required=True, help="e-mail of the Verqac account the import is done as")
    ap.add_argument("--commit", action="store_true", help="write the import (without it: a trial run that changes nothing)")
    ap.add_argument("--attachments", action="store_true", help="attach the files of an export folder to the imported records")
    ap.add_argument("--fix", action="store_true", help="correct an earlier import in place (dates, deadlines, reminders, file names)")
    a = ap.parse_args(argv)
    if a.attachments:
        return _files(a)
    if a.fix:
        return _fix(a)
    if a.file.endswith(".zip"):
        with zipfile.ZipFile(a.file) as z:
            data = json.loads(z.read("data.json"))
    else:
        data = json.load(open(a.file, encoding="utf-8"))
    try:
        _run(a, data)
    except TrialRun:
        print("\nTRIAL RUN: nothing was written. Add --commit to import (back up the database first).")


def _files(a):
    import os
    from app.core.db import session_scope
    from app.models.core import Project, User
    root = a.file
    data = json.load(open(os.path.join(root, "data.json"), encoding="utf-8"))
    try:
        with session_scope(bypass=True) as db:
            p = db.scalar(select(Project).where(func.upper(Project.code) == a.project.upper()))
            actor = db.scalar(select(User).where(func.lower(User.email) == a.actor.lower()))
            if p is None or actor is None:
                sys.exit("Project or account not found.")
            rep = import_files(db, data, root, p, actor, a.commit)
            print(f"Attachments for {p.code}:")
            for k, v in sorted(rep.items()):
                print(f"  {k:32} {v}")
            if not a.commit:
                raise TrialRun
            print("\nDone. Files moved into the platform's storage; running again adds only what is missing.")
    except TrialRun:
        print("\nTRIAL RUN: nothing was moved or written. Add --commit to attach the files.")


def _fix(a):
    import os
    from app.core.db import session_scope
    from app.models.core import Project
    if a.file.endswith(".zip"):
        with zipfile.ZipFile(a.file) as z:
            data = json.loads(z.read("data.json"))
    else:
        data = json.load(open(os.path.join(a.file, "data.json") if os.path.isdir(a.file) else a.file, encoding="utf-8"))
    try:
        with session_scope(bypass=True) as db:
            p = db.scalar(select(Project).where(func.upper(Project.code) == a.project.upper()))
            if p is None:
                sys.exit("Project not found.")
            paths: list = []
            rep = fix_imported(db, data, p, paths)
            print(f"Corrections for {p.code}:")
            for k, v in sorted(rep.items()):
                print(f"  {k:34} {v}")
            if not a.commit:
                raise TrialRun
        freed = 0
        for path in paths:  # committed: the letterhead files can go
            try:
                freed += os.path.getsize(path)
                os.remove(path)
            except OSError:
                pass
        if paths:
            print(f"  {'files deleted from disk':34} {len(paths)} ({freed // 1048576} MB)")
        print("\nDone.")
    except TrialRun:
        print("\nTRIAL RUN: nothing was written. Add --commit to apply.")


def _run(a, data):
    from app.core.db import session_scope
    from app.models.core import Project, User
    with session_scope(bypass=True) as db:
        p = db.scalar(select(Project).where(func.upper(Project.code) == a.project.upper()))
        if p is None:
            sys.exit(f"No Verqac project with the code {a.project}.")
        actor = db.scalar(select(User).where(func.lower(User.email) == a.actor.lower()))
        if actor is None:
            sys.exit(f"No Verqac account {a.actor}.")
        imp = Importer(db, data, p, actor, print)
        before = imp.existing()
        imp.run()
        after = imp.existing()
        from app.api.daily import project_progress
        prog = project_progress(db, p.id)
        print(f"\nOdoo: {data['meta'].get('db')} · project {', '.join(x['name'] for x in data.get('projects', []))}"
              f" · exported {data['meta'].get('exported_at')}")
        print(f"Verqac project {p.code}: {p.name_ar}")
        print(f"\nDeleted from Verqac: {before['records'] or 'no records'}, {before['daily_reports']} daily reports, "
              f"{before['stages']} stages, {before['locations']} locations")
        print("Imported:")
        for k, v in sorted(imp.report.items()):
            print(f"  {k:36} {v}")
        print(f"\nProgress after the import: {prog.project}% (Odoo's last snapshot: "
              f"{(data['models'].get('dr.schedule.snapshot') or [{}])[-1].get('actual_pct', '?')}%)")
        odoo = defaultdict(list)
        for c in data["models"].get("dr.schedule.cell", []):
            odoo[m2o_id(c.get("stage_id"))].append(c.get("progress") or 0)
        print(f"\n  {'stage':40} {'Odoo':>6} {'Verqac':>7}")
        for oid, st in imp.stage.items():
            o = sum(odoo[oid]) / len(odoo[oid]) if odoo.get(oid) else 0
            v = prog.stages.get(str(st.id), 0)
            print(f"  {st.name_en[:40]:40} {o:6.1f} {v:7.1f}{'  <-' if abs(o - v) > 0.5 else ''}")
        if imp.warnings:
            print(f"\nNotes ({len(imp.warnings)}):")
            for w in imp.warnings[:80]:
                print("  - " + w)
            if len(imp.warnings) > 80:
                print(f"  ... and {len(imp.warnings) - 80} more")
        if not a.commit:
            raise TrialRun
        print(f"\nImported into {p.code}. Records now: {after['records']}")


if __name__ == "__main__":
    main()
