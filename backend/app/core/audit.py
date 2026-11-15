from typing import Any
from uuid import UUID

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.models.core import AuditLog


def audit(
    db: Session,
    *,
    entity: str,
    action: str,
    entity_id: Any = None,
    actor: UUID | None = None,
    org_id: UUID | None = None,
    project_id: UUID | None = None,
    on_behalf_of: UUID | None = None,
    changes: dict | None = None,
    channel: str = "web",
    ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Append one audit row. Plain INSERT without RETURNING: the writer may not be
    allowed to read the row back (audit SELECT is limited to admins and project members)."""
    db.execute(
        insert(AuditLog).values(
            entity=entity,
            action=action,
            entity_id=str(entity_id) if entity_id is not None else None,
            actor_user_id=actor,
            org_id=org_id,
            project_id=project_id,
            on_behalf_of=on_behalf_of,
            changes=changes or {},
            channel=channel,
            ip=ip,
            user_agent=user_agent,
        )
    )


def diff(before: dict, after: dict) -> dict:
    """{field: [old, new]} for changed fields, JSON-safe."""
    out = {}
    for k, v in after.items():
        if before.get(k) != v:
            out[k] = [_j(before.get(k)), _j(v)]
    return out


def _j(v: Any) -> Any:
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    return str(v)
