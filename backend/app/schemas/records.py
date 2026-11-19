from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.core import DisciplineOut, Out, SubmittalKind, UserOut


class StateOut(Out):
    id: UUID
    code: str
    name_ar: str
    name_en: str
    category: str
    color: str


class TransitionOut(Out):
    action: str
    name_ar: str
    name_en: str
    requires_comment: bool
    style: str
    effect: str


class RecordTypeOut(Out):
    id: UUID
    code: str
    prefix: str
    name_ar: str
    name_en: str
    review_days: int


class KindName(BaseModel):
    ar: str
    en: str


class StageRef(BaseModel):
    id: UUID
    name_ar: str
    name_en: str
    scope: str


class LinkedRef(BaseModel):
    id: UUID
    number: str
    rev_no: int
    title: str
    state: "StateOut"
    stage_id: UUID | None = None


class TopicRef(BaseModel):
    id: UUID
    name_ar: str
    name_en: str


class LocationRef(BaseModel):
    id: UUID
    kind: str  # group (a whole building / zone) or unit (floor / section)
    name_ar: str  # with the group's name when the project has several groups
    name_en: str


class SubmittalDetailsIO(BaseModel):
    submittal_kind: str | None = Field(default=None, max_length=100)
    item: str | None = Field(default=None, max_length=300)
    manufacturer: str | None = Field(default=None, max_length=200)
    supplier: str | None = Field(default=None, max_length=200)
    drawing_ref: str | None = Field(default=None, max_length=200)
    spec_ref: str | None = Field(default=None, max_length=200)
    boq_ref: str | None = Field(default=None, max_length=100)
    quantity: Decimal | None = None
    unit: str | None = Field(default=None, max_length=30)


class RecordIn(BaseModel):
    record_type: str = "submittal"
    title: str | None = Field(default=None, max_length=300)  # may be left empty when a topic is chosen
    description: str | None = None
    discipline_id: UUID | None = None
    number: str | None = Field(default=None, max_length=60)  # manual number (e.g. migrated); else generated
    details: SubmittalDetailsIO = SubmittalDetailsIO()
    required_by: date | None = None
    required_by_note: str | None = Field(default=None, max_length=300)
    stage_id: UUID | None = None
    topic_id: UUID | None = None
    all_locations: bool = False
    location_ids: list[UUID] = []
    requested_for: datetime | None = None
    performed_at: datetime | None = None
    requested_for: datetime | None = None  # inspections: when it should take place (empty = now)
    linked_ids: list[UUID] = []  # inspections: approved submittals of the materials
    addressed_to: UUID | None = None  # "choose" routing: the consultant engineer the request goes to
    custom: dict[str, str | None] = {}  # extra fields of the type (RFI proposal, NCR severity, delivery note...)


class RequiredByIn(BaseModel):
    required_by: date | None
    required_by_note: str | None = Field(default=None, max_length=300)


class RecordPatch(BaseModel):
    title: str | None = Field(default=None, max_length=300)
    description: str | None = None
    discipline_id: UUID | None = None
    details: SubmittalDetailsIO | None = None
    # sent together: the stage and where it applies
    stage_id: UUID | None = None
    topic_id: UUID | None = None
    all_locations: bool | None = None
    location_ids: list[UUID] | None = None
    requested_for: datetime | None = None
    linked_ids: list[UUID] | None = None
    addressed_to: UUID | None = None
    custom: dict[str, str | None] | None = None


class CheckAnswer(BaseModel):
    result: Literal["ok", "nc", "na"] | None = None  # conforming / non-conforming / not applicable
    note: str | None = Field(default=None, max_length=500)


class CheckLine(CheckAnswer):
    ar: str
    en: str


class TransitionIn(BaseModel):
    action: str
    comment: str | None = Field(default=None, max_length=10000)
    on_behalf_of: UUID | None = None
    performed_at: datetime | None = None  # inspections: when it was actually done (default: now)
    answered_on: date | None = None  # imported records: the day the answer was really given (on paper)
    checklist: list[CheckAnswer] | None = None  # inspections: one answer per checklist line, in order


class CommentIn(BaseModel):
    body: str = Field(min_length=1, max_length=10000)
    visibility: Literal["shared", "internal"] = "shared"


