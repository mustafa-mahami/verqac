"""Daily site report (one per project per day) and the progress it feeds (stage x location cells)."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.core import Base, created, pk


class DailyReport(Base):
    __tablename__ = "daily_reports"

    record_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("records.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    shift: Mapped[str] = mapped_column(String(10), nullable=False, server_default="day")  # day | night | both
    work_status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="normal")  # normal | partial | stopped
    stop_reason: Mapped[str | None] = mapped_column(String(300))
    weather: Mapped[str | None] = mapped_column(String(20))
    temp_min: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    temp_max: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    wind: Mapped[str | None] = mapped_column(String(20))
    hours_from: Mapped[str | None] = mapped_column(String(5))
    hours_to: Mapped[str | None] = mapped_column(String(5))
    # [{group: supervision|contractor|labour, sub, name, count, hours}]
    crew: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    # [{name, count, hours, idle_hours, note}]
    equipment: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    # [{material, qty, unit, supplier, delivery_note, submittal_id, mir_id}]
    materials: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    # [{stage_id, topic_id, location_ids, all_locations, description, qty, unit, crew, progress}]
    works: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    planned: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")  # tomorrow, same shape
    # [{cause, hours, description, link_id}]
    delays: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    hse: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")  # incidents, near_misses, toolbox, notes
    visitors: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)


class ProgressCell(Base):
    """Progress of one stage at one location (or of a whole-project stage: location empty), from approved daily reports."""

    __tablename__ = "progress_cells"

    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_stages.id", ondelete="CASCADE"), nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_locations.id", ondelete="CASCADE"))
    progress: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, server_default="0")
    progress_on: Mapped[date | None] = mapped_column(Date)  # date of the report that set it
    record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # that daily report
    started_on: Mapped[date | None] = mapped_column(Date)
    finished_on: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = created()


class ProgressSnapshot(Base):
    """The project's progress on a day (S-curve)."""

    __tablename__ = "progress_snapshots"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    actual: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    planned: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
