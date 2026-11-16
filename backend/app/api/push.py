"""Browser push subscriptions of the signed-in user."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.core import push
from app.core.deps import Ctx, ctx
from app.models.core import PushSubscription

router = APIRouter(prefix="/push", tags=["push"])


class Keys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class SubscriptionIn(BaseModel):
    endpoint: str = Field(max_length=2000, pattern=r"^https://")
    keys: Keys


class EndpointIn(BaseModel):
    endpoint: str = Field(max_length=2000)


@router.get("/key")
def key():
    return {"public_key": push.public_key()}


@router.post("/subscribe", status_code=204)
def subscribe(body: SubscriptionIn, c: Ctx = Depends(ctx)):
    # one row per browser; a browser that changes user follows the new user
    from app.core.db import session_scope
    with session_scope(bypass=True) as db:
        db.execute(delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    c.db.add(PushSubscription(user_id=c.user.id, endpoint=body.endpoint, p256dh=body.keys.p256dh,
                              auth=body.keys.auth, user_agent=c.meta.user_agent))


@router.post("/unsubscribe", status_code=204)
def unsubscribe(body: EndpointIn, c: Ctx = Depends(ctx)):
    c.db.execute(delete(PushSubscription).where(PushSubscription.endpoint == body.endpoint,
                                                PushSubscription.user_id == c.user.id))


@router.get("/status")
def status(c: Ctx = Depends(ctx)):
    n = len(c.db.scalars(select(PushSubscription.id).where(PushSubscription.user_id == c.user.id)).all())
    return {"devices": n}
