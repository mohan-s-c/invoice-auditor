"""Control surface API (handoff §6 dashboard_api) — feeds the 8 designed screens.

RBAC region-scoping is enforced server-side: HQ sees all brands; a Regional President sees only
their region. Every list/KPI/flag/notification is filtered by the current role's region.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from libs.common import db, rbac
from libs.common.audit import AuditEvent, record, trail
from libs.common.config import settings
from libs.modelserve.provider import get_provider
from services import bootstrap
from services.agent import autonomy
from services.learning.capture import label_stats, record_disposition
from services.training import registry, trainer

_STATIC = Path(__file__).resolve().parent / "static"
_ACTION_STATUS = {"approve": "approved", "reject": "rejected", "hold": "held",
                  "escalate": "escalated", "dismiss": "cleared", "recover": "recovery"}
# Actions that only make sense before money has gone out the door, and after.
_UNPAID_ONLY = {"reject", "hold"}   # can't stop a payment that already cleared
_PAID_ONLY = {"recover"}            # nothing to claw back if it hasn't been paid


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    if db.query_one("SELECT COUNT(*) AS c FROM invoices")["c"] == 0:
        bootstrap.seed_all()
    yield


app = FastAPI(title="Invoice Auditor", version="0.1.0", lifespan=lifespan)


# --- scoping helpers -------------------------------------------------------
def _scope():
    return rbac.region_scope()


def _scoped(rows: list) -> list[dict]:
    s = _scope()
    return [dict(r) for r in rows if s is None or r["region"] == s]


# --- health / role ---------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/me")
def me():
    return {"role": rbac.current_role(), "roles": rbac.list_roles(),
            "model_version": registry.champion_version()}


class RoleReq(BaseModel):
    role: str


@app.post("/api/role")
def set_role(req: RoleReq):
    try:
        return {"role": rbac.set_role(req.role)}
    except ValueError as e:
        raise HTTPException(400, str(e))


# --- dashboard -------------------------------------------------------------
def _flag_row(r: dict) -> dict:
    return {"id": r["id"], "invoice_id": r["invoice_id"], "vendor": r["vendor"],
            "brand": r["brand"], "region": r["region"], "category": r["category"],
            "amount": r["amount"], "anomaly_type": r["anomaly_type"], "severity": r["severity"],
            "confidence": r["confidence"], "recommended_action": r["recommended_action"],
            "recoverable": r["recoverable"], "status": r["status"],
            "paid": bool(r["paid"]) if "paid" in r.keys() else False}


@app.get("/api/dashboard")
def dashboard():
    invs = _scoped(db.query("SELECT * FROM invoices"))
    flags = [_flag_row(r) for r in _scoped(db.query("SELECT * FROM flags WHERE status='open'"))]
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
        "scope": _scope() or "All brands",
    }


@app.get("/api/flags")
def flags(brand: str | None = None, category: str | None = None,
          severity: str | None = None, status: str | None = "open"):
    rows = [_flag_row(r) for r in _scoped(db.query("SELECT * FROM flags ORDER BY amount DESC"))]
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


# --- invoice detail + disposition -----------------------------------------
@app.get("/api/invoices/{invoice_id}")
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
    action: str  # approve | reject | hold | escalate
    note: str | None = None


@app.post("/api/invoices/{invoice_id}/disposition")
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


# --- vendors / notifications / autonomy / procurement / audit --------------
@app.get("/api/vendors")
def vendors():
    rows = db.query("SELECT * FROM vendors")
    s = _scope()
    out = [dict(r) for r in rows if s is None or r["region"] in (None, s)]
    off = sum(1 for v in out if v["contract"] == "off")
    return {"vendors": out, "off_contract_pct": round(off / len(out) * 100) if out else 0}


@app.get("/api/notifications")
def notifications():
    flags = [_flag_row(r) for r in _scoped(
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


@app.get("/api/autonomy")
def autonomy_view():
    return {"autonomy": autonomy.table(),
            "routing": [
                {"severity": "Critical", "rule": "Real-time → Kyle + Regional President (push + email)"},
                {"severity": "High", "rule": "Real-time → Regional President · digest → Kyle"},
                {"severity": "Medium", "rule": "Daily digest"},
                {"severity": "Scope", "rule": "RP sees only their brands"}],
            "guardrails": [
                {"policy": "Money decisions & high-value rejections", "value": "🔒 Human approval"},
                {"policy": "Max auto-reject value", "value": "$1,000"},
                {"policy": "Financial / PII data", "value": "🔒 Self-hosted models"},
                {"policy": "Audit logging", "value": "● Always on"}]}


@app.get("/api/procurement")
def procurement():
    return {"opportunities": [
        {"title": "HVAC service · 14 brands", "amount": 310000,
         "note": "est. annual savings via HQ national contract", "tag": "Consolidate to HQ"},
        {"title": "Cleaning supplies · Gulf region", "amount": 128000,
         "note": "switch to benchmarked supplier (−18% unit cost)", "tag": "Supplier switch"},
        {"title": "Linens · 9 brands", "amount": 74000,
         "note": "volume-tier discount not currently claimed", "tag": "Renegotiate"}],
        "benchmark": [
            {"supplier": "Summit Maintenance Co.", "unit": 42.0, "used_by": "3 brands",
             "on_contract": "No", "vs_hq": "+50%"},
            {"supplier": "Peak Mechanical", "unit": 31.0, "used_by": "5 brands",
             "on_contract": "Regional", "vs_hq": "+11%"},
            {"supplier": "HQ national contract", "unit": 28.0, "used_by": "—",
             "on_contract": "Yes", "vs_hq": "baseline"}]}


@app.get("/api/audit")
def audit(limit: int = 60):
    return {"events": trail(limit=limit)}


# --- self-learning: model registry + fine-tune loop (Phase 2) ---------------
@app.get("/api/registry")
def registry_view():
    return {"champion": registry.champion(), "versions": registry.list_versions(),
            "eval": trainer.eval_metrics(), "labels": label_stats(),
            "bar": settings.autonomy_precision_bar}


@app.post("/api/training/run")
def training_run():
    """Run one self-learning cycle: dispositions → fine-tune (simulated) → eval gate → promote."""
    res = trainer.run_finetune()
    record(AuditEvent("system", "trainer", "training.run", res["candidate"],
                      after={"promoted": res["promoted"], "precision": res["precision"]},
                      model_version=res["candidate"]))
    return res


@app.post("/api/registry/rollback")
def registry_rollback():
    return registry.rollback(by="kyle-hq")


@app.post("/api/demo/reset")
def demo_reset():
    res = bootstrap.seed_all()
    record(AuditEvent("system", "demo", "reset", "portfolio", after=res))
    return res


# --- web UI ----------------------------------------------------------------
if _STATIC.exists():
    app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.get("/", include_in_schema=False)
def ui():
    idx = _STATIC / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    raise HTTPException(404, "UI not built")
