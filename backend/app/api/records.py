"""Record engine API: one set of endpoints for every record type (design doc section 4).

Permission = role x record type x action within a scope (project / disciplines).
The direction of work is fixed by the record type: its creator party writes and
submits, its responder party answers.
"""
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core import storage
from app.core.access import ProjectAccess, project_access, require
from app.core.audit import audit
from app.core.deps import Ctx, ctx
from app.core.kinds import active_codes, kind_name, submittal_kinds
from app.core.notify import members_who_can, notify
from app.models.core import Discipline, Project, ProjectMember, ProjectParty, RolePermission, User
from app.models.records import (Attachment, Record, RecordComment, RecordEvent, RecordType, StoredFile,
                                SubmittalDetails, WorkflowState, WorkflowTransition)
from app.schemas.core import DisciplineOut, SubmittalKind, UserOut
from app.schemas.records import (AssignIn, AttachmentOut, CommentIn, InboxItem, CommentOut, EventOut, RecordDetail, RecordIn,
                                 RecordMeta, RecordPatch, RecordRow, RequiredByIn, RecordTypeOut, RevisionRef, StateOut, SubmittalDetailsIO,
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
                                                                RolePermission.record_type.in_([rtype.code, "*"]))):
                # a specific grant for the type wins over the '*' grant
                if rp.record_type != "*" or rp.action not in self.scopes:
                    self.scopes[rp.action] = rp.scope

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
            if self.party_kind != self.rtype.creator_party:
                return False
            if rec is not None and rec.from_party_id != self.a.party.id:
                return False
        if action == "respond" and self.party_kind != self.rtype.responder_party:
            return False
        return True


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
    if not p.can("view", rec) and not (rec.from_party_id == (a.party.id if a.party else None)):
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


