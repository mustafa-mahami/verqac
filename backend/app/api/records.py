"""Record engine API: one set of endpoints for every record type (design doc section 4).

Permission = role x record type x action within a scope (project / disciplines).
The direction of work is fixed by the record type: its creator party writes and
submits, its responder party answers.
"""
import hashlib
import json
import re
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core import storage
from app.core.access import ProjectAccess, project_access, require
from app.core.audit import audit
from app.core.deps import Ctx, ctx
from app.models.structure import ProjectLocation, ProjectStage, ProjectStageTopic
from app.core.seed_records import (CUSTOM_FIELDS, DATE_FIELDS, DEFAULT_PERIODS, DOCUMENT_KINDS, FINANCE_TYPES, NUMBER_FIELDS,
                                   RESPONSE_FIELDS, TIMED_TYPES)
from app.core.kinds import active_codes, kind_code, kind_name, submittal_kinds
from app.core.notify import members_who_can, notify
from app.core.workcal import add_period, calendar_for
from app.models.core import Discipline, Project, ProjectMember, ProjectParty, RolePermission, User
from app.models.records import (Attachment, Record, RecordComment, RecordEvent, RecordType, StoredFile,
                                SubmittalDetails, WorkflowState, WorkflowTransition)
from app.schemas.core import DisciplineOut, SubmittalKind, UserOut
from app.schemas.records import (AssignIn, AttachmentOut, CommentIn, InboxItem, CommentOut, EventOut, RecordDetail, RecordIn,
                                 LinkedRef, LocationRef, RecordMeta, RecordPatch, RecordRow, RequiredByIn, StageRef, TopicRef, RecordTypeOut, RevisionRef, StateOut, SubmittalDetailsIO,
                                 TransitionIn, TransitionOut)

router = APIRouter(tags=["records"])

DETAIL_FIELDS = list(SubmittalDetailsIO.model_fields)


# ----------------------------------------------------------------------------- permissions
class Perms:
    """What the signed-in user may do with one record type in one project."""

    def __init__(self, c: Ctx, a: ProjectAccess, rtype: RecordType):
        self.c, self.a, self.rtype = c, a, rtype
        self.scopes: dict[str, str] = {}
        # Disciplines belong to each organization, so a contractor's "Civil" and a consultant's
        # "Civil" are different rows: scopes are matched by discipline code (C, A, E, M, P, G).
        ids = a.member.discipline_ids if a.member else []
        self.my_codes: set[str] = set(c.db.scalars(select(Discipline.code).where(Discipline.id.in_(ids)))) if ids else set()
        self._code_cache: dict[uuid.UUID, str | None] = {}
        if a.role is not None:
            for rp in c.db.scalars(select(RolePermission).where(RolePermission.role_id == a.role.id,
                                                                RolePermission.record_type.in_(
                                                                    [rtype.code] if rtype.code in FINANCE_TYPES else [rtype.code, "*"]))):
                # a specific grant for the type wins over the '*' grant
                if rp.record_type != "*" or rp.action not in self.scopes:
                    self.scopes[rp.action] = rp.scope
        # money: an organization's admin sees (and acts for) its own party's payments, whatever its project role
        if rtype.code in FINANCE_TYPES and a.party is not None and a.party.org_id in a.admin_org_ids:
            mine = ("view", "export", *(("create", "edit", "submit", "cancel", "delete") if a.party.kind == rtype.creator_party
                                        else ("respond",) if a.party.kind == rtype.responder_party else ()))
            for action in mine:
                self.scopes.setdefault(action, "project")

    @property
    def party_kind(self) -> str | None:
        return self.a.party.kind if self.a.party else None

    def in_scope(self, action: str, discipline_id: uuid.UUID | None) -> bool:
        scope = self.scopes.get(action)
        if scope is None:
            return False
        if scope == "project":
            return True
        # no disciplines on the membership = all disciplines; a record with no discipline is general
        if not self.my_codes or discipline_id is None:
            return True
        if discipline_id not in self._code_cache:
            self._code_cache[discipline_id] = self.c.db.scalar(select(Discipline.code).where(Discipline.id == discipline_id))
        return self._code_cache[discipline_id] in self.my_codes

    def can(self, action: str, rec: Record | None = None, discipline_id: uuid.UUID | None = None) -> bool:
        d = rec.discipline_id if rec is not None else discipline_id
        if not self.in_scope(action, d):
            return False
        if action in ("create", "edit", "submit", "cancel", "delete"):
            # "any": either party writes them (the archive), each its own
            if self.party_kind != self.rtype.creator_party and not (
                    self.rtype.creator_party == "any" and self.party_kind in ("contractor", "consultant")):
                return False
            if rec is not None and rec.from_party_id != self.a.party.id:
                return False
        if action == "respond" and self.party_kind != self.rtype.responder_party:
            return False
        return True


def can_see(c: Ctx, a: ProjectAccess, p: Perms, rec: Record) -> bool:
    """Visible by the role's view scope (disciplines or the whole project). A record of the user's own company
    beyond that scope is visible only when the project opens it (party_sees_all), or to whoever wrote or
    submitted it."""
    if p.can("view", rec):
        return True
    if a.party is None or rec.from_party_id != a.party.id:
        return False
    return (bool((a.project.settings or {}).get("party_sees_all", False))
            or rec.created_by == c.user.id or rec.submitted_by == c.user.id)


def _rtype(c: Ctx, code: str) -> RecordType:
    rt = c.db.scalar(select(RecordType).where(RecordType.org_id.is_(None), RecordType.code == code))
    if rt is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "record_type_not_found")
    return rt


def _load(c: Ctx, record_id: uuid.UUID, lock: bool = False) -> tuple[Record, ProjectAccess, RecordType, Perms]:
    q = select(Record).where(Record.id == record_id)
    rec = c.db.scalar(q.with_for_update() if lock else q)
    if rec is None:  # RLS: drafts of another party and other projects look the same as missing
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    a = project_access(c, rec.project_id)
    rt = c.db.get(RecordType, rec.record_type_id)
    p = Perms(c, a, rt)
    if not can_see(c, a, p, rec):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    return rec, a, rt, p


def _audit(c: Ctx, rec: Record, action: str, changes: dict, a: ProjectAccess) -> None:
    audit(c.db, entity="record", action=action, entity_id=rec.id, actor=c.user.id, org_id=a.project.owner_org_id,
          project_id=rec.project_id, changes=changes, ip=c.meta.ip, user_agent=c.meta.user_agent)


# ----------------------------------------------------------------------------- numbering
def _next_number(c: Ctx, a: ProjectAccess, rt: RecordType, discipline: Discipline | None) -> str:
    """Pattern tokens: {PRJ} {TYPE} {DISC} {SEQ:000}. The counter row is incremented in one
    statement, so two people creating at the same moment never get the same number."""
    pattern = rt.numbering_pattern
    disc = discipline.code if discipline else "G"
    scope_key = disc if "{DISC}" in pattern else ""
    seq = c.db.execute(text(
        "INSERT INTO numbering_counters (id, project_id, record_type_id, scope_key, last_value) "
        "VALUES (gen_random_uuid(), :p, :t, :k, 1) "
        "ON CONFLICT (project_id, record_type_id, scope_key) "
        "DO UPDATE SET last_value = numbering_counters.last_value + 1 RETURNING last_value"
    ), {"p": a.project.id, "t": rt.id, "k": scope_key}).scalar_one()

    def seq_token(m: re.Match) -> str:
        return str(seq).zfill(len(m.group(1)) if m.group(1) else 3)

    out = pattern.replace("{PRJ}", a.project.code).replace("{TYPE}", rt.prefix).replace("{DISC}", disc)
    return re.sub(r"\{SEQ(?::(0+))?\}", seq_token, out)


RESUBMIT_STATES = ("revise_and_resubmit", "rejected")


def periods(project, rt: RecordType) -> tuple[int, int]:
    """(consultant reply, contractor resubmission) in hours for this project and record type.
    Projects saved before periods were in hours keep their day values."""
    s = project.settings or {}
    d_reply, d_resub = DEFAULT_PERIODS.get(rt.code, (rt.review_days * 24, 7 * 24))

    def pick(hours_key: str, days_key: str, default: int) -> int:
        if rt.code in s.get(hours_key, {}):
            return int(s[hours_key][rt.code])
        if rt.code in s.get(days_key, {}):
            return int(s[days_key][rt.code]) * 24
        return default
    return pick("reply_hours", "review_days", d_reply), pick("resubmit_hours", "resubmit_days", d_resub)


