"""Vendor/contract spend view + the (illustrative, Phase-3) procurement-savings surface."""
from __future__ import annotations

from fastapi import APIRouter

from libs.common import db
from services.dashboard_api.scoping import scope

router = APIRouter(tags=["vendors"])


@router.get("/api/vendors")
def vendors():
    rows = db.query("SELECT * FROM vendors")
    s = scope()
    out = [dict(r) for r in rows if s is None or r["region"] in (None, s)]
    off = sum(1 for v in out if v["contract"] == "off")
    return {"vendors": out, "off_contract_pct": round(off / len(out) * 100) if out else 0}


@router.get("/api/procurement")
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
