"""Notifier selection + egress guard.

Default is the OfflineNotifier (queues, never sends). A real provider is only constructed when
``allow_external_email`` is explicitly true — otherwise we fall back to offline (mirrors the
LLM provider's offline fallback) so a misconfiguration can never silently leak email.
"""
from __future__ import annotations

import structlog

from libs.common.config import settings

from .base import EmailMessage, EmailEgressError, Notifier, SendResult
from .offline import OfflineNotifier

log = structlog.get_logger("notify")

__all__ = ["EmailMessage", "EmailEgressError", "Notifier", "SendResult", "get_notifier"]


def get_notifier() -> Notifier:
    provider = settings.notify_provider
    if provider == "offline":
        return OfflineNotifier()
    if not settings.allow_external_email:
        log.warning("notify.egress_blocked", provider=provider,
                    msg="external email disabled — falling back to offline (set "
                        "ALLOW_EXTERNAL_EMAIL=true to enable)")
        return OfflineNotifier()
    if provider == "graph":
        from .graph import MicrosoftGraphNotifier
        return MicrosoftGraphNotifier()
    if provider == "smtp":
        from .smtp import SmtpNotifier
        return SmtpNotifier()
    log.warning("notify.unknown_provider", provider=provider)
    return OfflineNotifier()