def _resubmit_overdue(rec: Record) -> bool:
    return (rec.state_category in RESUBMIT_STATES and rec.resubmit_due_at is not None
            and rec.resubmitted_at is None and rec.resubmit_due_at < datetime.now(UTC))


# ----------------------------------------------------------------------------- serialisation
def _state(c: Ctx, state_id) -> WorkflowState:
    return c.db.get(WorkflowState, state_id)


def _user(c: Ctx, uid) -> UserOut | None:
    if uid is None:
        return None
    u = c.db.get(User, uid)
    return UserOut.model_validate(u) if u else None


def _overdue(rec: Record) -> bool:
    return rec.state_category == "submitted" and rec.due_at is not None and rec.due_at < datetime.now(UTC)


def _details(c: Ctx, rec: Record) -> SubmittalDetailsIO:
    d = c.db.get(SubmittalDetails, rec.id)
    return SubmittalDetailsIO.model_validate({f: getattr(d, f) for f in DETAIL_FIELDS}) if d else SubmittalDetailsIO()


def _latest_rev(c: Ctx, rec: Record) -> int:
    return c.db.scalar(select(func.max(Record.rev_no)).where(Record.revision_group_id == rec.revision_group_id))


def _checklists_on(project) -> bool:
    return bool((project.settings or {}).get("checklists", False))


def _topic_checklist(c: Ctx, rec: Record, rt: RecordType) -> list[dict]:
    if rt.code != "inspection" or not rec.topic_id or not _checklists_on(c.db.get(Project, rec.project_id)):
        return []
    topic = c.db.get(ProjectStageTopic, rec.topic_id)
    return [{"ar": x["ar"], "en": x["en"], "result": None, "note": None} for x in (topic.checklist if topic else [])]


def _checklist(c: Ctx, rec: Record, rt: RecordType) -> list[dict]:
    """Fixed into the request at submission; a draft shows what its topic will be checked against."""
    if rec.checklist is not None:
        # a waiting request whose project switched checklists off is answered without one
        unanswered = not any(x.get("result") for x in rec.checklist)
        return [] if unanswered and not _checklists_on(c.db.get(Project, rec.project_id)) else rec.checklist
    return _topic_checklist(c, rec, rt)


def _answer_checklist(rec: Record, answers, to: WorkflowState, on: bool) -> None:
    """Every line needs a result to answer; a plain acceptance cannot carry a non-conforming line.
    If the project switched checklists off after this request was submitted, an answer without one drops it."""
    if not rec.checklist:
        return
    if not on and not answers:
        rec.checklist = None
        return
    answers = answers or []
    if len(answers) != len(rec.checklist) or any(x.result is None for x in answers):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "checklist_incomplete")
    if to.category == "approved" and any(x.result == "nc" for x in answers):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "checklist_nonconforming")
    rec.checklist = [{"ar": line["ar"], "en": line["en"], "result": x.result, "note": (x.note or "").strip() or None}
                     for line, x in zip(rec.checklist, answers)]


def editable_returned(rt: RecordType, rec: Record) -> bool:
    """A daily report returned for correction is edited and resubmitted as it is (no new revision)."""
    return rt.code == "daily_report" and rec.state_category == "revise_and_resubmit"


def _detail(c: Ctx, rec: Record, a: ProjectAccess, rt: RecordType, p: Perms) -> RecordDetail:
    state = _state(c, rec.state_id)
    trans = []
    for t in c.db.scalars(select(WorkflowTransition).where(WorkflowTransition.from_state_id == rec.state_id)
                          .order_by(WorkflowTransition.sort)):
        if p.can(t.permission, rec):
            trans.append(TransitionOut.model_validate(t))
    party = c.db.get(ProjectParty, rec.from_party_id)
    parties = {pp.id: pp.kind for pp in c.db.scalars(select(ProjectParty).where(ProjectParty.project_id == rec.project_id))}

    events = []
    for e in c.db.scalars(select(RecordEvent).where(RecordEvent.record_id == rec.id).order_by(RecordEvent.at, RecordEvent.id)):
        events.append(EventOut(id=e.id, action=e.action, to_state=StateOut.model_validate(_state(c, e.to_state_id))
                               if e.to_state_id else None, actor=_user(c, e.actor_id), on_behalf_of=_user(c, e.on_behalf_of),
                               channel=e.channel, comment=e.comment, stamp=e.stamp, at=e.at))
    comments = [CommentOut(id=cm.id, author=_user(c, cm.author_id), party_kind=parties.get(cm.party_id, ""),
                           visibility=cm.visibility, body=cm.body, created_at=cm.created_at)
                for cm in c.db.scalars(select(RecordComment).where(RecordComment.record_id == rec.id)
                                       .order_by(RecordComment.created_at))]
    atts = [AttachmentOut(id=at.id, file_id=f.id, filename=f.filename, content_type=f.content_type, size=f.size,
                          kind=at.kind, party_kind=parties.get(at.party_id, ""), caption=at.caption,
                          can_edit=at.party_id == (a.party.id if a.party else None) and a.member is not None,
                          created_at=at.created_at)
            for at, f in c.db.execute(select(Attachment, StoredFile).join(StoredFile, StoredFile.id == Attachment.file_id)
                                      .where(Attachment.record_id == rec.id).order_by(Attachment.created_at))]
    revs = [RevisionRef(id=r.id, rev_no=r.rev_no, state=StateOut.model_validate(_state(c, r.state_id)))
            for r in c.db.scalars(select(Record).where(Record.revision_group_id == rec.revision_group_id)
                                  .order_by(Record.rev_no))]
    disc = c.db.get(Discipline, rec.discipline_id) if rec.discipline_id else None

    is_draft = rec.state_category == "draft"
    attach = []
    if (is_draft or editable_returned(rt, rec)) and p.can("edit", rec):
        attach.append("submission")
    if rec.state_category == "submitted" and p.can("respond", rec):
        attach.append("response")
    if rec.state_category == "responded" and p.can("submit", rec):
        attach.append("photo")  # the issuer's photos when verifying (an NCR's corrective action on site)
    if rec.state_category not in ("draft", "submitted", "cancelled") and (p.can("respond", rec) or p.can("submit", rec)):
        attach.append("signed")  # the paper copy signed by hand, added once answered (also to records brought from Odoo)
    can_assign = bool(rec.state_category == "submitted" and a.role and a.role.act_on_behalf and p.can("respond", rec))
    candidates = []
    if can_assign:
        candidates = [_user(c, m.user_id) for m, r in _responders(c, rec, rt) if not r.act_on_behalf]
    no_engineer = False
    if is_draft:
        no_engineer = not any(not r.act_on_behalf for _, r in _responders(c, rec, rt))
    can_revise = (rt.has_revisions and not is_draft and rec.rev_no == _latest_rev(c, rec)
                  and (rec.state_category in ("revise_and_resubmit", "rejected", "approved_as_noted", "cancelled")
                       or (rt.code == "programme" and rec.state_category == "approved"))  # an updated programme
                  and p.can("create", discipline_id=rec.discipline_id))
    return RecordDetail(imported=rec.legacy_ref is not None,
        id=rec.id, project_id=rec.project_id, record_type=RecordTypeOut.model_validate(rt), number=rec.number,
        rev_no=rec.rev_no, title=rec.title, description=rec.description,
        discipline=DisciplineOut.model_validate(disc) if disc else None, state=StateOut.model_validate(state),
        from_party_kind=party.kind, created_by=_user(c, rec.created_by), created_at=rec.created_at,
        submitted_by=_user(c, rec.submitted_by), submitted_at=rec.submitted_at, due_at=rec.due_at,
        overdue=_overdue(rec), answered_by=_user(c, rec.answered_by),
        answered_on_behalf_of=_user(c, rec.answered_on_behalf_of), answered_at=rec.answered_at,
        response_comment=rec.response_comment, resubmit_due_at=rec.resubmit_due_at,
        resubmitted_at=rec.resubmitted_at, resubmit_overdue=_resubmit_overdue(rec), required_by=rec.required_by, required_by_note=rec.required_by_note,
        can_set_required_by=_can_set_required_by(rec, a, p), details=(det := _details(c, rec)),
        submittal_kind_name=kind_name(a.project, det.submittal_kind), transitions=trans,
        stage=(place := _place_out(c, rec))[0], all_locations=rec.all_locations, locations=place[1], topic=place[2],
        requested_for=rec.requested_for, performed_at=rec.performed_at,
        linked=(links := _linked_out(c, a, rec, rt))[0], link_warning=links[1],
        checklist=_checklist(c, rec, rt), custom={k: v for k, v in (rec.custom or {}).items()
                                                  if k in CUSTOM_FIELDS.get(rt.code, ())},
        can_edit=is_draft and p.can("edit", rec), can_revise=can_revise, can_attach=attach,
        can_act_on_behalf=bool(a.role and a.role.act_on_behalf and p.can("respond", rec)),
        assigned_to=_user(c, rec.assigned_to), can_assign=can_assign, assign_candidates=candidates,
        addressed_to=_addressed_to(c, rec, rt),
        no_discipline_engineer=no_engineer,
        events=events, comments=comments, attachments=atts, revisions=revs,
    )


