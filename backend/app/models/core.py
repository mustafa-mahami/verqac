"""Core tables: identity, organizations, roles, projects, parties, membership, audit.

Design doc sections 2, 3 and 8. Every id is a UUID. Organization-scoped and
project-scoped tables carry org_id / project_id so RLS policies can filter them.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )


def created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


ORG_KINDS = ("contractor", "consultant", "owner", "subcontractor", "laboratory", "designer")
PARTY_KINDS = ("contractor", "consultant", "owner")


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (CheckConstraint(f"kind IN {ORG_KINDS}", name="kind_valid"),)

    id: Mapped[uuid.UUID] = pk()
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    default_locale: Mapped[str] = mapped_column(String(5), nullable=False, server_default="ar")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default="Asia/Hebron")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = created()


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = pk()
    # stored lower-case; uniqueness enforced by a unique index on email
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    full_name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    full_name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    locale: Mapped[str] = mapped_column(String(5), nullable=False, server_default="ar")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created()


class OrgMember(Base):
    __tablename__ = "org_members"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id"),
        CheckConstraint("org_role IN ('admin', 'member')", name="org_role_valid"),
    )

    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    org_role: Mapped[str] = mapped_column(String(10), nullable=False, server_default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = created()


class Discipline(Base):
    __tablename__ = "disciplines"
    __table_args__ = (UniqueConstraint("org_id", "code"),)

    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)  # used in numbering, e.g. C, E, M
    name_ar: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class Role(Base):
    """A role is data. org_id NULL = platform role (template); orgs copy and edit them."""

    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("org_id", "code"),
        CheckConstraint(f"party_kind IN {PARTY_KINDS}", name="party_kind_valid"),
    )

    id: Mapped[uuid.UUID] = pk()
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(40), nullable=False)
    name_ar: Mapped[str] = mapped_column(String(100), nullable=False)
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)
    party_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    # project-level abilities that are not tied to a record type
    manage_project: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    manage_team: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    act_on_behalf: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    view_dashboards: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    sort: Mapped[int] = mapped_column(Integer, nullable=False, server_default="10")


RECORD_ACTIONS = ("view", "create", "edit", "submit", "respond", "cancel", "delete", "export")
PERMISSION_SCOPES = ("project", "disciplines", "assigned")


class RolePermission(Base):
    """Permission = role x record type x action, within a scope (design doc section 3)."""

    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("role_id", "record_type", "action"),
        CheckConstraint(f"action IN {RECORD_ACTIONS}", name="action_valid"),
        CheckConstraint(f"scope IN {PERMISSION_SCOPES}", name="scope_valid"),
    )

    id: Mapped[uuid.UUID] = pk()
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id", ondelete="CASCADE"), nullable=False, index=True)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)  # record type code, '*' = all
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, server_default="project")


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("owner_org_id", "code"),)

    id: Mapped[uuid.UUID] = pk()
    owner_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)  # {PRJ} in numbering patterns
    name_ar: Mapped[str] = mapped_column(String(200), nullable=False)
    name_en: Mapped[str] = mapped_column(String(200), nullable=False)
    client_name: Mapped[str | None] = mapped_column(String(200))
    donor_name: Mapped[str | None] = mapped_column(String(200))
    contract_no: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # FK added by migration 0008 (project_types is created after this table)
    project_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = created()


class ProjectParty(Base):
    """An organization taking part in a project. Before the invitation is accepted
    the party exists with only placeholder_name (org_id NULL)."""

    __tablename__ = "project_parties"
    __table_args__ = (
        UniqueConstraint("project_id", "org_id"),
        CheckConstraint(f"kind IN {PARTY_KINDS}", name="party_kind_valid"),
        CheckConstraint("status IN ('invited', 'active', 'removed')", name="status_valid"),
        CheckConstraint("org_id IS NOT NULL OR placeholder_name IS NOT NULL", name="has_name"),
    )

    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    placeholder_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(10), nullable=False, server_default="active")
    created_at: Mapped[datetime] = created()


class ProjectMember(Base):
    """Membership = user + project + party + role + disciplines."""

    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    id: Mapped[uuid.UUID] = pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    party_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project_parties.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    discipline_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, server_default="{}")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = created()


class Invitation(Base):
    __tablename__ = "invitations"
    __table_args__ = (CheckConstraint("kind IN ('org_member', 'project_party')", name="kind_valid"),)

    id: Mapped[uuid.UUID] = pk()
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    org_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    party_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_parties.id", ondelete="CASCADE"))
    role_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("roles.id"))
    org_role: Mapped[str | None] = mapped_column(String(10))  # org_member invitations: admin | member
    # org_member invitation sent from a project team: joins that project with role + disciplines on acceptance
    discipline_ids: Mapped[list[uuid.UUID] | None] = mapped_column(ARRAY(UUID(as_uuid=True)))
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = created()


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # revoked because it was renewed
    user_agent: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = created()


class AuditLog(Base):
    """Append-only. The application role has INSERT and SELECT only (see migration)."""

    __tablename__ = "audit_log"
    # no RETURNING on insert: the writer may not be allowed to read its audit row back
    __table_args__ = {"implicit_returning": False}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    on_behalf_of: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    channel: Mapped[str] = mapped_column(String(20), nullable=False, server_default="web")  # web | mahami | system | import
    entity: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    changes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    ip: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(String(300))
