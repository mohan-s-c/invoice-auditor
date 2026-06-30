"""Ingestion + detection bootstrap (handoff Phase 0/1).

Pull invoices from the AP client → run detection across the batch → persist canonical invoices,
line flags, and scored flags (with model version) → auto-clear clean invoices. Writes the audit
trail. This is the offline stand-in for the streaming ingestion + detection services.
"""
from __future__ import annotations

import datetime as dt

from libs.ap_client.client import get_client
from libs.common import db
from libs.common.audit import AuditEvent, record
from services.agent import autonomy
from services.detection.engine import detect_all
from services.training import registry


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def seed_all() -> dict[str, int]:
    """Reset, ingest, detect, persist. Returns counts."""
    db.reset()
    client = get_client()
    vendors, contracts, invoices = client.vendors(), client.contracts(), client.invoices()
    # Register the initial champion model in the registry; flags are stamped with its version.
    base_prec = round(sum(a["precision"] for a in autonomy.table()) / len(autonomy.table()), 3)
    registry.register("qwen-offline-v1", base="qwen-instruct", parent=None, status="champion",
                      precision_overall=base_prec, metrics={"overall": base_prec, "seed": True},
                      labels_used=0)
    mv = registry.champion_version()

    db.executemany(
        "INSERT INTO vendors (id,name,category,contract,region,spend_ytd,vs_benchmark) "
        "VALUES (?,?,?,?,?,?,?)",
        [(v.id, v.name, v.category, v.contract, v.region, v.spend_ytd, v.vs_benchmark)
         for v in vendors])
    db.executemany(
        "INSERT INTO contracts (category,region,scope,hq_rate) VALUES (?,?,?,?)",
        [(c.category, c.region, c.scope, c.hq_rate) for c in contracts])

    results = detect_all(invoices, vendors, contracts)
    n_flags = 0
    for inv in invoices:
        res = results[inv.id]
        flagged = res.flagged
        status = "pending" if flagged else "cleared"
        db.execute(
            "INSERT INTO invoices (id,brand,region,vendor_id,vendor,category,amount,tax,status,"
            "approver,filed_ts,model_version,paid,paid_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (inv.id, inv.brand, inv.region, inv.vendor_id, inv.vendor, inv.category, inv.amount,
             inv.tax, status, inv.approver, inv.filed_ts, mv, 1 if inv.paid else 0, inv.paid_ts))
        for i, line in enumerate(inv.lines):
            db.execute(
                "INSERT INTO invoice_lines (invoice_id,item,category,qty,unit_price,amount,flag) "
                "VALUES (?,?,?,?,?,?,?)",
                (inv.id, line.item, line.category or inv.category, line.qty, line.unit_price,
                 line.amount, res.line_flags.get(i)))

        if not flagged:
            continue
        p = res.primary
        n_flags += 1
        flag_id = f"FLAG-{inv.id}"
        recoverable = round(sum(a.recoverable for a in res.anomalies), 2)
        rationale = [a.rationale for a in res.anomalies]
        db.execute(
            "INSERT INTO flags (id,invoice_id,brand,region,vendor,category,amount,anomaly_type,"
            "severity,confidence,recommended_action,recoverable,rationale,model_version,status,"
            "created_ts,paid) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (flag_id, inv.id, inv.brand, inv.region, inv.vendor, inv.category, inv.amount,
             p.type, p.severity, round(max(a.confidence for a in res.anomalies), 2),
             p.action, recoverable, db.dumps(rationale), mv, "open", _now(),
             1 if inv.paid else 0))
        record(AuditEvent("agent", "auditor", "flag.scored", inv.id,
                          after={"anomalies": len(res.anomalies), "type": p.type,
                                 "severity": p.severity}, model_version=mv))
        record(AuditEvent("agent", "auditor", "flag.routed", inv.id,
                          after={"to": f"Kyle + RP {inv.region}"}, model_version=mv))

    # Route notifications for flags that clear the policy (offline → queued to the outbox).
    from services.notify.dispatch import dispatch_notifications
    notify = dispatch_notifications()

    return {"invoices": len(invoices), "flags": n_flags, "vendors": len(vendors),
            "model_version_n": 1, "auto_act_types": sum(
                1 for a in autonomy.table() if a["level"].startswith("L3")),
            "notifications": notify["queued"] + notify["sent"]}