def _responder_party(c: Ctx, rec: Record, rt: RecordType) -> uuid.UUID | None:
    if rec.to_party_id is None:  # the responder joined the project after the record was written
        rec.to_party_id = c.db.scalar(select(ProjectParty.id).where(ProjectParty.project_id == rec.project_id,
                                                                    ProjectParty.kind == rt.responder_party,
                                                                    ProjectParty.status == "active"))
    return rec.to_party_id


def _responders(c: Ctx, rec: Record, rt: RecordType) -> list:
    party = _responder_party(c, rec, rt)
    return members_who_can(c, rec.project_id, party, rt, "respond", rec.discipline_id) if party else []


ROUTING_MODES = ("discipline", "manager", "choose")


def type_enabled(project, code: str) -> bool:
    """Each project shows the request types it uses (settings "types"; absent = all)."""
    if code == "programme":  # part of the progress tab, not a register of its own
        return True
    types = (project.settings or {}).get("types")
    return types is None or code in types


def routing(project, rt: RecordType) -> str:
    """Who a request goes to, per project and record type:
    discipline - the consultant engineers of its discipline (the PM still sees and can answer everything);
    manager    - the consultant PM, who passes it on;
    choose     - the contractor picks the addressee when writing the request."""
    mode = (project.settings or {}).get("routing", {}).get(rt.code, "discipline")
    return mode if mode in ROUTING_MODES else "discipline"


def _addressed_to(c: Ctx, rec: Record, rt: RecordType) -> list[UserOut]:
    """The person(s) the request is addressed to, as printed on it."""
    if rec.assigned_to:
        return [_user(c, rec.assigned_to)]
    resp = _responders(c, rec, rt)
    managers = [m.user_id for m, r in resp if r.act_on_behalf]
    engineers = [m.user_id for m, r in resp if not r.act_on_behalf]
    project = c.db.get(Project, rec.project_id)
    ids = managers if routing(project, rt) == "manager" or not engineers else engineers
    return [u for u in (_user(c, i) for i in dict.fromkeys(ids)) if u]


def _addressees(c: Ctx, project_id: uuid.UUID, rt: RecordType, discipline_id) -> list:
    party = c.db.scalar(select(ProjectParty.id).where(ProjectParty.project_id == project_id,
                                                      ProjectParty.kind == rt.responder_party,
                                                      ProjectParty.status == "active"))
    if party is None:
        return []
    rows = members_who_can(c, project_id, party, rt, "respond", discipline_id)
    rows.sort(key=lambda mr: (mr[1].act_on_behalf, ))  # engineers first, then the PM
    return [u for u in (_user(c, m.user_id) for m, _ in rows) if u]


def _check_addressee(c: Ctx, a: ProjectAccess, rt: RecordType, discipline_id, user_id):
    if user_id is None:
        return None
    if user_id not in {u.id for u in _addressees(c, a.project.id, rt, discipline_id)}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_addressee")
    return user_id


def _check_discipline(c: Ctx, a: ProjectAccess, discipline_id: uuid.UUID | None) -> Discipline | None:
    if discipline_id is None:
        return None
    d = c.db.get(Discipline, discipline_id)
    if d is None or a.party is None or d.org_id != a.party.org_id:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "discipline_not_in_org")
    return d


# ----------------------------------------------------------------------------- endpoints
@router.get("/record-types", response_model=list[RecordTypeOut])
def list_types(c: Ctx = Depends(ctx)):
    return c.db.scalars(select(RecordType).where(RecordType.org_id.is_(None)).order_by(RecordType.sort)).all()


@router.get("/projects/{project_id}/records/meta", response_model=RecordMeta)
def records_meta(project_id: uuid.UUID, type: str = Query("submittal"), c: Ctx = Depends(ctx)):
    """What the screens need before showing a register: can I create, and with which disciplines."""
    a = project_access(c, project_id)
    rt = _rtype(c, type)
    p = Perms(c, a, rt)
    discs = []
    if a.party is not None and a.party.org_id:
        discs = c.db.scalars(select(Discipline).where(Discipline.org_id == a.party.org_id, Discipline.is_active)
                             .order_by(Discipline.sort)).all()
        if p.my_codes:
            discs = [d for d in discs if d.code in p.my_codes]
    on = type_enabled(a.project, rt.code)
    return RecordMeta(record_type=RecordTypeOut.model_validate(rt),
                      can_create=on and a.party is not None and p.can("create"), enabled=on,
                      disciplines=[DisciplineOut.model_validate(d) for d in discs],
                      party_kind=a.party.kind if a.party else None,
                      submittal_kinds=[SubmittalKind(**k) for k in submittal_kinds(a.project) if k["active"]],
                      states=[StateOut.model_validate(x) for x in c.db.scalars(
                          select(WorkflowState).where(WorkflowState.workflow_id == rt.workflow_id).order_by(WorkflowState.sort))],
                      link_submittals=_links_on(a.project), reply_hours=periods(a.project, rt)[0],
                      routing=routing(a.project, rt))


@router.get("/projects/{project_id}/addressees", response_model=list[UserOut])
def addressees(project_id: uuid.UUID, type: str = Query("submittal"), discipline_id: uuid.UUID | None = None,
               c: Ctx = Depends(ctx)):
    """Who a request of this type and discipline can be addressed to (for the "choose" routing)."""
    a = project_access(c, project_id)
    return _addressees(c, project_id, _rtype(c, type), discipline_id)


@router.get("/projects/{project_id}/link-candidates", response_model=list[LinkedRef])
def link_candidates(project_id: uuid.UUID, stage_id: uuid.UUID | None = None, c: Ctx = Depends(ctx)):
    """Submittals an inspection can rely on: the latest revision of each number, approved ones first,
    those of the given stage before the others."""
    a = project_access(c, project_id)
    sub = _rtype(c, "submittal")
    rows = c.db.scalars(select(Record).where(Record.project_id == project_id, Record.record_type_id == sub.id,
                                             Record.state_category != "cancelled")
                        .order_by(Record.number, Record.rev_no)).all()
    latest: dict = {}
    for r in rows:
        latest[r.revision_group_id] = r
    out = [LinkedRef(id=r.id, number=r.number, rev_no=r.rev_no, title=r.title, stage_id=r.stage_id,
                     state=StateOut.model_validate(_state(c, r.state_id))) for r in latest.values()]
    out.sort(key=lambda x: (stage_id is not None and x.stage_id != stage_id, x.state.category not in APPROVED, x.number))
    return out


