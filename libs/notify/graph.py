"""Microsoft Graph notifier (M365 / Outlook) — client-credentials, stdlib urllib (no SDK).

Real send only; guarded by ``get_notifier`` which refuses to construct a real provider unless
``allow_external_email`` is true. Sends via POST /v1.0/users/{from}/sendMail.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from libs.common.config import settings

from .base import EmailMessage, SendResult

_TOKEN_URL = "https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"


class MicrosoftGraphNotifier:
    name = "graph"

    def _token(self) -> str:
        data = urllib.parse.urlencode({
            "client_id": settings.graph_client_id,
            "client_secret": settings.graph_client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        }).encode()
        url = _TOKEN_URL.format(tenant=settings.graph_tenant_id)
        with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
            return json.loads(r.read())["access_token"]

    def send(self, msg: EmailMessage) -> SendResult:
        token = self._token()
        payload = {
            "message": {
                "subject": msg.subject,
                "body": {"contentType": "Text", "content": msg.body},
                "toRecipients": [{"emailAddress": {"address": msg.to_email}}],
            },
            "saveToSentItems": True,
        }
        url = _SENDMAIL_URL.format(sender=urllib.parse.quote(settings.notify_from))
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            code = r.getcode()
        return SendResult(status="sent" if code in (200, 202) else "failed",
                          provider=self.name, detail=f"graph sendMail HTTP {code}")
