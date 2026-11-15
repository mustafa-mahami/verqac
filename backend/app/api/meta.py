from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import Ctx, ctx
from app.models.core import Discipline, Role
from app.schemas.core import DisciplineOut, RoleOut

router = APIRouter(tags=["settings"])


@router.get("/roles", response_model=list[RoleOut])
def list_roles(c: Ctx = Depends(ctx)):
    return c.db.scalars(select(Role).where(Role.org_id.is_(None)).order_by(Role.sort)).all()


@router.get("/orgs/{org_id}/disciplines", response_model=list[DisciplineOut])
def list_disciplines(org_id: UUID, c: Ctx = Depends(ctx)):
    return c.db.scalars(select(Discipline).where(Discipline.org_id == org_id, Discipline.is_active)
                        .order_by(Discipline.sort)).all()