@router.get("/projects/{project_id}/records", response_model=list[RecordRow])
def list_records(project_id: uuid.UUID, type: str = Query("submittal"), all_revisions: bool = False,
                 c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    rt = _rtype(c, type)
    p = Perms(c, a, rt)
    q = select(Record).where(Record.project_id == project_id, Record.record_type_id == rt.id)
    rows = c.db.scalars(q.order_by(Record.number, Record.rev_no)).all()
    counts: dict[uuid.UUID, int] = {}
    latest: dict[uuid.UUID, Record] = {}
    for r in rows:
        counts[r.revision_group_id] = counts.get(r.revision_group_id, 0) + 1
        latest[r.revision_group_id] = r  # ordered by rev_no: the last one wins
    keep = rows if all_revisions else list(latest.values())
    out = []
    discs = {d.id: d for d in c.db.scalars(select(Discipline).where(
        Discipline.id.in_({r.discipline_id for r in keep if r.discipline_id})))}
    kinds = dict(c.db.execute(select(SubmittalDetails.record_id, SubmittalDetails.submittal_kind)
                              .where(SubmittalDetails.record_id.in_([r.id for r in keep]))).all())
    labs = {}
    if rt.code == "test":
        from app.models.lab import LabResult
        labs = {x.record_id: x for x in c.db.scalars(select(LabResult).where(LabResult.record_id.in_([r.id for r in keep])))}
    for r in keep:
        if not can_see(c, a, p, r):
            continue
        d = discs.get(r.discipline_id)
        out.append(RecordRow(id=r.id, number=r.number, rev_no=r.rev_no, title=r.title,
                             state=StateOut.model_validate(_state(c, r.state_id)),
                             discipline=DisciplineOut.model_validate(d) if d else None,
                             submitted_at=r.submitted_at, due_at=r.due_at, answered_at=r.answered_at,
                             overdue=_overdue(r), revisions=counts[r.revision_group_id], required_by=r.required_by,
                             resubmit_due_at=r.resubmit_due_at if r.resubmitted_at is None else None,
                             resubmit_overdue=_resubmit_overdue(r),
                             submittal_kind=kind_code(a.project, kinds.get(r.id)), submittal_kind_name=kind_name(a.project, kinds.get(r.id)),
                             stage_id=r.stage_id, topic_id=r.topic_id, all_locations=r.all_locations,
                             requested_for=r.requested_for, performed_at=r.performed_at,
                             location_ids=r.location_ids or [],
                             lab_result=labs[r.id].result if r.id in labs else None,
                             lab_decision=labs[r.id].decision if r.id in labs else None,
                             custom={k: v for k, v in (r.custom or {}).items() if k in LIST_FIELDS.get(rt.code, ())}))
    return out


def _can_set_required_by(rec: Record, a: ProjectAccess, p: "Perms") -> bool:
    """The author side sets it while the record waits for an answer (draft or submitted)."""
    return (a.party is not None and rec.from_party_id == a.party.id and rec.state_category in ("draft", "submitted")
            and (p.can("edit", rec) or p.can("submit", rec)))


def _check_place(c: Ctx, a: ProjectAccess, stage_id, all_locations: bool, location_ids,
                 current: Record | None = None, topic_id=None) -> tuple:
    """Validate a stage, its topic and locations for this project;
    returns (stage_id, all_locations, location_ids, topic_id).
    A stage done for the whole project ("whole" scope) always covers all locations."""
    topic = None
    if topic_id is not None:
        topic = c.db.get(ProjectStageTopic, topic_id)
        if topic is None or topic.project_id != a.project.id or (stage_id and topic.stage_id != stage_id) or (
                not topic.is_active and (current is None or current.topic_id != topic_id)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_topic")
        stage_id = topic.stage_id
    stage = None
    if stage_id is not None:
        stage = c.db.get(ProjectStage, stage_id)
        if stage is None or stage.project_id != a.project.id or (
                not stage.is_active and (current is None or current.stage_id != stage_id)):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_stage")
    ids = list(dict.fromkeys(location_ids or []))
    if stage is not None and stage.scope == "whole":
        all_locations = True
    tid = topic.id if topic else None
    if all_locations:
        return stage_id, True, None, tid
    if ids:
        known = {r.id: r for r in c.db.scalars(select(ProjectLocation).where(ProjectLocation.id.in_(ids)))}
        before = set(current.location_ids or []) if current is not None else set()
        for i in ids:
            r = known.get(i)
            if r is None or r.project_id != a.project.id or (not r.is_active and i not in before):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_location")
    return stage_id, False, ids or None, tid


def _title(title: str | None, topic_id, c: Ctx) -> str:
    """The typed subject, or the chosen topic's name when nothing was typed."""
    t = (title or "").strip()
    if len(t) >= 2:
        return t
    if topic_id:
        return c.db.get(ProjectStageTopic, topic_id).name_ar
    raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "title_required")


def _place_out(c: Ctx, rec: Record) -> tuple:
    stage = c.db.get(ProjectStage, rec.stage_id) if rec.stage_id else None
    topic = c.db.get(ProjectStageTopic, rec.topic_id) if rec.topic_id else None
    locs = []
    if rec.location_ids:
        rows = {r.id: r for r in c.db.scalars(select(ProjectLocation).where(
            ProjectLocation.project_id == rec.project_id))}
        many = sum(1 for r in rows.values() if r.kind == "group") > 1
        for i in rec.location_ids:
            r = rows.get(i)
            if r is None:
                continue
            g = rows.get(r.parent_id) if r.parent_id else None
            ar, en = r.name_ar, r.name_en
            if g is not None and many:
                ar, en = f"{g.name_ar} – {ar}", f"{g.name_en} – {en}"
            locs.append(LocationRef(id=r.id, kind=r.kind, name_ar=ar, name_en=en))
    return (StageRef(id=stage.id, name_ar=stage.name_ar, name_en=stage.name_en, scope=stage.scope) if stage else None,
            locs, TopicRef(id=topic.id, name_ar=topic.name_ar, name_en=topic.name_en) if topic else None)


def _links_on(project) -> bool:
    return bool((project.settings or {}).get("link_submittals", False))


APPROVED = ("approved", "approved_as_noted")


def _check_links(c: Ctx, a: ProjectAccess, ids) -> list | None:
    """Linked records must be submittals of this project."""
    ids = list(dict.fromkeys(ids or []))
    if not ids:
        return None
    sub = c.db.scalar(select(RecordType.id).where(RecordType.org_id.is_(None), RecordType.code == "submittal"))
    found = set(c.db.scalars(select(Record.id).where(Record.id.in_(ids), Record.project_id == a.project.id,
                                                     Record.record_type_id == sub)))
    if found != set(ids):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_link")
    return ids


def _linked_out(c: Ctx, a: ProjectAccess, rec: Record, rt: RecordType) -> tuple[list, str | None]:
    refs = []
    for r in c.db.scalars(select(Record).where(Record.id.in_(rec.linked_ids or []))).all():
        refs.append(LinkedRef(id=r.id, number=r.number, rev_no=r.rev_no, title=r.title, stage_id=r.stage_id,
                              state=StateOut.model_validate(_state(c, r.state_id))))
    warning = None
    if rt.code in TIMED_TYPES and _links_on(a.project):
        if not refs:
            warning = "no_link"
        elif any(x.state.category not in APPROVED for x in refs):
            warning = "not_approved"
    return refs, warning


LIST_FIELDS = {"document": ("kind", "direction", "doc_date", "sender", "recipient", "their_ref"),
               "payment": ("claimed_gross", "claimed", "certified", "payable")}
CHOICES = {"impact": ("none", "cost", "time", "cost_time"), "severity": ("minor", "major"),
           "kind": DOCUMENT_KINDS, "direction": ("incoming", "outgoing", "internal")}


def _check_custom(rt: RecordType, old: dict, new: dict, responder: bool = False) -> dict:
    """The type's extra fields only; text is trimmed, empty removes the field. Amounts are numbers, periods dates;
    the fields of the answer (a payment's certified amounts) are written by the answering party only."""
    allowed = RESPONSE_FIELDS.get(rt.code, ()) if responder else \
        tuple(k for k in CUSTOM_FIELDS.get(rt.code, ()) if k not in RESPONSE_FIELDS.get(rt.code, ()))
    out = {k: v for k, v in old.items()}
    for k, v in (new or {}).items():
        if k not in allowed:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_field")
        v = (v or "").strip()
        if len(v) > 4000 or (v and k in CHOICES and v not in CHOICES[k]):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_field")
        if v and k in NUMBER_FIELDS:
            try:
                n = float(v.replace(",", ""))
            except ValueError:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_amount") from None
            if n < 0 or n > 1e12:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_amount")
            v = f"{round(n, 2):g}" if n < 1e15 else str(n)
        if v and k in DATE_FIELDS:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_field") from None
        if v:
            out[k] = v
        else:
            out.pop(k, None)
    return out


def _check_kind(a, code: str | None) -> None:
    if code is not None and code not in active_codes(a.project):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_kind")


@router.post("/projects/{project_id}/records", response_model=RecordDetail, status_code=201)
def create_record(project_id: uuid.UUID, body: RecordIn, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    rt = _rtype(c, body.record_type)
    p = Perms(c, a, rt)
    require(a.party is not None and p.can("create", discipline_id=body.discipline_id), "cannot_create")
    require(type_enabled(a.project, rt.code), "type_disabled")
    disc = _check_discipline(c, a, body.discipline_id)
    initial = c.db.scalar(select(WorkflowState).where(WorkflowState.workflow_id == rt.workflow_id,
                                                      WorkflowState.is_initial))
    number = body.number.strip() if body.number else _next_number(c, a, rt, disc)
    stage_id, all_locs, loc_ids, topic_id = _check_place(c, a, body.stage_id, body.all_locations, body.location_ids,
                                                         topic_id=body.topic_id)
    title = _title(body.title, topic_id, c)
    responder = c.db.scalar(select(ProjectParty.id).where(ProjectParty.project_id == project_id,
                                                          ProjectParty.kind == rt.responder_party,
                                                          ProjectParty.status != "removed"))
    rec = Record(project_id=project_id, record_type_id=rt.id, number=number, rev_no=0,
                 revision_group_id=uuid.uuid4(), discipline_id=body.discipline_id, title=title,
                 description=body.description, state_id=initial.id, state_category=initial.category,
                 from_party_id=a.party.id, to_party_id=responder, created_by=c.user.id,
                 required_by=body.required_by, required_by_note=(body.required_by_note or "").strip() or None,
                 stage_id=stage_id, all_locations=all_locs, location_ids=loc_ids, topic_id=topic_id,
                 requested_for=body.requested_for, linked_ids=_check_links(c, a, body.linked_ids),
                 assigned_to=_check_addressee(c, a, rt, body.discipline_id, body.addressed_to),
                 custom=_check_custom(rt, {}, body.custom))
    c.db.add(rec)
    try:
        c.db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "number_taken") from None
    _check_kind(a, body.details.submittal_kind)
    c.db.add(SubmittalDetails(record_id=rec.id, **body.details.model_dump()))
    c.db.add(RecordEvent(record_id=rec.id, action="create", to_state_id=initial.id, actor_id=c.user.id))
    _audit(c, rec, "create", {"number": number, "type": rt.code}, a)
    c.db.flush()
    return _detail(c, rec, a, rt, p)


@router.get("/records/{record_id}", response_model=RecordDetail)
def get_record(record_id: uuid.UUID, c: Ctx = Depends(ctx)):
    rec, a, rt, p = _load(c, record_id)
    return _detail(c, rec, a, rt, p)


@router.patch("/records/{record_id}", response_model=RecordDetail)
def update_record(record_id: uuid.UUID, body: RecordPatch, c: Ctx = Depends(ctx)):
    rec, a, rt, p = _load(c, record_id, lock=True)
    require(rec.state_category == "draft", "locked_after_submit")
    require(p.can("edit", rec), "cannot_edit")
    changes: dict[str, Any] = {}
    if "title" in body.model_fields_set or "topic_id" in body.model_fields_set:
        tid = body.topic_id if "topic_id" in body.model_fields_set else rec.topic_id
        if tid is not None and c.db.get(ProjectStageTopic, tid) is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_topic")
        body.title = _title(body.title, tid, c)
    for f in ("title", "description"):
        v = getattr(body, f)
        if v is not None and v != getattr(rec, f):
            changes[f] = [getattr(rec, f), v]
            setattr(rec, f, v)
    if "discipline_id" in body.model_fields_set and body.discipline_id != rec.discipline_id:
        _check_discipline(c, a, body.discipline_id)
        changes["discipline_id"] = [str(rec.discipline_id), str(body.discipline_id)]
        rec.discipline_id = body.discipline_id
    if {"stage_id", "topic_id", "all_locations", "location_ids"} & body.model_fields_set:
        place = _check_place(c, a, body.stage_id, bool(body.all_locations), body.location_ids, current=rec,
                             topic_id=body.topic_id)
        if place != (rec.stage_id, rec.all_locations, rec.location_ids, rec.topic_id):
            changes["place"] = [str(rec.stage_id), str(place[0])]
            rec.stage_id, rec.all_locations, rec.location_ids, rec.topic_id = place
    if "addressed_to" in body.model_fields_set and body.addressed_to != rec.assigned_to:
        rec.assigned_to = _check_addressee(c, a, rt, rec.discipline_id, body.addressed_to)
        changes["addressed_to"] = str(body.addressed_to)
    if body.custom is not None:
        custom = _check_custom(rt, rec.custom or {}, body.custom)
        if custom != (rec.custom or {}):
            changes["custom"] = [rec.custom, custom]
            rec.custom = custom
    if "requested_for" in body.model_fields_set and body.requested_for != rec.requested_for:
        changes["requested_for"] = [str(rec.requested_for), str(body.requested_for)]
        rec.requested_for = body.requested_for
    if body.linked_ids is not None:
        links = _check_links(c, a, body.linked_ids)
        if links != rec.linked_ids:
            changes["linked_ids"] = [len(rec.linked_ids or []), len(links or [])]
            rec.linked_ids = links
    if body.details is not None:
        d = c.db.get(SubmittalDetails, rec.id) or SubmittalDetails(record_id=rec.id)
        if body.details.submittal_kind != d.submittal_kind:  # keeping an old or deactivated kind is fine
            _check_kind(a, body.details.submittal_kind)
        for f, v in body.details.model_dump().items():
            if getattr(d, f) != v:
                changes[f] = [str(getattr(d, f)), str(v)]
                setattr(d, f, v)
        c.db.add(d)
    rec.updated_at = datetime.now(UTC)
    if changes:
        _audit(c, rec, "edit", changes, a)
    c.db.flush()
    return _detail(c, rec, a, rt, p)


def _stamp(c: Ctx, rec: Record, state: WorkflowState) -> str:
    """Fingerprint of what was answered: data, files and the answer itself (design doc section 7)."""
    files = c.db.scalars(select(StoredFile.sha256).join(Attachment, Attachment.file_id == StoredFile.id)
                         .where(Attachment.record_id == rec.id).order_by(StoredFile.sha256)).all()
    payload = {"number": rec.number, "rev": rec.rev_no, "title": rec.title, "description": rec.description,
               "details": _details(c, rec).model_dump(mode="json"), "files": files, "state": state.code,
               "comment": rec.response_comment, "answered_at": rec.answered_at.astimezone(UTC).isoformat(),
               "answered_by": str(rec.answered_by), "on_behalf_of": str(rec.answered_on_behalf_of)}
    # stage and locations join the fingerprint only when set, so earlier stamps still verify
    if rec.stage_id:
        payload["stage"] = str(rec.stage_id)
    if rec.topic_id:
        payload["topic"] = str(rec.topic_id)
    if rec.performed_at:
        payload["performed_at"] = rec.performed_at.astimezone(UTC).isoformat()
    if rec.checklist:
        payload["checklist"] = [[x["ar"], x["result"], x["note"]] for x in rec.checklist]
    if rec.linked_ids:
        payload["linked"] = sorted(str(i) for i in rec.linked_ids)
    if rec.all_locations or rec.location_ids:
        payload["locations"] = "all" if rec.all_locations else sorted(str(i) for i in rec.location_ids)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@router.post("/records/{record_id}/transitions", response_model=RecordDetail)
def transition(record_id: uuid.UUID, body: TransitionIn, bg: BackgroundTasks, c: Ctx = Depends(ctx)):
    rec, a, rt, p = _load(c, record_id, lock=True)
    t = c.db.scalar(select(WorkflowTransition).where(WorkflowTransition.from_state_id == rec.state_id,
                                                     WorkflowTransition.action == body.action))
    if t is None:
        # e.g. two people answered at the same time: the second sees the record already moved on
        raise HTTPException(status.HTTP_409_CONFLICT, "transition_not_available")
    require(p.can(t.permission, rec), "cannot_" + t.permission)
    comment = (body.comment or "").strip() or None
    if t.requires_comment and not comment:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "comment_required")

    on_behalf = None
    if body.on_behalf_of and body.on_behalf_of != c.user.id:
        require(t.effect == "respond" and a.role is not None and a.role.act_on_behalf, "cannot_act_on_behalf")
        target = c.db.scalar(select(ProjectMember).where(ProjectMember.project_id == rec.project_id,
                                                         ProjectMember.user_id == body.on_behalf_of,
                                                         ProjectMember.party_id == a.party.id,
                                                         ProjectMember.is_active))
        require(target is not None, "on_behalf_not_in_party")
        on_behalf = body.on_behalf_of

    to = c.db.get(WorkflowState, t.to_state_id)
    now = datetime.now(UTC)
    if rt.code == "payment":
        cu = rec.custom or {}
        if t.effect == "submit" and not (cu.get("claimed_gross") and cu.get("claimed")):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "payment_claim_required")
        if t.effect == "submit" and float(cu["claimed"]) > float(cu["claimed_gross"]):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "net_exceeds_claim")
        if to.category == "approved" and not (cu.get("certified") and cu.get("payable")):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "payment_amounts_required")
        if to.category == "approved":
            _payable_within(cu)
    if rt.code == "document" and to.category == "approved":  # filed: dated by the document itself
        d = (rec.custom or {}).get("doc_date")
        rec.submitted_by = c.user.id
        rec.submitted_at = datetime.combine(date.fromisoformat(d), time(12, 0), calendar_for(c.db, a.project).tz) if d else now
    if t.effect == "submit" and rt.code == "daily_report":
        from app.api.daily import check_works
        check_works(c.db, rec)
    if t.effect == "submit" and rt.code == "test":
        from app.models.lab import LabResult
        lab = c.db.get(LabResult, rec.id)
        if lab is None or not lab.lines or not any(x.get("value") is not None or x.get("text") for x in lab.lines):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "lab_results_required")
    if t.effect == "submit":
        rec.submitted_by, rec.submitted_at = c.user.id, now
        # the reply clock starts at the later of now and the time the inspection was asked for
        start = max(now, rec.requested_for) if rec.requested_for else now
        rec.due_at = add_period(start, periods(a.project, rt)[0], calendar_for(c.db, a.project))
        if rec.rev_no > 0:  # this revision answers the previous one's request to resubmit
            prev = c.db.scalar(select(Record).where(Record.revision_group_id == rec.revision_group_id,
                                                    Record.rev_no == rec.rev_no - 1))
            if prev is not None and prev.resubmitted_at is None:
                prev.resubmitted_at = now
        rec.checklist = _topic_checklist(c, rec, rt) or None
    elif t.effect == "respond":
        when = now
        if body.answered_on:  # an answer given on paper before the record came over from Odoo
            # imported records answered on paper, and payment applications certified before they were entered
            require(rec.legacy_ref is not None or rt.code == "payment", "answered_on_imported_only")
            local = datetime.combine(body.answered_on, time(12, 0), calendar_for(c.db, a.project).tz)
            old_ipc = rt.code == "payment" and rec.legacy_ref is None  # entered after it was certified on paper
            if body.answered_on > now.astimezone(local.tzinfo).date() or (
                    not old_ipc and rec.submitted_at and local < rec.submitted_at - timedelta(days=1)):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "answered_on_range")
            when = local if old_ipc else max(local, rec.submitted_at) if rec.submitted_at else local
        rec.answered_by, rec.answered_at, rec.answered_on_behalf_of = c.user.id, when, on_behalf
        rec.response_comment = comment
        if rt.code in TIMED_TYPES:
            if body.performed_at and body.performed_at > now + timedelta(minutes=5):
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "performed_in_future")
            rec.performed_at = body.performed_at or when
            _answer_checklist(rec, body.checklist, to, _checklists_on(a.project))
        if to.category in RESUBMIT_STATES:
            rec.resubmit_due_at = add_period(now, periods(a.project, rt)[1], calendar_for(c.db, a.project))
    rec.state_id, rec.state_category, rec.updated_at = to.id, to.category, now
    c.db.flush()
    if rt.code == "daily_report" and to.category == "approved":
        from app.api.daily import apply_progress
        apply_progress(c.db, rec)  # the approved report sets the progress of its cells
    stamp = _stamp(c, rec, to) if t.effect == "respond" else None
    ev = RecordEvent(record_id=rec.id, action=t.action, from_state_id=t.from_state_id, to_state_id=to.id,
                     actor_id=c.user.id, on_behalf_of=on_behalf, comment=comment, stamp=stamp)
    if t.effect == "respond" and body.answered_on:
        ev.at = rec.answered_at  # the history shows the real day; the audit log keeps when it was entered
    c.db.add(ev)
    _audit(c, rec, "transition", {"action": t.action, "to": to.code, "on_behalf_of": str(on_behalf) if on_behalf else None,
                                  "answered_on": body.answered_on.isoformat() if body.answered_on else None}, a)
    c.db.flush()
    _notify_transition(c, bg, a.project, rec, rt, t, to, comment)
    return _detail(c, rec, a, rt, p)


