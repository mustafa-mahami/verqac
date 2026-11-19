from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, update

from app.core.deps import Ctx, ctx
from app.models.records import Notification

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationOut(BaseModel):
    id: int
    record_id: str | None
    project_id: str | None = None
    event: str
    title_ar: str
    title_en: str
    body: str | None
    created_at: datetime
    read: bool


class NotificationsOut(BaseModel):
    unread: int
    items: list[NotificationOut]


class ReadIn(BaseModel):
    ids: list[int] = []
    all: bool = False


@router.get("", response_model=NotificationsOut)
def list_notifications(c: Ctx = Depends(ctx)):
    mine = Notification.user_id == c.user.id
    unread = c.db.scalar(select(func.count()).where(mine, Notification.read_at.is_(None)))
    rows = c.db.scalars(select(Notification).where(mine).order_by(Notification.created_at.desc()).limit(30))
    return NotificationsOut(unread=unread, items=[
        NotificationOut(id=n.id, record_id=str(n.record_id) if n.record_id else None,
                        project_id=str(n.project_id) if n.project_id else None, event=n.event,
                        title_ar=n.title_ar, title_en=n.title_en, body=n.body, created_at=n.created_at,
                        read=n.read_at is not None) for n in rows])


@router.post("/read", status_code=204)
def mark_read(body: ReadIn, c: Ctx = Depends(ctx)):
    q = update(Notification).where(Notification.user_id == c.user.id, Notification.read_at.is_(None))
    if not body.all:
        q = q.where(Notification.id.in_(body.ids))
    c.db.execute(q.values(read_at=datetime.now(UTC)))
