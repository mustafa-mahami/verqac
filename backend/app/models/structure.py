"""Project structure: project types with templates (per organization), and each project's own
stages (weighted work stages) and locations (buildings / zones and their floors / sections).

Stages and locations are copied from the project type's template when a project is created,
then edited per project. Records point at a stage and at locations; inspections will too.
"""
import uuid
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.core import Base, pk

STAGE_SCOPES = ("per_location", "whole")
LOCATION_KINDS = ("group", "unit")  # group: building / zone; unit: floor / section, inside a group


class ProjectType(Base):
    """An organization's kind of project (buildings, roads, water...) and its templates."""

    __tablename__ = "project_types"
    __table_args__ = (UniqueConstraint("org_id", "code"),)

    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    # what a location group and a unit are called in this kind of project (مبنى / طابق, مقطع...)
    group_label_ar: Mapped[str] = mapped_column(String(40), nullable=False)
    group_label_en: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_label_ar: Mapped[str] = mapped_column(String(40), nullable=False)
    unit_label_en: Mapped[str] = mapped_column(String(40), nullable=False)
    stages: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")  # [{name_ar,name_en,scope,weight,topics}]
    units: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")   # [{name_ar,name_en}] per group
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class ProjectStage(Base):
    __tablename__ = "project_stages"
    __table_args__ = (CheckConstraint(f"scope IN {STAGE_SCOPES}", name="scope_valid"),)

    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name_ar: Mapped[str] = mapped_column(String(150), nullable=False)
    name_en: Mapped[str] = mapped_column(String(150), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, server_default="per_location")
    weight: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class ProjectStageTopic(Base):
    """A subject under a stage (Structure: footings, columns, slabs...). Requests pick one instead of typing it."""

    __tablename__ = "project_stage_topics"

    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_stages.id", ondelete="CASCADE"), nullable=False, index=True)
    name_ar: Mapped[str] = mapped_column(String(150), nullable=False)
    name_en: Mapped[str] = mapped_column(String(150), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    # inspection checklist [{ar, en}], copied into an inspection request when it is submitted
    checklist: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")


class ProjectLocation(Base):
    __tablename__ = "project_locations"
    __table_args__ = (
        CheckConstraint(f"kind IN {LOCATION_KINDS}", name="kind_valid"),
        CheckConstraint("(kind = 'group') = (parent_id IS NULL)", name="units_have_a_group"),
    )

    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_locations.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


STRUCTURE_TABLES = ["project_types", "project_stages", "project_locations"]
TOPIC_TABLES = ["project_stage_topics"]
