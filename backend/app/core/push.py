"""Web Push: notifications shown by the browser even when no Verqac tab is open.

The VAPID key pair is made on first use and kept on the files volume (survives rebuilds),
so nothing needs to be added to .env.
"""
import base64
import json
import logging
import uuid
from functools import lru_cache
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid
from pywebpush import WebPushException, webpush
from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.db import session_scope
from app.models.core import PushSubscription

log = logging.getLogger("verqac.push")


@lru_cache
def _vapid() -> Vapid:
    path = Path(get_settings().files_dir) / "vapid_private.pem"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        v = Vapid()
        v.generate_keys()
        v.save_key(str(path))
        path.chmod(0o600)
    return Vapid.from_file(str(path))


def public_key() -> str:
    raw = _vapid().public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def send_push(user_ids: set[uuid.UUID], payload: dict) -> None:
    """Send to every browser of these users; forget browsers that unsubscribed (404/410)."""
    with session_scope(bypass=True) as db:
        subs = [(s.id, s.endpoint, s.p256dh, s.auth) for s in
                db.scalars(select(PushSubscription).where(PushSubscription.user_id.in_(user_ids)))]
    if not subs:
        return
    data = json.dumps(payload, ensure_ascii=False)
    sub_claim = "mailto:" + (get_settings().smtp_user or "no-reply@verqac.com")
    gone = []
    for sid, endpoint, p256dh, auth in subs:
        try:
            webpush({"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}}, data,
                    vapid_private_key=_vapid(), vapid_claims={"sub": sub_claim}, ttl=86400, timeout=10)
        except WebPushException as e:
            if e.response is not None and e.response.status_code in (404, 410):
                gone.append(sid)
            else:
                log.warning("push failed: %s", e)
        except Exception:  # noqa: BLE001 - never break the caller
            log.exception("push failed")
    if gone:
        with session_scope(bypass=True) as db:
            db.execute(delete(PushSubscription).where(PushSubscription.id.in_(gone)))
