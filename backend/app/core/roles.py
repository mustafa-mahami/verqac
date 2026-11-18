"""Roles as one project shows them: platform roles (renamed or hidden per project) and roles added in it.

A project role is a name on top of a platform role of the same party: its permissions are a copy of that role's
and cannot be edited, so a contractor role can never carry the consultant's powers.
"""
from app.models.core import Project, Role
from app.schemas.core import RoleOut


def overrides(project: Project | None) -> dict:
    return ((project.settings or {}).get("roles") or {}) if project is not None else {}


def role_out(project: Project | None, role: Role) -> RoleOut:
    o = overrides(project).get(role.code, {}) if role.project_id is None else {}
    return RoleOut(id=role.id, code=role.code, party_kind=role.party_kind,
                   name_ar=o.get("name_ar") or role.name_ar, name_en=o.get("name_en") or role.name_en,
                   base_code=role.base_code or role.code)


def is_hidden(project: Project, role: Role) -> bool:
    return bool(overrides(project).get(role.code, {}).get("hidden"))
