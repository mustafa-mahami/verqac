from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Scope = Literal["per_location", "whole"]


class TemplateUnit(BaseModel):
    name_ar: str = Field(max_length=150)
    name_en: str = Field(max_length=150)


class CheckItem(BaseModel):
    """One line of an inspection checklist."""
    ar: str = Field(max_length=300)
    en: str = Field(default="", max_length=300)


class TemplateTopic(TemplateUnit):
    checklist: list[CheckItem] = Field(default=[], max_length=60)


class TemplateStage(BaseModel):
    name_ar: str = Field(max_length=150)
    name_en: str = Field(max_length=150)
    scope: Scope = "per_location"
    weight: Decimal = Field(default=Decimal(0), ge=0, le=100)
    topics: list[TemplateTopic] = []


class ProjectTypeIO(BaseModel):
    id: UUID | None = None  # empty for a new type
    name_ar: str = Field(max_length=100)
    name_en: str = Field(max_length=100)
    group_label_ar: str = Field(max_length=40)
    group_label_en: str = Field(max_length=40)
    unit_label_ar: str = Field(max_length=40)
    unit_label_en: str = Field(max_length=40)
    stages: list[TemplateStage] = []
    units: list[TemplateUnit] = []
    is_active: bool = True


class Labels(BaseModel):
    group_ar: str = "مبنى"
    group_en: str = "Building"
    unit_ar: str = "طابق"
    unit_en: str = "Floor"


class TopicIO(BaseModel):
    id: UUID | None = None
    name_ar: str = Field(max_length=150)
    name_en: str = Field(max_length=150)
    is_active: bool = True
    used: bool = False
    checklist: list[CheckItem] = Field(default=[], max_length=60)


class StageIO(BaseModel):
    id: UUID | None = None
    name_ar: str = Field(max_length=150)
    name_en: str = Field(max_length=150)
    scope: Scope = "per_location"
    weight: Decimal = Field(default=Decimal(0), ge=0, le=100)
    is_active: bool = True
    used: bool = False  # output only: records point at it, so it can be switched off but not deleted
    topics: list[TopicIO] = []


class UnitIO(BaseModel):
    id: UUID | None = None
    name_ar: str = Field(max_length=100)
    name_en: str = Field(max_length=100)
    is_active: bool = True
    used: bool = False


class GroupIO(UnitIO):
    units: list[UnitIO] = []


class TypeRef(BaseModel):
    id: UUID
    name_ar: str
    name_en: str


class StructureOut(BaseModel):
    project_type: TypeRef | None
    labels: Labels
    stages: list[StageIO]
    locations: list[GroupIO]
    can_edit: bool
    checklists: bool = False  # the project uses inspection checklists
    types: list[TypeRef] = []  # the owner organization's types, to apply a template (editors only)


class ApplyTypeIn(BaseModel):
    project_type_id: UUID
