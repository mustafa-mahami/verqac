from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import BackgroundTasks
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.mailer import mail_enabled, send_mail
from app.core.security import new_opaque_token
from app.models.core import Invitation, User
from app.schemas.core import InviteOut


def create_invite(
    db: Session,
    bg: BackgroundTasks,
    *,
    kind: str,
    email: str,
    inviter: User,
    subject_ar: str,
    subject_en: str,
    org_id: UUID | None = None,
    project_id: UUID | None = None,
    party_id: UUID | None = None,
    role_id: UUID | None = None,
    org_role: str | None = None,
) -> InviteOut:
    s = get_settings()
    token, token_hash = new_opaque_token()
    expires = datetime.now(UTC) + timedelta(days=s.invitation_days)
    db.add(Invitation(kind=kind, email=email.lower(), org_id=org_id, project_id=project_id, party_id=party_id,
                      role_id=role_id, org_role=org_role, token_hash=token_hash, expires_at=expires, created_by=inviter.id))
    link = f"{s.app_url.rstrip('/')}/invite/{token}"
    sent = mail_enabled()
    if sent:
        text = (
            f"{inviter.full_name_ar} دعاك إلى {subject_ar} على Verqac.\n"
            f"افتح الرابط لقبول الدعوة (صالح {s.invitation_days} يوماً):\n{link}\n\n"
            f"{inviter.full_name_en} invited you to {subject_en} on Verqac.\n"
            f"Open the link to accept (valid {s.invitation_days} days):\n{link}\n"
        )
        bg.add_task(send_mail, email, f"Verqac: {subject_en} | دعوة إلى {subject_ar}", text)
    return InviteOut(link=link, email=email.lower(), email_sent=sent, expires_at=expires)
