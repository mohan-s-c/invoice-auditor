"""RBAC-scoping + row-shaping helpers shared across routers.

Kept separate from any single router because both invoices.py and notify.py need the same
region-scoping and flag-shaping logic — duplicating it per-router would reintroduce the drift
this split is meant to prevent.
"""
from __future__ import annotations

from libs.common import rbac


def scope() -> str | None:
    """The region the current role may see; None = all (HQ)."""
    return rbac.region_scope()


def scoped(rows: list) -> list[dict]:
    s = scope()
    return [dict(r) for r in rows if s is None or r["region"] == s]


def flag_row(r: dict) -> dict:
    return {"id": r["id"], "invoice_id": r["invoice_id"], "vendor": r["vendor"],
            "brand": r["brand"], "region": r["region"], "category": r["category"],
            "amount": r["amount"], "anomaly_type": r["anomaly_type"], "severity": r["severity"],
            "confidence": r["confidence"], "recommended_action": r["recommended_action"],
            "recoverable": r["recoverable"], "status": r["status"],
            "paid": bool(r["paid"]) if "paid" in r.keys() else False}
