"""Plain SMTP sender. Called after the transaction commits (FastAPI BackgroundTasks),
so a slow or failing mail server never blocks or rolls back the request."""
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

log = logging.getLogger("verqac.mail")


def mail_enabled() -> bool:
    return bool(get_settings().smtp_host)


def send_mail(to: str, subject: str, text: str, html: str | None = None) -> None:
    s = get_settings()
    if not s.smtp_host:
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = s.smtp_from, to, subject
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            if s.smtp_starttls:
                smtp.starttls()
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
    except Exception:  # noqa: BLE001 - mail must never break the caller
        log.exception("mail to %s failed", to)
