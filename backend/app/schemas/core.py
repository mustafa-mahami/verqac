from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

Locale = Literal["ar", "en"]


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class RegisterOrgIn(BaseModel):
    org_kind: Literal["contractor", "consultant", "owner"] = "contractor"
    org_name_ar: str = Field(min_length=2, max_length=200)
    org_name_en: str = Field(min_length=2, max_length=200)
    full_name_ar: str = Field(min_length=2, max_length=200)
    full_name_en: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    locale: Locale = "ar"


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserOut(Out):
    id: UUID
    email: str
    full_name_ar: str
    full_name_en: str
    locale: str


class OrgOut(Out):
    id: UUID
    kind: str
    name_ar: str
    name_en: str


class MembershipOut(BaseModel):
    org: OrgOut
    org_role: str


class MeOut(BaseModel):
    user: UserOut
    orgs: list[MembershipOut]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ProjectIn(BaseModel):
    org_id: UUID
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Za-z0-9_-]+$")
    name_ar: str = Field(min_length=2, max_length=200)
    name_en: str = Field(min_length=2, max_length=200)
    client_name: str | None = Field(default=None, max_length=200)
    donor_name: str | None = Field(default=None, max_length=200)
    contract_no: str | None = Field(default=None, max_length=100)
    description: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    # names written until the consultant / owner accept their invitation (design doc section 6)
    consultant_name: str | None = Field(default=None, max_length=200)
    owner_name: str | None = Field(default=None, max_length=200)


class RoleOut(Out):
    id: UUID
    code: str
    name_ar: str
    name_en: str
    party_kind: str


class PartyOut(BaseModel):
    id: UUID
    kind: str
    status: str
    org: OrgOut | None
    placeholder_name: str | None


class ProjectOut(Out):
    id: UUID
    owner_org_id: UUID
    code: str
    name_ar: str
    name_en: str
    client_name: str | None
    donor_name: str | None
    contract_no: str | None
    description: str | None
    start_date: date | None
    end_date: date | None


class ProjectListItem(BaseModel):
    project: ProjectOut
    my_role: RoleOut | None
    parties: list[PartyOut]


class DisciplineOut(Out):
    id: UUID
    code: str
    name_ar: str
    name_en: str
