"""Public check of a printed reply: the QR on the PDF opens /v/{stamp}, which calls this endpoint.

No sign-in. The stamp is a 64-hex SHA-256, so it cannot be guessed; the answer is a short summary
(what was answered, by whom, when, and whether it still matches) with no files or internal comments.
"""
import re
from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import system_db
from app.models.core import Organization, Project, ProjectParty, User
from app.models.records import Record, RecordEvent, RecordType, WorkflowState

router = APIRouter(tags=["verify"])
STAMP_RE = re.compile(r"^[0-9a-f]{64}$")


class Name(BaseModel):
    ar: str
    en: str


class StateOut(BaseModel):
    code: str
    category: str
    color: str | None
    name: Name


class VerifyOut(BaseModel):
    stamp: str
    intact: bool                 # the record, files and reply still give the same fingerprint
    project_code: str
    project: Name
    contractor: Name | None
    consultant: Name | None
    record_type: Name
    number: str
    rev_no: int
    title: str
    decision: StateOut
    answered_at: datetime
    answered_by: Name
    on_behalf_of: Name | None
    latest_rev: int              # > rev_no when a newer revision exists
    latest_state: StateOut | None
    cancelled: bool


def _name(o, base: str = "name") -> Name | None:
    return Name(ar=getattr(o, f"{base}_ar"), en=getattr(o, f"{base}_en")) if o else None


def _state(s: WorkflowState) -> StateOut:
    return StateOut(code=s.code, category=s.category, color=s.color, name=_name(s))


def _party(db: Session, project_id, kind: str) -> Name | None:
    row = db.execute(select(ProjectParty, Organization).outerjoin(Organization, Organization.id == ProjectParty.org_id)
                     .where(ProjectParty.project_id == project_id, ProjectParty.kind == kind,
                            ProjectParty.status != "removed")).first()
    if not row:
        return None
    p, o = row
    return _name(o) if o else Name(ar=p.placeholder_name, en=p.placeholder_name)


@router.get("/verify/{stamp}", response_model=VerifyOut)
def verify(stamp: str, db: Session = Depends(system_db, scope="function")):
    from app.api.records import _stamp  # local import: records imports a lot of the app

    stamp = stamp.strip().lower()
    ev = db.scalar(select(RecordEvent).where(RecordEvent.stamp == stamp)) if STAMP_RE.match(stamp) else None
    if ev is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "stamp_not_found")
    rec = db.get(Record, ev.record_id)
    decision = db.get(WorkflowState, ev.to_state_id)
    project = db.get(Project, rec.project_id)
    rt = db.get(RecordType, rec.record_type_id)
    latest = db.scalar(select(Record).where(Record.revision_group_id == rec.revision_group_id,
                                            Record.state_category != "cancelled")
                       .order_by(Record.rev_no.desc()).limit(1))
    latest_rev = db.scalar(select(func.max(Record.rev_no)).where(Record.revision_group_id == rec.revision_group_id))
    intact = rec.answered_at is not None and _stamp(SimpleNamespace(db=db), rec, decision) == stamp
    return VerifyOut(
        stamp=stamp, intact=intact, project_code=project.code, project=_name(project),
        contractor=_party(db, project.id, "contractor"), consultant=_party(db, project.id, "consultant"),
        record_type=_name(rt), number=rec.number, rev_no=rec.rev_no, title=rec.title, decision=_state(decision),
        answered_at=ev.at, answered_by=_name(db.get(User, ev.actor_id), "full_name"),
        on_behalf_of=_name(db.get(User, ev.on_behalf_of), "full_name") if ev.on_behalf_of else None,
        latest_rev=latest_rev,
        latest_state=_state(db.get(WorkflowState, latest.state_id)) if latest and latest.id != rec.id else None,
        cancelled=rec.state_category == "cancelled",
    )