def _notify_transition(c: Ctx, bg: BackgroundTasks, project: Project, rec: Record, rt: RecordType,
                       t: WorkflowTransition, to: WorkflowState, comment: str | None) -> None:
    head = f"{rec.number} R{rec.rev_no}"
    if t.effect == "submit" or (t.effect == "cancel" and t.from_state_id != _initial_id(c, rt)):
        responders = _responders(c, rec, rt)
        to_manager = rec.assigned_to is None and routing(project, rt) == "manager"
        users = {m.user_id for m, r in responders
                 if r.act_on_behalf or (not to_manager and (rec.assigned_to is None or m.user_id == rec.assigned_to))}
        ar = f"{rt.name_ar} {head}: " + ("بانتظار ردك" if t.effect == "submit" else "سُحب وأُلغي")
        en = f"{rt.name_en} {head}: " + ("awaiting your reply" if t.effect == "submit" else "withdrawn")
        notify(c, bg, project=project, rec=rec, event=t.action, user_ids=users, title_ar=ar, title_en=en,
               body=rec.title)
    elif t.effect == "none":  # e.g. NCR verified and closed: both sides hear of it
        users = {rec.created_by, rec.submitted_by, rec.answered_by}
        users |= {m.user_id for m, _ in _responders(c, rec, rt)}
        notify(c, bg, project=project, rec=rec, event=t.action, user_ids=users,
               title_ar=f"{rt.name_ar} {head}: {to.name_ar}", title_en=f"{rt.name_en} {head}: {to.name_en}",
               body=comment or rec.title)
    elif t.effect == "respond":
        users = {rec.created_by, rec.submitted_by}
        users |= {m.user_id for m, r in members_who_can(c, rec.project_id, rec.from_party_id, rt, "create",
                                                         rec.discipline_id) if r.manage_project}
        notify(c, bg, project=project, rec=rec, event=t.action, user_ids=users,
               title_ar=f"{rt.name_ar} {head}: {to.name_ar}", title_en=f"{rt.name_en} {head}: {to.name_en}",
               body=comment or rec.title)