class RecordRow(BaseModel):
    id: UUID
    number: str
    rev_no: int
    title: str
    state: StateOut
    discipline: DisciplineOut | None
    submitted_at: datetime | None
    due_at: datetime | None
    answered_at: datetime | None
    overdue: bool
    revisions: int  # how many revisions this number has
    required_by: date | None = None
    resubmit_due_at: datetime | None = None  # open resubmission deadline (none once the next revision is in)
    resubmit_overdue: bool = False
    submittal_kind: str | None = None
    submittal_kind_name: KindName | None = None
    stage_id: UUID | None = None
    topic_id: UUID | None = None
    all_locations: bool = False
    location_ids: list[UUID] = []
    lab_result: str | None = None  # lab tests: pass | fail (calculated)
    lab_decision: str | None = None


class EventOut(BaseModel):
    id: int
    action: str
    to_state: StateOut | None
    actor: UserOut
    on_behalf_of: UserOut | None
    channel: str
    comment: str | None
    stamp: str | None
    at: datetime


class CommentOut(BaseModel):
    id: UUID
    author: UserOut
    party_kind: str
    visibility: str
    body: str
    created_at: datetime


class AttachmentOut(BaseModel):
    id: UUID
    file_id: UUID
    filename: str
    content_type: str
    size: int
    kind: str
    party_kind: str
    created_at: datetime


class RevisionRef(BaseModel):
    id: UUID
    rev_no: int
    state: StateOut


class RecordDetail(BaseModel):
    id: UUID
    imported: bool = False  # brought over from Odoo: an answer may carry its real (earlier) date
    project_id: UUID
    record_type: RecordTypeOut
    number: str
    rev_no: int
    title: str
    description: str | None
    discipline: DisciplineOut | None
    state: StateOut
    from_party_kind: str
    created_by: UserOut
    created_at: datetime
    submitted_by: UserOut | None
    submitted_at: datetime | None
    due_at: datetime | None
    overdue: bool
    answered_by: UserOut | None
    answered_on_behalf_of: UserOut | None
    answered_at: datetime | None
    response_comment: str | None
    required_by: date | None = None  # the author's "answer needed by" (supply schedule); not printed
    resubmit_due_at: datetime | None = None
    resubmitted_at: datetime | None = None
    resubmit_overdue: bool = False
    required_by_note: str | None = None
    can_set_required_by: bool = False
    details: SubmittalDetailsIO
    submittal_kind_name: KindName | None = None  # details.submittal_kind shown in both languages
    stage: StageRef | None = None
    topic: TopicRef | None = None
    requested_for: datetime | None = None
    performed_at: datetime | None = None
    linked: list["LinkedRef"] = []
    custom: dict[str, str | None] = {}
    checklist: list[CheckLine] = []  # inspections: fixed at submission (before that: the topic's current list)
    link_warning: str | None = None  # no_link | not_approved (only when the project links inspections)
    all_locations: bool = False
    locations: list[LocationRef] = []
    transitions: list[TransitionOut]
    can_edit: bool
    can_revise: bool
    can_attach: list[str]  # attachment kinds the user may add now
    can_act_on_behalf: bool
    assigned_to: UserOut | None = None
    addressed_to: list[UserOut] = []  # who the request goes to: the assigned engineer, else the consultant PM(s)
    can_assign: bool = False
    assign_candidates: list[UserOut] = []
    no_discipline_engineer: bool = False  # draft: no consultant engineer covers this discipline yet
    events: list[EventOut]
    comments: list[CommentOut]
    attachments: list[AttachmentOut]
    revisions: list[RevisionRef]


class RecordMeta(BaseModel):
    record_type: RecordTypeOut
    can_create: bool
    disciplines: list[DisciplineOut]  # the ones the user may create records in
    party_kind: str | None
    submittal_kinds: list[SubmittalKind] = []  # active kinds of this project, in order
    states: list["StateOut"] = []  # this type's workflow states (labels for the dashboard)
    link_submittals: bool = False
    reply_hours: int = 0
    routing: str = "discipline"
    enabled: bool = True  # the project uses this type


class AssignIn(BaseModel):
    user_id: UUID | None


class InboxItem(BaseModel):
    id: UUID
    project_id: UUID
    project_code: str
    project_name_ar: str
    project_name_en: str
    record_type: RecordTypeOut
    number: str
    rev_no: int
    title: str
    state: StateOut
    reason: Literal["reply", "verify", "returned", "draft"]
    due_at: datetime | None
    required_by: date | None = None
    submittal_kind_name: KindName | None = None
    overdue: bool
    assigned_to_me: bool
    updated_at: datetime
