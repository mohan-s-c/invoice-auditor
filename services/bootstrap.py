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
from libs.modelserve.provider import model_version
from services.agent import autonomy
from services.detection.engine import detect_all


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def seed_all() -> dict[str, int]:
    """Reset, ingest, detect, persist. Returns counts."""
    db.reset()
    client = get_client()
    vendors, contracts, invoices = client.vendors(), client.contracts(), client.invoices()
    mv = model_version()

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
            "approver,filed_ts,model_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (inv.id, inv.brand, inv.region, inv.vendor_id, inv.vendor, inv.category, inv.amount,
             inv.tax, status, inv.approver, inv.filed_ts, mv))
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
            "created_ts) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (flag_id, inv.id, inv.brand, inv.region, inv.vendor, inv.category, inv.amount,
             p.type, p.severity, round(max(a.confidence for a in res.anomalies), 2),
             p.action, recoverable, db.dumps(rationale), mv, "open", _now()))
        record(AuditEvent("agent", "auditor", "flag.scored", inv.id,
                          after={"anomalies": len(res.anomalies), "type": p.type,
                                 "severity": p.severity}, model_version=mv))
        record(AuditEvent("agent", "auditor", "flag.routed", inv.id,
                          after={"to": f"Kyle + RP {inv.region}"}, model_version=mv))

    return {"invoices": len(invoices), "flags": n_flags, "vendors": len(vendors),
            "model_version_n": 1, "auto_act_types": sum(
                1 for a in autonomy.table() if a["level"].startswith("L3"))}
