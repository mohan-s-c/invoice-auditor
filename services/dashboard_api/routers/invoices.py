"""Dashboard, flag queue, invoice detail + human disposition (the core invoice domain)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from libs.common import db, rbac
from libs.common.audit import trail
from libs.modelserve.provider import get_provider
from services.agent import autonomy
from services.dashboard_api.scoping import flag_row, scope, scoped
from services.learning.capture import label_stats, record_disposition

router = APIRouter(tags=["invoices"])

_ACTION_STATUS = {"approve": "approved", "reject": "rejected", "hold": "held",
                  "escalate": "escalated", "dismiss": "cleared", "recover": "recovery"}
# Actions that only make sense before money has gone out the door, and after.
_UNPAID_ONLY = {"reject", "hold"}   # can't stop a payment that already cleared
_PAID_ONLY = {"recover"}            # nothing to claw back if it hasn't been paid


@router.get("/api/dashboard")
def dashboard():
    invs = scoped(db.query("SELECT * FROM invoices"))
    flags = [flag_row(r) for r in scoped(db.query("SELECT * FROM flags WHERE status='open'"))]
    cleared = sum(1 for i in invs if i["status"] == "cleared")
    cat: dict[str, float] = {}
    for i in invs:
        cat[i["category"]] = cat.get(i["category"], 0) + i["amount"]
    anom: dict[str, int] = {}
    for f in flags:
        anom[f["anomaly_type"]] = anom.get(f["anomaly_type"], 0) + 1
    reg: dict[str, dict] = {}
    for i in invs:
        d = reg.setdefault(i["region"], {"spend": 0.0, "brands": set()})
        d["spend"] += i["amount"]
        d["brands"].add(i["brand"])
    regions = [{"region": k, "spend": round(v["spend"]), "brands": len(v["brands"])}
               for k, v in sorted(reg.items(), key=lambda kv: -kv[1]["spend"])]
    return {
        "kpis": {
            "filed": len(invs),
            "flagged": len(flags),
            "at_risk": round(sum(f["amount"] for f in flags)),
            "auto_cleared_pct": round(cleared / len(invs) * 100) if invs else 0,
            "recoverable": round(sum(f["recoverable"] for f in flags)),
        },
        "category_spend": [{"category": k, "amount": round(v)} for k, v in
                           sorted(cat.items(), key=lambda kv: -kv[1])],
        "anomalies": [{"type": k, "count": v} for k, v in
                      sorted(anom.items(), key=lambda kv: -kv[1])],
        "regions": regions,
        "recent_flags": sorted(flags, key=lambda f: -f["amount"])[:5],
        "scope": scope() or "All brands",
    }


@router.get("/api/flags")
def flags(brand: str | None = None, category: str | None = None,
          severity: str | None = None, status: str | None = "open"):
    rows = [flag_row(r) for r in scoped(db.query("SELECT * FROM flags ORDER BY amount DESC"))]
    if status and status != "all":
        rows = [r for r in rows if r["status"] == status]
    if brand:
        rows = [r for r in rows if r["brand"] == brand]
    if category:
        rows = [r for r in rows if r["category"] == category]
    if severity:
        rows = [r for r in rows if r["severity"].lower() == severity.lower()]
    at_risk = round(sum(r["amount"] for r in rows))
    return {"flags": rows, "count": len(rows), "at_risk": at_risk}


@router.get("/api/invoices/{invoice_id}")
def invoice_detail(invoice_id: str):
    inv = db.query_one("SELECT * FROM invoices WHERE id=?", (invoice_id,))
    if not inv or not rbac.visible(inv["region"]):
        raise HTTPException(404, "invoice not found in your scope")
    inv = dict(inv)
    inv["paid"] = bool(inv["paid"])
    lines = [dict(r) for r in db.query("SELECT * FROM invoice_lines WHERE invoice_id=?",
                                       (invoice_id,))]
    flag = db.query_one("SELECT * FROM flags WHERE invoice_id=?", (invoice_id,))
    agent = None
    if flag:
        flag = dict(flag)
        flag["rationale"] = db.loads(flag["rationale"]) or []
        narrative = get_provider().complete(
            "You are an invoice controls analyst.",
            f"Invoice {invoice_id} flagged for {flag['anomaly_type']}; recommend a disposition.")
        recoverable_txt = (f" (est. recoverable ${flag['recoverable']:,.0f})"
                           if flag["recoverable"] else "")
        if inv["paid"]:
            rec = ("Invoice already paid — recommend opening a recovery/clawback case for the "
                   "flagged lines" + recoverable_txt + "; pursue a vendor credit or refund.")
        else:
            rec = ("Recommend a partial hold: keep clean lines; reject the flagged lines"
                   + recoverable_txt + ".")
        agent = {"action": flag["recommended_action"], "confidence": flag["confidence"],
                 "autonomy": autonomy.level_for(flag["anomaly_type"]),
                 "recoverable": flag["recoverable"], "recommendation": rec,
                 "narrative": narrative, "rationale": flag["rationale"], "gate": True,
                 "model_version": flag["model_version"]}
    return {"invoice": inv, "lines": lines, "flag": flag, "agent": agent,
            "audit": trail(target=invoice_id)}


class DispositionReq(BaseModel):
    action: str  # approve | reject | hold | escalate | dismiss | recover
    note: str | None = None


class DispositionResponse(BaseModel):
    invoice_id: str
    status: str
    labels: dict[str, int]


@router.post("/api/invoices/{invoice_id}/disposition", response_model=DispositionResponse)
def disposition(invoice_id: str, req: DispositionReq):
    inv = db.query_one("SELECT * FROM invoices WHERE id=?", (invoice_id,))
    if not inv or not rbac.visible(inv["region"]):
        raise HTTPException(404, "invoice not found in your scope")
    if req.action not in _ACTION_STATUS:
        raise HTTPException(400, f"unknown action {req.action}")
    paid = bool(inv["paid"])
    if paid and req.action in _UNPAID_ONLY:
        raise HTTPException(409, f"invoice already paid — cannot {req.action}; "
                                 "use 'recover' to open a recovery/clawback case")
    if not paid and req.action in _PAID_ONLY:
        raise HTTPException(409, "invoice not yet paid — nothing to recover; "
                                 "reject or place a hold instead")
    flag = db.query_one("SELECT * FROM flags WHERE invoice_id=?", (invoice_id,))
    flag_id = flag["id"] if flag else None
    new_status = _ACTION_STATUS[req.action]
    actor = rbac.current_role()
    record_disposition(flag_id or "", invoice_id, actor["id"], req.action,
                       before={"status": flag["status"] if flag else inv["status"]},
                       after={"status": new_status, "note": req.note},
                       model_version=flag["model_version"] if flag else None)
    if flag:
        db.execute("UPDATE flags SET status=? WHERE id=?", (new_status, flag_id))
    db.execute("UPDATE invoices SET status=? WHERE id=?",
               ("cleared" if req.action == "approve" else new_status, invoice_id))
    return {"invoice_id": invoice_id, "status": new_status, "labels": label_stats()}
