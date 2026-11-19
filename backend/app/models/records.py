"""Record engine (design doc sections 4 and 8).

One `records` table holds every quality record; each record type has a 1:1 details table.
Record types, workflows, states and transitions are data. Every state carries one of
seven fixed categories (the `dr` status codes); KPIs and visibility rules use the
category, never the state's name.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.core import Base, created, pk

CATEGORIES = ("draft", "submitted", "responded", "approved", "approved_as_noted", "revise_and_resubmit", "rejected",
              "cancelled")
# categories that close a record (a reply was given or it was withdrawn)
CLOSED = ("approved", "approved_as_noted", "revise_and_resubmit", "rejected", "cancelled")
EFFECTS = ("submit", "respond", "cancel", "none")


class Workflow(Base):
    __tablename__ = "workflows"
    __table_args__ = (UniqueConstraint("org_id", "code"),)

    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)


class WorkflowState(Base):
    __tablename__ = "workflow_states"
    __table_args__ = (
        UniqueConstraint("workflow_id", "code"),
        CheckConstraint(f"category IN {CATEGORIES}", name="category_valid"),
    )

    id: Mapped[uuid.UUID] = pk()
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    color: Mapped[str] = mapped_column(String(20), nullable=False, server_default="gray")
    is_initial: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")


class WorkflowTransition(Base):
    """from -> to, the permission it needs (role_permissions action) and what it does."""

    __tablename__ = "workflow_transitions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "from_state_id", "action"),
        CheckConstraint(f"effect IN {EFFECTS}", name="effect_valid"),
    )

    id: Mapped[uuid.UUID] = pk()
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    from_state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=False)
    to_state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_states.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    permission: Mapped[str] = mapped_column(String(20), nullable=False)  # submit | respond | cancel | edit
    effect: Mapped[str] = mapped_column(String(20), nullable=False, server_default="none")
    requires_comment: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    style: Mapped[str] = mapped_column(String(20), nullable=False, server_default="default")  # button colour hint
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")


class RecordType(Base):
    __tablename__ = "record_types"
    __table_args__ = (UniqueConstraint("org_id", "code"),)

    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String(40), nullable=False)  # matches role_permissions.record_type
    prefix: Mapped[str] = mapped_column(String(10), nullable=False)  # {TYPE} in numbering
    name_ar: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    workflow_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflows.id"), nullable=False)
    numbering_pattern: Mapped[str] = mapped_column(String(100), nullable=False,
                                                   server_default="{PRJ}-{TYPE}-{DISC}-{SEQ:000}")
    review_days: Mapped[int] = mapped_column(Integer, nullable=False, server_default="14")
    has_revisions: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    creator_party: Mapped[str] = mapped_column(String(20), nullable=False, server_default="contractor")
    responder_party: Mapped[str] = mapped_column(String(20), nullable=False, server_default="consultant")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")


class Record(Base):
    __tablename__ = "records"

    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    record_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("record_types.id"), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(60), nullable=False)
    rev_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    revision_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    discipline_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("disciplines.id"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    state_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workflow_states.id"), nullable=False)
    # copy of the state's category: used by RLS (drafts), the unique index and the KPIs
    state_category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    from_party_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_parties.id"), nullable=False, index=True)
    to_party_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_parties.id"))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # optional: the consultant PM hands the record to one engineer of the discipline
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    # latest date the author needs the answer by (e.g. from the supply schedule); never printed
    required_by: Mapped[date | None] = mapped_column(Date)
    required_by_note: Mapped[str | None] = mapped_column(String(300))
    # after "revise and resubmit" / "rejected": the author has until resubmit_due_at to submit the next
    # revision; resubmitted_at is set when it does (the record then stops counting as overdue)
    resubmit_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resubmitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # inspections: when the contractor wants it (empty = now), when it was actually done, and the
    # approved submittals of the materials it relies on
    requested_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    performed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    linked_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    # inspections: the topic's checklist fixed at submission, with the answers [{ar, en, result, note}]
    checklist: Mapped[list | None] = mapped_column(JSONB)
    # work stage and locations the record covers (FK added by migration 0008); all_locations = the whole project
    stage_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    topic_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # FK added by migration 0009
    all_locations: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    location_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    answered_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    answered_on_behalf_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_comment: Mapped[str | None] = mapped_column(Text)
    custom: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    legacy_ref: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = created()
    updated_at: Mapped[datetime] = created()


class SubmittalDetails(Base):
    __tablename__ = "submittal_details"

    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    submittal_kind: Mapped[str | None] = mapped_column(String(100))  # material, shop drawing, method statement...
    item: Mapped[str | None] = mapped_column(String(300))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    supplier: Mapped[str | None] = mapped_column(String(200))  # agent / supplier
    drawing_ref: Mapped[str | None] = mapped_column(String(200))
    spec_ref: Mapped[str | None] = mapped_column(String(200))
    boq_ref: Mapped[str | None] = mapped_column(String(100))
    quantity: Mapped[float | None] = mapped_column(Numeric(14, 3))
    unit: Mapped[str | None] = mapped_column(String(30))


class NumberingCounter(Base):
    __tablename__ = "numbering_counters"
    __table_args__ = (UniqueConstraint("project_id", "record_type_id", "scope_key"),)

    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    record_type_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("record_types.id"), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(20), nullable=False, server_default="")  # e.g. discipline code
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class RecordEvent(Base):
    """State history of a record: who moved it, from where to where, on whose behalf, through which channel."""

    __tablename__ = "record_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    from_state_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_states.id"))
    to_state_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workflow_states.id"))
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    on_behalf_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String(20), nullable=False, server_default="web")
    comment: Mapped[str | None] = mapped_column(Text)
    stamp: Mapped[str | None] = mapped_column(String(64))  # SHA-256 of the record as it was answered
    at: Mapped[datetime] = created()


class RecordComment(Base):
    __tablename__ = "record_comments"
    __table_args__ = (CheckConstraint("visibility IN ('shared', 'internal')", name="visibility_valid"),)

    id: Mapped[uuid.UUID] = pk()
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True)
    party_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_parties.id"), nullable=False)  # author's party
    visibility: Mapped[str] = mapped_column(String(10), nullable=False, server_default="shared")
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = created()


class StoredFile(Base):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = created()


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (CheckConstraint("kind IN ('submission', 'response', 'photo', 'signed', 'other')", name="kind_valid"),)

    id: Mapped[uuid.UUID] = pk()
    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), nullable=False, index=True)
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="submission")
    party_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_parties.id"), nullable=False)
    caption: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = created()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = {"implicit_returning": False}  # written for other users, who the writer cannot read

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    record_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"))
    event: Mapped[str] = mapped_column(String(40), nullable=False)
    title_ar: Mapped[str] = mapped_column(String(300), nullable=False)
    title_en: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = created()
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProjectReminder(Base):
    """A project reminder already sent (e.g. a day without a daily report), so each goes out once."""

    __tablename__ = "project_reminders"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)  # dr_missing
    key: Mapped[str] = mapped_column(String(40), primary_key=True)  # the day
    sent_at: Mapped[datetime] = created()


RECORD_TABLES = [
    "workflows", "workflow_states", "workflow_transitions", "record_types", "records", "submittal_details",
    "numbering_counters", "record_events", "record_comments", "files", "attachments",
]


class RecordReminder(Base):
    """A deadline reminder already sent, so each goes out once (late ones once per day for submittals)."""

    __tablename__ = "record_reminders"

    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), primary_key=True)  # reply_soon | reply_late | resub_soon | resub_late
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    sent_at: Mapped[datetime] = created()
