"""Who is told about a record event, and how.

In-app notifications (the bell and the "awaiting me" screen) always work. E-mail and Mahami
are chosen per project in its settings, so a project can stay quiet outside the platform.
External sends run after the transaction commits (BackgroundTasks) and never fail the request.
"""
import json
import logging
import urllib.request
import uuid

from fastapi import BackgroundTasks
from sqlalchemy import insert, select

from app.core.config import get_settings
from app.core.deps import Ctx
from app.core.mailer import mail_enabled, send_mail
from app.models.core import Discipline, Project, ProjectMember, Role, RolePermission, User
from app.models.records import Notification, Record, RecordType

log = logging.getLogger("verqac.notify")


def channels(project: Project) -> dict[str, bool]:
    saved = (project.settings or {}).get("notify", {})
    return {"email": bool(saved.get("email", False)), "mahami": bool(saved.get("mahami", False))}


def mahami_enabled() -> bool:
    s = get_settings()
    return bool(s.mahami_url and s.mahami_key)


def members_who_can(c: Ctx, project_id: uuid.UUID, party_id: uuid.UUID, rt: RecordType, action: str,
                    discipline_id: uuid.UUID | None) -> list[tuple[ProjectMember, Role]]:
    """Active members of one party whose role allows `action` on this record type and discipline."""
    rows = c.db.execute(select(ProjectMember, Role).join(Role, Role.id == ProjectMember.role_id)
                        .where(ProjectMember.project_id == project_id, ProjectMember.party_id == party_id,
                               ProjectMember.is_active)).all()
    if not rows:
        return []
    perms: dict[uuid.UUID, str] = {}
    for rp in c.db.scalars(select(RolePermission).where(RolePermission.role_id.in_({r.id for _, r in rows}),
                                                        RolePermission.action == action,
                                                        RolePermission.record_type.in_([rt.code, "*"]))):
        if rp.record_type != "*" or rp.role_id not in perms:
            perms[rp.role_id] = rp.scope
    code = c.db.scalar(select(Discipline.code).where(Discipline.id == discipline_id)) if discipline_id else None
    all_ids = {d for m, _ in rows for d in m.discipline_ids}
    codes = dict(c.db.execute(select(Discipline.id, Discipline.code).where(Discipline.id.in_(all_ids))).all()) if all_ids else {}
    out = []
    for m, r in rows:
        scope = perms.get(r.id)
        if scope is None:
            continue
        mine = {codes.get(d) for d in m.discipline_ids}
        if scope == "project" or not m.discipline_ids or code is None or code in mine:
            out.append((m, r))
    return out


def notify(c: Ctx, bg: BackgroundTasks, *, project: Project, rec: Record, event: str, user_ids: set[uuid.UUID],
           title_ar: str, title_en: str, body: str | None = None) -> None:
    user_ids = {u for u in user_ids if u and u != c.user.id}
    if not user_ids:
        return
    c.db.execute(insert(Notification), [
        {"user_id": u, "project_id": project.id, "record_id": rec.id, "event": event, "title_ar": title_ar[:300],
         "title_en": title_en[:300], "body": (body or "")[:2000] or None} for u in user_ids])

    ch = channels(project)
    want_mail, want_mahami = ch["email"] and mail_enabled(), ch["mahami"] and mahami_enabled()
    if not (want_mail or want_mahami):
        return
    emails = sorted(e.lower() for e in c.db.scalars(select(User.email).where(User.id.in_(user_ids), User.is_active)))
    link = f"{get_settings().app_url.rstrip('/')}/records/{rec.id}"
    if want_mail:
        text = f"{title_ar}\n{body or ''}\n\n{title_en}\n\n{link}\n"
        for e in emails:
            bg.add_task(send_mail, e, f"Verqac: {title_en}", text)
    if want_mahami:
        bg.add_task(_post_mahami, {"emails": emails, "title": title_ar[:250], "body": (body or title_en)[:500],
                                   "url": link, "project": project.name_ar, "ref": f"verqac.record,{rec.id}"})


def _post_mahami(payload: dict) -> None:
    s = get_settings()
    req = urllib.request.Request(
        s.mahami_url.rstrip("/") + "/integrations/odoo/notify", data=json.dumps(payload).encode(), method="POST",
        headers={"X-API-Key": s.mahami_key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:  # noqa: S310 - fixed https URL from settings
            if r.status != 200:
                log.warning("Mahami notify HTTP %s", r.status)
    except Exception:  # noqa: BLE001 - never break the caller
        log.exception("Mahami notify failed")
