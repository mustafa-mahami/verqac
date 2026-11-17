"""Laboratory tests: organization templates, project concrete classes, and each test record's results."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.core import Base, pk


class LabTemplate(Base):
    """A test and its parameters with limits (sample, parameter, unit, method, kind, min, max)."""

    __tablename__ = "lab_templates"

    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(150), nullable=False)
    name_en: Mapped[str] = mapped_column(String(150), nullable=False)
    material: Mapped[str] = mapped_column(String(10), nullable=False, server_default="OTH")
    standard: Mapped[str | None] = mapped_column(String(200))
    acceptance: Mapped[str] = mapped_column(String(10), nullable=False, server_default="all")  # all | concrete
    samples: Mapped[str | None] = mapped_column(String(200))  # e.g. "Ø32,Ø25" - lines repeat per sample
    lines: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class ConcreteClass(Base):
    """A concrete grade of the project with its specified strength and acceptance rule (project spec / QMP)."""

    __tablename__ = "concrete_classes"

    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    grade: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str | None] = mapped_column(String(150))
    aliases: Mapped[str | None] = mapped_column(String(150))  # other names on certificates, comma separated
    specimen: Mapped[str] = mapped_column(String(10), nullable=False, server_default="cube")
    fck: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    mean_margin: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    individual_rule: Mapped[str] = mapped_column(String(10), nullable=False, server_default="minus")  # minus | percent
    individual_margin: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default="4")
    elements: Mapped[str | None] = mapped_column(String(300))  # keywords, comma separated
    topic_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    ref: Mapped[str | None] = mapped_column(String(150))  # spec / QMP clause
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class LabResult(Base):
    """The certificate of one lab test record: details, result lines, calculated result, decision, AI reading."""

    __tablename__ = "lab_results"

    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("lab_templates.id", ondelete="SET NULL"))
    material: Mapped[str | None] = mapped_column(String(10))
    acceptance: Mapped[str] = mapped_column(String(10), nullable=False, server_default="all")
    lab_name: Mapped[str | None] = mapped_column(String(150))
    lab_report_no: Mapped[str | None] = mapped_column(String(80))
    sampling_date: Mapped[date | None] = mapped_column(Date)
    test_date: Mapped[date | None] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)
    grade: Mapped[str | None] = mapped_column(String(30))
    class_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("concrete_classes.id", ondelete="SET NULL"))
    fck: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    mean_margin: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    individual_rule: Mapped[str | None] = mapped_column(String(10))
    individual_margin: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    element: Mapped[str | None] = mapped_column(String(200))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    quantity_uom: Mapped[str | None] = mapped_column(String(20))
    specimen_count: Mapped[int | None] = mapped_column(Integer)
    specification: Mapped[str | None] = mapped_column(String(200))
    lab_conclusion: Mapped[str | None] = mapped_column(String(10))  # pass | fail, as printed by the lab
    lines: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    result: Mapped[str | None] = mapped_column(String(10), index=True)  # pass | fail (calculated)
    note: Mapped[str | None] = mapped_column(String(300))
    decision: Mapped[str | None] = mapped_column(String(20))  # on a failed test: retest | core | accepted | ...
    decision_note: Mapped[str | None] = mapped_column(Text)
    decision_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ai_state: Mapped[str | None] = mapped_column(String(12))  # reading | ready | error
    ai_message: Mapped[str | None] = mapped_column(String(300))
    ai_draft: Mapped[dict | None] = mapped_column(JSONB)
    ai_file_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
