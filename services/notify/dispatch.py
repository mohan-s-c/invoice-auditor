"""Notification dispatcher (next-phase §) — turn open flags into routed email notifications.

For each open flag that clears the policy, compose an email per recipient, hand it to the
configured Notifier (offline by default → queued), and persist it to the outbox with an audit
row. Idempotent: a flag already in the outbox is skipped unless ``force`` is set.
"""
from __future__ import annotations

import datetime as dt

from libs.common import db
from libs.common.audit import AuditEvent, record
from libs.common.config import settings
from libs.notify import EmailMessage, get_notifier

from . import policy


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _compose(flag: dict, rcpt: dict) -> EmailMessage:
    paid = bool(flag.get("paid"))
    money = (f"Already PAID — open a recovery/clawback case (est. recoverable "
             f"${flag['recoverable']:,.0f})." if paid else
             f"Not yet paid — can be held or rejected before payment (est. recoverable "
             f"${flag['recoverable']:,.0f}).")
    subject = (f"[Invoice Auditor] {flag['severity'].title()} · {flag['anomaly_type']} · "
               f"{flag['vendor']} ({flag['brand']}) — ${flag['amount']:,.0f}")
    body = (
        f"Hello {rcpt['name']},\n\n"
        f"An invoice anomaly was detected in your scope and needs review.\n\n"
        f"  Invoice:      {flag['invoice_id']}\n"
        f"  Vendor:       {flag['vendor']}\n"
        f"  Brand/region: {flag['brand']} · {flag['region']}\n"
        f"  Category:     {flag['category']}\n"
        f"  Amount:       ${flag['amount']:,.2f}\n"
        f"  Anomaly:      {flag['anomaly_type']} ({flag['severity']}, "
        f"confidence {float(flag['confidence']):.2f})\n"
        f"  Recommended:  {flag['recommended_action']}\n"
        f"  Status:       {money}\n\n"
        f"Review and disposition: open invoice {flag['invoice_id']} in Invoice Auditor.\n\n"
        f"— Invoice Auditor (automated; a human owns the final money decision)\n"
    )
    return EmailMessage(to_name=rcpt["name"], to_email=rcpt["email"], subject=subject,
                        body=body, kind=rcpt["kind"])


def _already_sent(flag_id: str) -> bool:
    row = db.query_one("SELECT COUNT(*) AS c FROM notifications_outbox WHERE flag_id=?",
                       (flag_id,))
    return bool(row and row["c"])


def dispatch_notifications(force: bool = False) -> dict:
    """Send/queue notifications for all open flags that clear the policy. Returns counts."""
    notifier = get_notifier()
    flags = db.query("SELECT * FROM flags WHERE status='open'")
    considered = notified = queued = sent = skipped_policy = skipped_dupe = 0
    for r in flags:
        flag = dict(r)
        considered += 1
        ok, reason = policy.should_notify(flag)
        if not ok:
            skipped_policy += 1
            continue
        if _already_sent(flag["id"]) and not force:
            skipped_dupe += 1
            continue
        notified += 1
        for rcpt in policy.recipients(flag):
            msg = _compose(flag, rcpt)
            res = notifier.send(msg)
            if res.status == "sent":
                sent += 1
            elif res.status == "queued":
                queued += 1
            db.execute(
                "INSERT INTO notifications_outbox (flag_id,invoice_id,region,recipient_name,"
                "recipient_email,kind,subject,body,severity,anomaly_type,reason,provider,"
                "status,ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (flag["id"], flag["invoice_id"], flag["region"], rcpt["name"], rcpt["email"],
                 rcpt["kind"], msg.subject, msg.body, flag["severity"], flag["anomaly_type"],
                 reason, res.provider, res.status, _now()))
            record(AuditEvent("agent", "notifier", f"notify.{res.status}", flag["invoice_id"],
                              after={"to": rcpt["email"], "kind": rcpt["kind"],
                                     "reason": reason, "provider": res.provider}))
    return {"considered": considered, "notified_flags": notified, "queued": queued,
            "sent": sent, "skipped_below_threshold": skipped_policy,
            "skipped_already_notified": skipped_dupe, "provider": notifier.name,
            "external_email_enabled": settings.allow_external_email}


def outbox(region: str | None = None, limit: int = 200) -> list[dict]:
    """Most recent notifications, optionally region-scoped. Bounded like the audit trail
    (``libs.common.audit.trail``) so a large outbox can't force an unbounded read."""
    if region is not None:
        rows = db.query("SELECT * FROM notifications_outbox WHERE region=? "
                        "ORDER BY id DESC LIMIT ?", (region, limit))
    else:
        rows = db.query("SELECT * FROM notifications_outbox ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]