def _initial_id(c: Ctx, rt: RecordType):
    return c.db.scalar(select(WorkflowState.id).where(WorkflowState.workflow_id == rt.workflow_id, WorkflowState.is_initial))


@router.put("/records/{record_id}/required-by", response_model=RecordDetail)
def set_required_by(record_id: uuid.UUID, body: RequiredByIn, bg: BackgroundTasks, c: Ctx = Depends(ctx)):
    """Latest date the contractor needs the answer by (supply schedule). Shown to both sides, never printed."""
    rec, a, rt, p = _load(c, record_id, lock=True)
    require(_can_set_required_by(rec, a, p), "cannot_set_required_by")
    note = (body.required_by_note or "").strip() or None if body.required_by else None
    if (rec.required_by, rec.required_by_note) == (body.required_by, note):
        return _detail(c, rec, a, rt, p)
    _audit(c, rec, "required_by", {"required_by": [str(rec.required_by) if rec.required_by else None,
                                                    str(body.required_by) if body.required_by else None],
                                   "note": [rec.required_by_note, note]}, a)
    rec.required_by, rec.required_by_note, rec.updated_at = body.required_by, note, datetime.now(UTC)
    c.db.flush()
    if rec.state_category == "submitted" and body.required_by:
        to_manager = rec.assigned_to is None and routing(a.project, rt) == "manager"
        users = {m.user_id for m, r in _responders(c, rec, rt)
                 if r.act_on_behalf or (not to_manager and (rec.assigned_to is None or m.user_id == rec.assigned_to))}
        d = body.required_by.isoformat()
        notify(c, bg, project=a.project, rec=rec, event="required_by", user_ids=users,
               title_ar=f"{rt.name_ar} {rec.number} R{rec.rev_no}: مطلوب الاعتماد قبل {d}",
               title_en=f"{rt.name_en} {rec.number} R{rec.rev_no}: answer needed by {d}", body=note or rec.title)
    return _detail(c, rec, a, rt, p)


