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
    project_type_id: UUID | None = None  # copies the type's stages and locations into the project


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


class ProjectStats(BaseModel):
    records: int = 0  # record numbers (all revisions of a number count once)
    open: int = 0  # submitted, waiting for an answer
    overdue: int = 0  # open past the reply date


class ProjectListItem(BaseModel):
    project: ProjectOut
    my_role: RoleOut | None
    parties: list[PartyOut]
    stats: ProjectStats = ProjectStats()


class NotifyChannels(BaseModel):
    email: bool = False
    mahami: bool = False


class SubmittalKind(BaseModel):
    code: str | None = Field(default=None, max_length=40)  # empty for a new kind: the server assigns one
    name_ar: str = Field(max_length=100)  # emptiness is checked by the endpoint, with its own error code
    name_en: str = Field(max_length=100)
    active: bool = True


class HolidayIO(BaseModel):
    from_: date = Field(alias="from")
    to: date | None = None
    name: str = Field(default="", max_length=100)
    model_config = {"populate_by_name": True}

    def stored(self) -> dict:
        return {"from": self.from_.isoformat(), "to": (self.to or self.from_).isoformat(), "name": self.name.strip()}


class OrgCalendar(BaseModel):
    weekend: list[int] = [5]  # 0 = Sunday ... 6 = Saturday
    holidays: list[HolidayIO] = []


class ProjectCalendar(BaseModel):
    weekend: list[int] | None = None  # None: the organization's
    holidays: list[HolidayIO] = []  # in addition to the organization's
    work_start: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    work_end: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


class ProjectSettingsOut(BaseModel):
    reply_hours: dict[str, int]  # record type code -> hours the responder has to answer
    resubmit_hours: dict[str, int]  # record type code -> hours the author has to resubmit after "revise"/"reject"
    link_submittals: bool = False  # inspections show and link the approved submittals of their stage
    checklists: bool = False  # inspections are answered against their topic's checklist
    reminders: bool = True  # reminders before and after reply / resubmission deadlines
    party_sees_all: bool = False  # staff see every record of their own company, not only their disciplines
    routing: dict[str, str] = {}  # record type code -> discipline | manager | choose
    calendar: ProjectCalendar = ProjectCalendar()
    types: list[str] = []  # record types the project uses
    start_date: date | None = None  # daily reports are numbered from it
    end_date: date | None = None
    org_calendar: OrgCalendar = OrgCalendar()  # the owner organization's, read only here
    notify: NotifyChannels
    submittal_kinds: list[SubmittalKind]
    has_header: bool = False  # a letterhead banner was uploaded
    email_available: bool  # SMTP configured on the server
    mahami_available: bool  # Mahami URL and key configured on the server
    can_edit: bool


class ProjectSettingsIn(BaseModel):
    reply_hours: dict[str, int] = {}
    resubmit_hours: dict[str, int] = {}
    link_submittals: bool | None = None
    checklists: bool | None = None
    reminders: bool | None = None
    party_sees_all: bool | None = None
    routing: dict[str, str] = {}
    calendar: ProjectCalendar | None = None
    types: list[str] | None = None
    dates: dict[str, date | None] | None = None  # start_date / end_date
    notify: NotifyChannels | None = None
    submittal_kinds: list[SubmittalKind] | None = None


class DisciplineOut(Out):
    id: UUID
    code: str
    name_ar: str
    name_en: str


# ---- team, parties, invitations (phase 1)
from datetime import datetime  # noqa: E402


class InviteOut(BaseModel):
    link: str
    email: str
    email_sent: bool
    expires_at: datetime


class PendingInvite(BaseModel):
    email: str
    expires_at: datetime


class TeamParty(PartyOut):
    can_manage_team: bool
    pending_invite: PendingInvite | None


class MemberOut(BaseModel):
    id: UUID
    user: UserOut
    party_id: UUID
    role: RoleOut
    discipline_ids: list[UUID]
    is_active: bool


class TeamOut(BaseModel):
    project: ProjectOut
    can_manage_project: bool
    my_party_id: UUID | None
    parties: list[TeamParty]
    members: list[MemberOut]


class PartyIn(BaseModel):
    kind: Literal["consultant", "owner"]
    placeholder_name: str = Field(min_length=2, max_length=200)
    email: EmailStr | None = None


class PartyInviteIn(BaseModel):
    email: EmailStr


class MemberIn(BaseModel):
    party_id: UUID
    user_id: UUID
    role_id: UUID
    discipline_ids: list[UUID] = []


class MemberPatch(BaseModel):
    role_id: UUID | None = None
    discipline_ids: list[UUID] | None = None
    is_active: bool | None = None


class MemberProject(BaseModel):
    project_id: UUID
    code: str
    name_ar: str
    name_en: str
    role: RoleOut
    is_active: bool


class OrgMemberOut(BaseModel):
    user: UserOut
    org_role: str
    is_active: bool = True
    projects: list[MemberProject] = []


class OrgMemberPatch(BaseModel):
    is_active: bool | None = None
    org_role: Literal["admin", "member"] | None = None


class TeamInviteIn(BaseModel):
    """Invite a new colleague into the organization and straight into this project's team."""
    email: EmailStr
    role_id: UUID
    discipline_ids: list[UUID] = []


class OrgInviteIn(BaseModel):
    email: EmailStr
    org_role: Literal["admin", "member"] = "member"


class InvitationInfo(BaseModel):
    kind: str
    email: str
    status: Literal["valid", "accepted", "expired"]
    user_exists: bool
    inviter_name_ar: str
    inviter_name_en: str
    org: OrgOut | None  # the org joined (org_member) or the inviting project owner org
    project: ProjectOut | None
    party_kind: str | None
    party_placeholder: str | None
    role: RoleOut | None


class AcceptIn(BaseModel):
    # new user (when the e-mail is not registered yet)
    full_name_ar: str | None = Field(default=None, min_length=2, max_length=200)
    full_name_en: str | None = Field(default=None, min_length=2, max_length=200)
    password: str | None = Field(default=None, min_length=10, max_length=128)
    locale: Locale = "ar"
    # project party: join with an existing organization, or create one
    org_id: UUID | None = None
    org_name_ar: str | None = Field(default=None, min_length=2, max_length=200)
    org_name_en: str | None = Field(default=None, min_length=2, max_length=200)
