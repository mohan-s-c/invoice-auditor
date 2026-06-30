"""SMTP notifier (Google Workspace / M365 / any relay) — stdlib smtplib, STARTTLS.

Real send only; guarded by ``get_notifier``. Works with Gmail app passwords, M365 SMTP AUTH,
or an internal relay — configured via SMTP_* settings.
"""
from __future__ import annotations

import smtplib
from email.message import EmailMessage as MIMEMessage

from libs.common.config import settings

from .base import EmailMessage, SendResult


class SmtpNotifier:
    name = "smtp"

    def send(self, msg: EmailMessage) -> SendResult:
        mime = MIMEMessage()
        mime["From"] = settings.notify_from
        mime["To"] = msg.to_email
        mime["Subject"] = msg.subject
        mime.set_content(msg.body)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as s:
            s.starttls()
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            s.send_message(mime)
        return SendResult(status="sent", provider=self.name,
                          detail=f"smtp {settings.smtp_host}:{settings.smtp_port}")