@router.post("/records/{record_id}/assign", response_model=RecordDetail)
def assign(record_id: uuid.UUID, body: AssignIn, bg: BackgroundTasks, c: Ctx = Depends(ctx)):
    """The consultant PM hands a submitted record to one engineer of the discipline (or clears it)."""
    rec, a, rt, p = _load(c, record_id, lock=True)
    detail = _detail(c, rec, a, rt, p)
    require(detail.can_assign, "cannot_assign")
    if body.user_id is not None and body.user_id not in {u.id for u in detail.assign_candidates}:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "assignee_not_eligible")
    rec.assigned_to = body.user_id
    _audit(c, rec, "assign", {"assigned_to": str(body.user_id) if body.user_id else None}, a)
    c.db.flush()
    if body.user_id:
        notify(c, bg, project=a.project, rec=rec, event="assign", user_ids={body.user_id},
               title_ar=f"{rt.name_ar} {rec.number} R{rec.rev_no}: حُوِّل إليك للرد",
               title_en=f"{rt.name_en} {rec.number} R{rec.rev_no}: assigned to you", body=rec.title)
    return _detail(c, rec, a, rt, p)


@router.get("/inbox", response_model=list[InboxItem])
def inbox(c: Ctx = Depends(ctx)):
    """Everything that waits for the signed-in user, across projects, overdue first."""
    project_ids = c.db.scalars(select(ProjectMember.project_id).where(ProjectMember.user_id == c.user.id,
                                                                      ProjectMember.is_active)).all()
    types = {rt.id: rt for rt in c.db.scalars(select(RecordType).where(RecordType.org_id.is_(None)))}
    out: list[InboxItem] = []
    for pid in project_ids:
        a = project_access(c, pid)
        if a.party is None:
            continue
        perms = {tid: Perms(c, a, rt) for tid, rt in types.items()}
        recs = c.db.scalars(select(Record).where(Record.project_id == pid, Record.state_category.in_(
            ("draft", "submitted", "responded", "revise_and_resubmit", "rejected"))))
        latest: dict[uuid.UUID, int] = {}
        recs = list(recs)
        kinds = dict(c.db.execute(select(SubmittalDetails.record_id, SubmittalDetails.submittal_kind)
                                  .where(SubmittalDetails.record_id.in_([r.id for r in recs]))).all()) if recs else {}
        # the latest revision of each number among ALL its revisions (an answered R2 hides a returned R1);
        # a cancelled revision does not count, so the earlier one is due again
        for g, rev in c.db.execute(select(Record.revision_group_id, func.max(Record.rev_no))
                                   .where(Record.project_id == pid, Record.state_category != "cancelled")
                                   .group_by(Record.revision_group_id)):
            latest[g] = rev
        for r in recs:
            p = perms[r.record_type_id]
            reason = None
            if r.state_category == "submitted" and p.can("respond", r):
                manager_first = r.assigned_to is None and routing(a.project, types[r.record_type_id]) == "manager"
                if (a.role and a.role.act_on_behalf) or r.assigned_to == c.user.id or (r.assigned_to is None and not manager_first):
                    reason = "reply"
            elif r.state_category == "draft" and r.created_by == c.user.id:
                reason = "draft"
            elif (r.state_category == "responded" and r.from_party_id == a.party.id and p.can("submit", r)
                  and (r.created_by == c.user.id or r.submitted_by == c.user.id or (a.role and a.role.act_on_behalf)
                       or (a.role and a.role.manage_project))):
                reason = "verify"  # e.g. an NCR's corrective action, to check on site and close
            elif (r.state_category in ("revise_and_resubmit", "rejected") and r.rev_no == latest.get(r.revision_group_id, r.rev_no)
                  and r.from_party_id == a.party.id and p.can("create", discipline_id=r.discipline_id)
                  and (r.created_by == c.user.id or r.submitted_by == c.user.id or (a.role and a.role.manage_project))):
                reason = "returned"
            if reason:
                rt = types[r.record_type_id]
                out.append(InboxItem(id=r.id, project_id=pid, project_code=a.project.code,
                                     project_name_ar=a.project.name_ar, project_name_en=a.project.name_en,
                                     record_type=RecordTypeOut.model_validate(rt), number=r.number, rev_no=r.rev_no,
                                     title=r.title, state=StateOut.model_validate(_state(c, r.state_id)),
                                     reason=reason,
                                     # a returned request is due by the resubmission date, not the reply date
                                     due_at=r.resubmit_due_at if reason == "returned" else r.due_at,
                                     overdue=_resubmit_overdue(r) if reason == "returned" else _overdue(r),
                                     required_by=r.required_by,
                                     assigned_to_me=r.assigned_to == c.user.id, updated_at=r.updated_at,
                                     submittal_kind_name=kind_name(a.project, kinds.get(r.id))))
    order = {"reply": 0, "verify": 1, "returned": 2, "draft": 3}
    def soonest(x: InboxItem) -> datetime:
        when = [x.due_at or x.updated_at]
        if x.required_by:
            when.append(datetime.combine(x.required_by, time.max, UTC))
        return min(when)
    out.sort(key=lambda x: (not x.overdue, order[x.reason], soonest(x)))
    return out


@router.post("/records/{record_id}/revise", response_model=RecordDetail, status_code=201)
def new_revision(record_id: uuid.UUID, c: Ctx = Depends(ctx)):
    """R(n+1) of the same number: copies the content, clears the answer, starts as a draft."""
    rec, a, rt, p = _load(c, record_id)
    detail = _detail(c, rec, a, rt, p)
    require(detail.can_revise, "cannot_revise")
    initial = c.db.scalar(select(WorkflowState).where(WorkflowState.workflow_id == rt.workflow_id,
                                                      WorkflowState.is_initial))
    new = Record(project_id=rec.project_id, record_type_id=rt.id, number=rec.number, rev_no=rec.rev_no + 1,
                 revision_group_id=rec.revision_group_id, discipline_id=rec.discipline_id, title=rec.title,
                 description=rec.description, state_id=initial.id, state_category=initial.category,
                 from_party_id=a.party.id, to_party_id=rec.to_party_id, created_by=c.user.id, custom={k: v for k, v in (rec.custom or {}).items() if k not in RESPONSE_FIELDS.get(rt.code, ())},
                 required_by=rec.required_by, required_by_note=rec.required_by_note,
                 stage_id=rec.stage_id, all_locations=rec.all_locations, location_ids=rec.location_ids,
                 topic_id=rec.topic_id, linked_ids=rec.linked_ids)
    c.db.add(new)
    try:
        c.db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "revision_exists") from None
    c.db.add(SubmittalDetails(record_id=new.id, **_details(c, rec).model_dump()))
    if rt.code == "test":  # a retest: same parameters and limits, no values yet
        from app.models.lab import LabResult
        old = c.db.get(LabResult, rec.id)
        if old is not None:
            c.db.add(LabResult(record_id=new.id, template_id=old.template_id, material=old.material,
                               acceptance=old.acceptance, grade=old.grade, class_id=old.class_id, fck=old.fck,
                               mean_margin=old.mean_margin, individual_rule=old.individual_rule,
                               individual_margin=old.individual_margin, element=old.element, quantity=old.quantity,
                               quantity_uom=old.quantity_uom, specimen_count=old.specimen_count,
                               specification=old.specification,
                               lines=[{**x, "value": None, "text": None, "legible": True} for x in old.lines]))
    if rt.code == "programme":  # the update starts from the previous programme
        from app.models.programme import Programme
        old = c.db.get(Programme, rec.id)
        c.db.add(Programme(record_id=new.id, project_id=rec.project_id, lines=old.lines if old else [],
                           cycles=old.cycles if old else [], source=old.source if old else "manual"))
    c.db.add(RecordEvent(record_id=new.id, action="new_revision", to_state_id=initial.id, actor_id=c.user.id,
                         comment=f"R{rec.rev_no} → R{new.rev_no}"))
    _audit(c, new, "revise", {"from_record": str(rec.id), "rev": new.rev_no}, a)
    c.db.flush()
    return _detail(c, new, a, rt, Perms(c, a, rt))


@router.post("/records/{record_id}/comments", response_model=RecordDetail, status_code=201)
def add_comment(record_id: uuid.UUID, body: CommentIn, c: Ctx = Depends(ctx)):
    rec, a, rt, p = _load(c, record_id)
    require(a.party is not None and a.member is not None, "not_a_member")
    c.db.add(RecordComment(record_id=rec.id, party_id=a.party.id, visibility=body.visibility, author_id=c.user.id,
                           body=body.body.strip()))
    c.db.flush()
    return _detail(c, rec, a, rt, p)


