"""Project-level permission checks used by the services (RLS is the second line)."""
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select

from app.core.deps import Ctx
from app.models.core import OrgMember, Project, ProjectMember, ProjectParty, Role


@dataclass
class ProjectAccess:
    project: Project
    member: ProjectMember | None
    role: Role | None
    party: ProjectParty | None
    admin_org_ids: set[UUID]  # orgs in which the user is admin

    @property
    def is_owner_org_admin(self) -> bool:
        return self.project.owner_org_id in self.admin_org_ids

    @property
    def can_manage_project(self) -> bool:
        """Parties and project settings: the owning organization's admin or a role with manage_project."""
        return self.is_owner_org_admin or bool(self.role and self.role.manage_project)

    def can_manage_party_team(self, party: ProjectParty) -> bool:
        """A party's own people are managed by that party: its org admin or a manage_team role in it."""
        if party.org_id is None:
            return False
        if party.org_id in self.admin_org_ids:
            return True
        return bool(self.member and self.member.party_id == party.id and self.role and self.role.manage_team)


def project_access(c: Ctx, project_id: UUID) -> ProjectAccess:
    project = c.db.get(Project, project_id)
    if project is None:  # not found and not visible look the same
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not_found")
    row = c.db.execute(
        select(ProjectMember, Role, ProjectParty)
        .join(Role, Role.id == ProjectMember.role_id)
        .join(ProjectParty, ProjectParty.id == ProjectMember.party_id)
        .where(ProjectMember.project_id == project_id, ProjectMember.user_id == c.user.id, ProjectMember.is_active)
    ).first()
    admin_orgs = set(c.db.scalars(select(OrgMember.org_id).where(OrgMember.user_id == c.user.id,
                                                                  OrgMember.org_role == "admin")))
    member, role, party = row if row else (None, None, None)
    return ProjectAccess(project=project, member=member, role=role, party=party, admin_org_ids=admin_orgs)


def require(ok: bool, code: str = "forbidden") -> None:
    if not ok:
        raise HTTPException(status.HTTP_403_FORBIDDEN, code)
