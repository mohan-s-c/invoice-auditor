"""Notifier interface (next-phase §) — the ONLY place that sends email.

A real provider (Microsoft Graph / SMTP) slots in behind the ``Notifier`` Protocol. The default
``OfflineNotifier`` never sends — it returns 'queued' so the app is fully demoable offline and
no message leaves the environment unless a real provider is configured AND egress is allowed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class EmailMessage:
    to_name: str
    to_email: str
    subject: str
    body: str
    kind: str = "to"   # 'to' | 'cc'


@dataclass
class SendResult:
    status: str        # 'queued' | 'sent' | 'failed'
    provider: str
    detail: str = ""


class EmailEgressError(RuntimeError):
    """Raised if a real send is attempted while external email egress is disabled."""


class Notifier(Protocol):
    name: str
    def send(self, msg: EmailMessage) -> SendResult: ...
