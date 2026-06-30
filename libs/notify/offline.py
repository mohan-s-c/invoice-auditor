"""Offline notifier (default) — queues, never sends. Keeps the app demoable with no egress."""
from __future__ import annotations

from .base import EmailMessage, SendResult


class OfflineNotifier:
    name = "offline"

    def send(self, msg: EmailMessage) -> SendResult:
        # Intentionally does not transmit. The dispatcher persists the message to the outbox;
        # 'queued' means "composed and routed, awaiting a real provider".
        return SendResult(status="queued", provider=self.name,
                          detail="offline — message queued, not transmitted")