@router.post("/records/{record_id}/attachments", response_model=RecordDetail, status_code=201)
def upload(record_id: uuid.UUID, file: UploadFile = File(...), kind: str = Form("submission"), c: Ctx = Depends(ctx)):
    rec, a, rt, p = _load(c, record_id)
    allowed = _detail(c, rec, a, rt, p).can_attach
    require(kind in allowed, "cannot_attach")
    key, size, sha = storage.save_upload(rec.project_id, file)
    f = StoredFile(project_id=rec.project_id, storage_key=key, filename=(file.filename or "file")[:255],
                   content_type=(file.content_type or "application/octet-stream")[:120], size=size, sha256=sha,
                   uploaded_by=c.user.id)
    c.db.add(f)
    c.db.flush()
    c.db.add(Attachment(record_id=rec.id, file_id=f.id, kind=kind, party_id=a.party.id))
    _audit(c, rec, "attach", {"file": f.filename, "size": size, "sha256": sha, "kind": kind}, a)
    c.db.flush()
    return _detail(c, rec, a, rt, p)


class CertificationIn(BaseModel):
    certified: str | None = None  # certified amount, with the retention kept
    payable: str | None = None  # net amount to pay


@router.put("/records/{record_id}/certification", response_model=RecordDetail)
def put_certification(record_id: uuid.UUID, body: CertificationIn, c: Ctx = Depends(ctx)):
    """A payment's certified amounts, written by supervision while it reviews it (before certifying)."""
    rec, a, rt, p = _load(c, record_id)
    require(rt.code in RESPONSE_FIELDS and rec.state_category == "submitted" and p.can("respond", rec), "cannot_respond")
    new = _check_custom(rt, rec.custom or {}, body.model_dump(), responder=True)
    _payable_within(new)
    if new != (rec.custom or {}):
        _audit(c, rec, "certification", {"from": {k: (rec.custom or {}).get(k) for k in RESPONSE_FIELDS[rt.code]},
                                        "to": {k: new.get(k) for k in RESPONSE_FIELDS[rt.code]}}, a)
        rec.custom = new
        c.db.flush()
    return _detail(c, rec, a, rt, p)


def _payable_within(cu: dict) -> None:
    """The amount for payment is what was certified less retention and recoveries: never more than the certified."""
    try:
        certified, payable = float(cu.get("certified") or 0), float(cu.get("payable") or 0)
    except ValueError:
        return
    if cu.get("certified") and cu.get("payable") and payable > certified:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "payable_exceeds_certified")


class CaptionIn(BaseModel):
    caption: str | None = Field(None, max_length=300)


@router.patch("/records/{record_id}/attachments/{attachment_id}", response_model=RecordDetail)
def caption_attachment(record_id: uuid.UUID, attachment_id: uuid.UUID, body: CaptionIn, c: Ctx = Depends(ctx)):
    """The caption says what a photo shows: its own party may write it at any time (the file itself stays as it is)."""
    rec, a, rt, p = _load(c, record_id)
    att = c.db.get(Attachment, attachment_id)
    if att is None or att.record_id != rec.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    require(a.member is not None and att.party_id == (a.party.id if a.party else None), "cannot_attach")
    new = (body.caption or "").strip() or None
    if new != att.caption:
        _audit(c, rec, "caption", {"attachment": str(att.id), "from": att.caption, "to": new}, a)
        att.caption = new
        c.db.flush()
    return _detail(c, rec, a, rt, p)


@router.delete("/records/{record_id}/attachments/{attachment_id}", response_model=RecordDetail)
def remove_attachment(record_id: uuid.UUID, attachment_id: uuid.UUID, c: Ctx = Depends(ctx)):
    """Only while the file can still be changed: a draft's own files, or a response not yet sent."""
    rec, a, rt, p = _load(c, record_id)
    att = c.db.get(Attachment, attachment_id)
    if att is None or att.record_id != rec.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    require(att.kind in _detail(c, rec, a, rt, p).can_attach and att.party_id == (a.party.id if a.party else None),
            "cannot_attach")
    f = c.db.get(StoredFile, att.file_id)
    c.db.delete(att)
    c.db.flush()
    _audit(c, rec, "detach", {"file": f.filename, "sha256": f.sha256}, a)
    return _detail(c, rec, a, rt, p)


@router.get("/files/{file_id}")
def download(file_id: uuid.UUID, c: Ctx = Depends(ctx)):
    f = c.db.get(StoredFile, file_id)
    # visible only through a record the user may see (RLS on records filters the join)
    rec_id = c.db.scalar(select(Attachment.record_id).where(Attachment.file_id == file_id))
    if f is None or rec_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    _load(c, rec_id)
    return FileResponse(storage.path_of(f.storage_key), media_type=f.content_type, filename=f.filename)


@router.get("/records/{record_id}/pdf")
def record_pdf(record_id: uuid.UUID, lang: str = Query("ar", pattern="^(ar|en)$"), c: Ctx = Depends(ctx)):
    from app.reports.record_pdf import render_record_pdf

    rec, a, rt, p = _load(c, record_id)
    detail = _detail(c, rec, a, rt, p)
    pdf = render_record_pdf(c, a, detail, lang)
    name = f"{rec.number}-R{rec.rev_no}.pdf"
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{name}"'})



# ----------------------------------------------------------------------------- bulk actions
class BulkIn(BaseModel):
    ids: list[uuid.UUID] = Field(max_length=1000)


class BulkAction(BaseModel):
    action: str
    name_ar: str
    name_en: str
    requires_comment: bool
    style: str
    count: int  # how many of the chosen records it applies to


class BulkTransitionIn(BulkIn):
    action: str = Field(max_length=40)
    comment: str | None = Field(default=None, max_length=10000)


class BulkFailure(BaseModel):
    id: uuid.UUID
    number: str
    error: str


class BulkResult(BaseModel):
    done: int
    skipped: int  # the action does not apply to them (state, permission)
    failed: list[BulkFailure] = []


def _bulk_records(c: Ctx, ids: list[uuid.UUID]):
    """The chosen records this user may see, with their access and permissions (types differ per record)."""
    out, cache = [], {}
    for rec in c.db.scalars(select(Record).where(Record.id.in_(ids))):
        if rec.project_id not in cache:
            cache[rec.project_id] = project_access(c, rec.project_id)
        a = cache[rec.project_id]
        rt = c.db.get(RecordType, rec.record_type_id)
        p = Perms(c, a, rt)
        if can_see(c, a, p, rec):
            out.append((rec, a, rt, p))
    return out


@router.post("/records-bulk/actions", response_model=list[BulkAction])
def bulk_actions(body: BulkIn, c: Ctx = Depends(ctx)):
    """What the user can do to the chosen records, with how many each action applies to (like Odoo's action menu)."""
    found: dict[str, BulkAction] = {}
    by_state: dict = {}
    for rec, a, rt, p in _bulk_records(c, body.ids):
        if rec.state_id not in by_state:
            by_state[rec.state_id] = list(c.db.scalars(select(WorkflowTransition).where(WorkflowTransition.from_state_id == rec.state_id)
                                                      .order_by(WorkflowTransition.sort)))
        for t in by_state[rec.state_id]:
            if not p.can(t.permission, rec):
                continue
            x = found.get(t.action)
            if x is None:
                found[t.action] = BulkAction(action=t.action, name_ar=t.name_ar, name_en=t.name_en,
                                             requires_comment=t.requires_comment, style=t.style, count=1)
            else:
                x.count += 1
                x.requires_comment = x.requires_comment or t.requires_comment
    return sorted(found.values(), key=lambda x: (-x.count, x.action))


@router.post("/records-bulk/transition", response_model=BulkResult)
def bulk_transition(body: BulkTransitionIn, bg: BackgroundTasks, c: Ctx = Depends(ctx)):
    """One action on many records: each goes through the same checks as on its own page; one that fails
    (missing results, an unanswered checklist ...) is listed and the others go on."""
    out = BulkResult(done=0, skipped=0)
    for rec, a, rt, p in _bulk_records(c, body.ids):
        t = c.db.scalar(select(WorkflowTransition).where(WorkflowTransition.from_state_id == rec.state_id,
                                                         WorkflowTransition.action == body.action))
        if t is None or not p.can(t.permission, rec):
            out.skipped += 1
            continue
        try:
            with c.db.begin_nested():
                transition(rec.id, TransitionIn(action=body.action, comment=body.comment), bg, c)
            out.done += 1
        except HTTPException as e:
            out.failed.append(BulkFailure(id=rec.id, number=f"{rec.number} R{rec.rev_no}", error=str(e.detail)))
    out.skipped += len(body.ids) - out.done - out.skipped - len(out.failed)
    return out