def _review_days(a: ProjectAccess, rt: RecordType) -> int:
    return int((a.project.settings or {}).get("review_days", {}).get(rt.code, rt.review_days))


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
                          kind=at.kind, party_kind=parties.get(at.party_id, ""), created_at=at.created_at)
            for at, f in c.db.execute(select(Attachment, StoredFile).join(StoredFile, StoredFile.id == Attachment.file_id)
                                      .where(Attachment.record_id == rec.id).order_by(Attachment.created_at))]
    revs = [RevisionRef(id=r.id, rev_no=r.rev_no, state=StateOut.model_validate(_state(c, r.state_id)))
            for r in c.db.scalars(select(Record).where(Record.revision_group_id == rec.revision_group_id)
                                  .order_by(Record.rev_no))]
    disc = c.db.get(Discipline, rec.discipline_id) if rec.discipline_id else None

    is_draft = rec.state_category == "draft"
    attach = []
    if is_draft and p.can("edit", rec):
        attach.append("submission")
    if rec.state_category == "submitted" and p.can("respond", rec):
        attach.append("response")
    can_assign = bool(rec.state_category == "submitted" and a.role and a.role.act_on_behalf and p.can("respond", rec))
    candidates = []
    if can_assign:
        candidates = [_user(c, m.user_id) for m, r in _responders(c, rec, rt) if not r.act_on_behalf]
    no_engineer = False
    if is_draft:
        no_engineer = not any(not r.act_on_behalf for _, r in _responders(c, rec, rt))
    can_revise = (rt.has_revisions and not is_draft and rec.rev_no == _latest_rev(c, rec)
                  and rec.state_category in ("revise_and_resubmit", "rejected", "approved_as_noted", "cancelled")
                  and p.can("create", discipline_id=rec.discipline_id))
    return RecordDetail(
        id=rec.id, project_id=rec.project_id, record_type=RecordTypeOut.model_validate(rt), number=rec.number,
        rev_no=rec.rev_no, title=rec.title, description=rec.description,
        discipline=DisciplineOut.model_validate(disc) if disc else None, state=StateOut.model_validate(state),
        from_party_kind=party.kind, created_by=_user(c, rec.created_by), created_at=rec.created_at,
        submitted_by=_user(c, rec.submitted_by), submitted_at=rec.submitted_at, due_at=rec.due_at,
        overdue=_overdue(rec), answered_by=_user(c, rec.answered_by),
        answered_on_behalf_of=_user(c, rec.answered_on_behalf_of), answered_at=rec.answered_at,
        response_comment=rec.response_comment, required_by=rec.required_by, required_by_note=rec.required_by_note,
        can_set_required_by=_can_set_required_by(rec, a, p), details=(det := _details(c, rec)),
        submittal_kind_name=kind_name(a.project, det.submittal_kind), transitions=trans,
        can_edit=is_draft and p.can("edit", rec), can_revise=can_revise, can_attach=attach,
        can_act_on_behalf=bool(a.role and a.role.act_on_behalf and p.can("respond", rec)),
        assigned_to=_user(c, rec.assigned_to), can_assign=can_assign, assign_candidates=candidates,
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
    return RecordMeta(record_type=RecordTypeOut.model_validate(rt), can_create=a.party is not None and p.can("create"),
                      disciplines=[DisciplineOut.model_validate(d) for d in discs],
                      party_kind=a.party.kind if a.party else None,
                      submittal_kinds=[SubmittalKind(**k) for k in submittal_kinds(a.project) if k["active"]])


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
    my_party = a.party.id if a.party else None
    out = []
    discs = {d.id: d for d in c.db.scalars(select(Discipline).where(
        Discipline.id.in_({r.discipline_id for r in keep if r.discipline_id})))}
    for r in keep:
        if not p.can("view", r) and r.from_party_id != my_party:
            continue
        d = discs.get(r.discipline_id)
        out.append(RecordRow(id=r.id, number=r.number, rev_no=r.rev_no, title=r.title,
                             state=StateOut.model_validate(_state(c, r.state_id)),
                             discipline=DisciplineOut.model_validate(d) if d else None,
                             submitted_at=r.submitted_at, due_at=r.due_at, answered_at=r.answered_at,
                             overdue=_overdue(r), revisions=counts[r.revision_group_id], required_by=r.required_by))
    return out


def _can_set_required_by(rec: Record, a: ProjectAccess, p: "Perms") -> bool:
    """The author side sets it while the record waits for an answer (draft or submitted)."""
    return (a.party is not None and rec.from_party_id == a.party.id and rec.state_category in ("draft", "submitted")
            and (p.can("edit", rec) or p.can("submit", rec)))


def _check_kind(a, code: str | None) -> None:
    if code is not None and code not in active_codes(a.project):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_kind")


@router.post("/projects/{project_id}/records", response_model=RecordDetail, status_code=201)
def create_record(project_id: uuid.UUID, body: RecordIn, c: Ctx = Depends(ctx)):
    a = project_access(c, project_id)
    rt = _rtype(c, body.record_type)
    p = Perms(c, a, rt)
    require(a.party is not None and p.can("create", discipline_id=body.discipline_id), "cannot_create")
    disc = _check_discipline(c, a, body.discipline_id)
    initial = c.db.scalar(select(WorkflowState).where(WorkflowState.workflow_id == rt.workflow_id,
                                                      WorkflowState.is_initial))
    number = body.number.strip() if body.number else _next_number(c, a, rt, disc)
    responder = c.db.scalar(select(ProjectParty.id).where(ProjectParty.project_id == project_id,
                                                          ProjectParty.kind == rt.responder_party,
                                                          ProjectParty.status != "removed"))
    rec = Record(project_id=project_id, record_type_id=rt.id, number=number, rev_no=0,
                 revision_group_id=uuid.uuid4(), discipline_id=body.discipline_id, title=body.title,
                 description=body.description, state_id=initial.id, state_category=initial.category,
                 from_party_id=a.party.id, to_party_id=responder, created_by=c.user.id,
                 required_by=body.required_by, required_by_note=(body.required_by_note or "").strip() or None)
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
    for f in ("title", "description"):
        v = getattr(body, f)
        if v is not None and v != getattr(rec, f):
            changes[f] = [getattr(rec, f), v]
            setattr(rec, f, v)
    if "discipline_id" in body.model_fields_set and body.discipline_id != rec.discipline_id:
        _check_discipline(c, a, body.discipline_id)
        changes["discipline_id"] = [str(rec.discipline_id), str(body.discipline_id)]
        rec.discipline_id = body.discipline_id
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
    if t.effect == "submit":
        rec.submitted_by, rec.submitted_at = c.user.id, now
        rec.due_at = now + timedelta(days=_review_days(a, rt))
    elif t.effect == "respond":
        rec.answered_by, rec.answered_at, rec.answered_on_behalf_of = c.user.id, now, on_behalf
        rec.response_comment = comment
    rec.state_id, rec.state_category, rec.updated_at = to.id, to.category, now
    c.db.flush()
    stamp = _stamp(c, rec, to) if t.effect == "respond" else None
    c.db.add(RecordEvent(record_id=rec.id, action=t.action, from_state_id=t.from_state_id, to_state_id=to.id,
                         actor_id=c.user.id, on_behalf_of=on_behalf, comment=comment, stamp=stamp))
    _audit(c, rec, "transition", {"action": t.action, "to": to.code, "on_behalf_of": str(on_behalf) if on_behalf else None}, a)
    c.db.flush()
    _notify_transition(c, bg, a.project, rec, rt, t, to, comment)
    return _detail(c, rec, a, rt, p)


def _notify_transition(c: Ctx, bg: BackgroundTasks, project: Project, rec: Record, rt: RecordType,
                       t: WorkflowTransition, to: WorkflowState, comment: str | None) -> None:
    head = f"{rec.number} R{rec.rev_no}"
    if t.effect == "submit" or (t.effect == "cancel" and t.from_state_id != _initial_id(c, rt)):
        responders = _responders(c, rec, rt)
        users = {m.user_id for m, r in responders if rec.assigned_to is None or r.act_on_behalf
                 or m.user_id == rec.assigned_to}
        ar = f"{rt.name_ar} {head}: " + ("بانتظار ردك" if t.effect == "submit" else "سُحب وأُلغي")
        en = f"{rt.name_en} {head}: " + ("awaiting your reply" if t.effect == "submit" else "withdrawn")
        notify(c, bg, project=project, rec=rec, event=t.action, user_ids=users, title_ar=ar, title_en=en,
               body=rec.title)
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
        users = {m.user_id for m, r in _responders(c, rec, rt) if rec.assigned_to is None or r.act_on_behalf
                 or m.user_id == rec.assigned_to}
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
        recs = c.db.scalars(select(Record).where(Record.project_id == pid,
                                                 Record.state_category.in_(("draft", "submitted", "revise_and_resubmit", "rejected"))))
        latest: dict[uuid.UUID, int] = {}
        recs = list(recs)
        for r in recs:
            latest[r.revision_group_id] = max(latest.get(r.revision_group_id, -1), r.rev_no)
        for r in recs:
            p = perms[r.record_type_id]
            reason = None
            if r.state_category == "submitted" and p.can("respond", r):
                if r.assigned_to is None or r.assigned_to == c.user.id or (a.role and a.role.act_on_behalf):
                    reason = "reply"
            elif r.state_category == "draft" and r.created_by == c.user.id:
                reason = "draft"
            elif (r.state_category in ("revise_and_resubmit", "rejected") and r.rev_no == latest[r.revision_group_id]
                  and r.from_party_id == a.party.id and p.can("create", discipline_id=r.discipline_id)
                  and (r.created_by == c.user.id or r.submitted_by == c.user.id or (a.role and a.role.manage_project))):
                reason = "returned"
            if reason:
                rt = types[r.record_type_id]
                out.append(InboxItem(id=r.id, project_id=pid, project_code=a.project.code,
                                     project_name_ar=a.project.name_ar, project_name_en=a.project.name_en,
                                     record_type=RecordTypeOut.model_validate(rt), number=r.number, rev_no=r.rev_no,
                                     title=r.title, state=StateOut.model_validate(_state(c, r.state_id)),
                                     reason=reason, due_at=r.due_at, overdue=_overdue(r), required_by=r.required_by,
                                     assigned_to_me=r.assigned_to == c.user.id, updated_at=r.updated_at))
    order = {"reply": 0, "returned": 1, "draft": 2}
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
                 from_party_id=a.party.id, to_party_id=rec.to_party_id, created_by=c.user.id, custom=rec.custom,
                 required_by=rec.required_by, required_by_note=rec.required_by_note)
    c.db.add(new)
    try:
        c.db.flush()
    except IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "revision_exists") from None
    c.db.add(SubmittalDetails(record_id=new.id, **_details(c, rec).model_dump()))
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

