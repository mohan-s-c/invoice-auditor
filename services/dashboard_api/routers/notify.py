"""Notification bell (legacy) + threshold-based email routing to RP/Ops: outbox, dispatch, policy."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from libs.common import db, rbac
from libs.common.audit import AuditEvent, record
from libs.common.config import settings
from services.dashboard_api.scoping import flag_row, scope, scoped
from services.notify import dispatch as notify_dispatch
from services.notify import policy as notify_policy_mod

router = APIRouter(tags=["notify"])


@router.get("/api/notifications")
def notifications():
    flags = [flag_row(r) for r in scoped(
        db.query("SELECT * FROM flags WHERE status='open' ORDER BY amount DESC"))]
    sev_rank = {"critical": 0, "high": 1, "medium": 2}
    flags.sort(key=lambda f: (sev_rank.get(f["severity"], 3), -f["amount"]))
    items = [{
        "severity": f["severity"], "anomaly_type": f["anomaly_type"], "vendor": f["vendor"],
        "brand": f["brand"], "amount": f["amount"], "invoice_id": f["invoice_id"],
        "recoverable": f["recoverable"], "recommended_action": f["recommended_action"],
        "route": f"to Kyle + RP {f['region']}",
    } for f in flags[:10]]
    return {"unread": len(items), "items": items}


@router.get("/api/notify/outbox")
def notify_outbox(limit: int = 200):
    """Notifications routed for the current scope (RP sees only their region)."""
    items = notify_dispatch.outbox(region=scope(), limit=limit)
    return {"items": items, "count": len(items),
            "queued": sum(1 for i in items if i["status"] == "queued"),
            "sent": sum(1 for i in items if i["status"] == "sent"),
            "provider": settings.notify_provider,
            "external_email_enabled": settings.allow_external_email}


class DispatchResponse(BaseModel):
    considered: int
    notified_flags: int
    queued: int
    sent: int
    skipped_below_threshold: int
    skipped_already_notified: int
    provider: str
    external_email_enabled: bool


@router.post("/api/notify/dispatch", response_model=DispatchResponse)
def notify_run(force: bool = False):
    """Evaluate open flags against the policy and send/queue notifications. HQ-only."""
    if rbac.current_role()["region"] is not None:
        raise HTTPException(403, "only HQ can run a notification dispatch")
    return notify_dispatch.dispatch_notifications(force=force)


class ThresholdsResponse(BaseModel):
    categories: dict[str, float]
    default: float
    always_notify_severity: list[str]


@router.get("/api/notify/policy", response_model=ThresholdsResponse)
def notify_policy():
    return notify_policy_mod.get_thresholds()


class ThresholdsReq(BaseModel):
    categories: dict[str, float] | None = None
    default: float | None = None


@router.patch("/api/notify/policy", response_model=ThresholdsResponse)
def notify_policy_update(req: ThresholdsReq):
    """Edit per-category notification thresholds. HQ-only."""
    actor = rbac.current_role()
    if actor["region"] is not None:
        raise HTTPException(403, "only HQ can edit notification thresholds")
    t = notify_policy_mod.set_thresholds(req.categories or {}, req.default)
    record(AuditEvent("human", actor["id"], "notify.thresholds.update", "policy", after=t))
    return t
