"""Seed dataset for the offline build — brands/regions, vendors, contracts, category
benchmarks, and a mix of clean + anomalous invoices the detection engine flags for real.
Mirrors the figures in the approved mockup (Summit Maintenance overage, CleanCo off-contract,
GreenScape duplicate, PoolPro threshold-gaming, etc.).
"""
from __future__ import annotations

from libs.canonical.models import Contract, Invoice, InvoiceLine, Vendor

APPROVAL_THRESHOLD = 2000.0  # invoices just under this are threshold-gaming candidates

# Region -> brands
BRANDS = {
    "Mountain West": ["Stay Montana", "Cabin Collective", "Summit Stays"],
    "Gulf": ["Gulf Coast Getaways", "Sunshine Stays", "Bayou Rentals"],
    "Southeast": ["Pristine Properties", "Coastal Keys", "Palmetto Stays"],
    "Pacific NW": ["Cascade Cabins", "Rainier Rentals"],
}

# HQ benchmark unit price per (category, item). Off-benchmark lines flag as price overage.
BENCHMARKS = {
    ("Maintenance & repairs", "HVAC filter replacement"): 28.0,
    ("Maintenance & repairs", "Labor (hrs)"): 95.0,
    ("Maintenance & repairs", "Emergency call-out fee"): 185.0,
    ("Cleaning supplies", "All-purpose cleaner (case)"): 36.0,
    ("Linens", "Bath towel (each)"): 4.20,
    ("Landscaping", "Mowing visit"): 110.0,
    ("Pool service", "Weekly service"): 140.0,
}
CATEGORY_DEFAULT_BENCHMARK = {
    "Maintenance & repairs": 95.0, "Cleaning supplies": 36.0, "Linens": 4.2,
    "Landscaping": 110.0, "Pool service": 140.0,
}

VENDORS = [
    Vendor(id="v-summit", name="Summit Maintenance Co.", category="Maintenance & repairs",
           contract="off", region="Mountain West", spend_ytd=214000, vs_benchmark=0.50),
    Vendor(id="v-peak", name="Peak Mechanical", category="Maintenance & repairs",
           contract="regional", region="Mountain West", spend_ytd=430000, vs_benchmark=0.11),
    Vendor(id="v-cleanco", name="CleanCo Supplies", category="Cleaning supplies",
           contract="off", region="Gulf", spend_ytd=305000, vs_benchmark=0.18),
    Vendor(id="v-linen", name="National Linen Group", category="Linens",
           contract="hq", region=None, spend_ytd=612000, vs_benchmark=0.0),
    Vendor(id="v-green", name="GreenScape LLC", category="Landscaping",
           contract="regional", region="Southeast", spend_ytd=148000, vs_benchmark=-0.03),
    Vendor(id="v-pool", name="PoolPro", category="Pool service",
           contract="off", region="Gulf", spend_ytd=96000, vs_benchmark=0.22),
    Vendor(id="v-linenplus", name="LinenPlus", category="Linens",
           contract="regional", region="Mountain West", spend_ytd=72000, vs_benchmark=0.05),
    Vendor(id="v-acme", name="Acme Hardware", category="Maintenance & repairs",
           contract="off", region="Mountain West", spend_ytd=3000, vs_benchmark=0.0),
    Vendor(id="v-bright", name="BrightElectric", category="Maintenance & repairs",
           contract="regional", region="Southeast", spend_ytd=120000, vs_benchmark=0.30),
]

CONTRACTS = [
    Contract(category="Maintenance & repairs", scope="hq", hq_rate=28.0),
    Contract(category="Cleaning supplies", scope="hq", hq_rate=36.0),
    Contract(category="Linens", scope="hq", hq_rate=4.20),
]


def _inv(id, brand, region, v, category, lines, status="pending", tax=0.0, filed="2026-06-29",
         approver="A. Operator", paid=False, paid_ts=None) -> Invoice:
    amount = round(sum(line_la(line) for line in lines) + tax, 2)
    return Invoice(id=id, brand=brand, region=region, vendor_id=v.id, vendor=v.name,
                   category=category, amount=amount, tax=tax, status=status,
                   approver=approver, filed_ts=filed, lines=lines,
                   paid=paid, paid_ts=(paid_ts or (filed if paid else None)))


def line_la(line: InvoiceLine) -> float:
    return line.amount


def L(item, qty, unit, category=None) -> InvoiceLine:
    return InvoiceLine(item=item, category=category, qty=qty, unit_price=unit,
                       amount=round(qty * unit, 2))


def _vendor(vid: str) -> Vendor:
    return next(v for v in VENDORS if v.id == vid)


def build_invoices() -> list[Invoice]:
    inv: list[Invoice] = []

    # --- the headline anomaly invoices (match the mockup) ---
    # Already paid: a duplicate that was disbursed before audit → a recovery/clawback case.
    inv.append(_inv("INV-44871", "Stay Montana", "Mountain West", _vendor("v-summit"),
                    "Maintenance & repairs", [
        L("HVAC filter replacement", 12, 42.0),     # benchmark 28 → +50% overage
        L("Emergency call-out fee", 3, 185.0),       # duplicate of INV-44102
        L("Labor (hrs)", 14, 95.0),                  # in range
        L("Misc. parts", 1, 2591.0),                 # vague high line
    ], paid=True, paid_ts="2026-06-27"))
    inv.append(_inv("INV-44102", "Stay Montana", "Mountain West", _vendor("v-summit"),
                    "Maintenance & repairs", [
        L("Emergency call-out fee", 3, 185.0),       # the original of the duplicate
        L("Labor (hrs)", 6, 95.0),
    ], filed="2026-06-25", paid=True, paid_ts="2026-06-25"))

    # Already paid: off-contract overage that slipped through → recovery case.
    inv.append(_inv("INV-45012", "Gulf Coast Getaways", "Gulf", _vendor("v-cleanco"),
                    "Cleaning supplies", [
        L("All-purpose cleaner (case)", 40, 53.5),   # off-contract vendor + +49% unit
    ], paid=True, paid_ts="2026-06-26"))

    inv.append(_inv("INV-45120", "Pristine Properties", "Southeast", _vendor("v-green"),
                    "Landscaping", [L("Mowing visit", 8, 170.0)]))
    inv.append(_inv("INV-45121", "Pristine Properties", "Southeast", _vendor("v-green"),
                    "Landscaping", [L("Mowing visit", 8, 170.0)]))  # exact duplicate

    inv.append(_inv("INV-45230", "Stay Montana", "Mountain West", _vendor("v-linenplus"),
                    "Linens", [L("Bath towel (each)", 200, 4.40)]))  # qty outlier (norm ~40)

    # PoolPro split invoices just under the $2,000 approval threshold (threshold gaming)
    inv.append(_inv("INV-45301", "Sunshine Stays", "Gulf", _vendor("v-pool"),
                    "Pool service", [L("Weekly service", 13, 147.0)]))   # 1,911
    inv.append(_inv("INV-45302", "Sunshine Stays", "Gulf", _vendor("v-pool"),
                    "Pool service", [L("Weekly service", 13, 146.0)]))   # 1,898

    inv.append(_inv("INV-45410", "Cabin Collective", "Mountain West", _vendor("v-acme"),
                    "Maintenance & repairs", [L("Door hardware", 6, 102.0)]))  # new vendor
    inv.append(_inv("INV-45500", "Coastal Keys", "Southeast", _vendor("v-bright"),
                    "Maintenance & repairs", [L("Panel upgrade", 1, 3300.0)]))  # rate variance

    # --- clean invoices across brands (auto-clear; populate the dashboard) ---
    clean = [
        ("Stay Montana", "Mountain West", "v-peak", "Maintenance & repairs",
         [L("Labor (hrs)", 6, 95.0)]),
        ("Cabin Collective", "Mountain West", "v-peak", "Maintenance & repairs",
         [L("Labor (hrs)", 4, 95.0)]),
        ("Gulf Coast Getaways", "Gulf", "v-linen", "Linens", [L("Bath towel (each)", 40, 4.20)]),
        ("Sunshine Stays", "Gulf", "v-linen", "Linens", [L("Bath towel (each)", 30, 4.20)]),
        ("Pristine Properties", "Southeast", "v-linen", "Linens", [L("Bath towel (each)", 50, 4.20)]),
        ("Coastal Keys", "Southeast", "v-green", "Landscaping", [L("Mowing visit", 4, 110.0)]),
        ("Cascade Cabins", "Pacific NW", "v-peak", "Maintenance & repairs", [L("Labor (hrs)", 5, 95.0)]),
        ("Rainier Rentals", "Pacific NW", "v-linen", "Linens", [L("Bath towel (each)", 25, 4.20)]),
        ("Palmetto Stays", "Southeast", "v-green", "Landscaping", [L("Mowing visit", 3, 110.0)]),
        ("Bayou Rentals", "Gulf", "v-linen", "Linens", [L("Bath towel (each)", 20, 4.20)]),
        ("Summit Stays", "Mountain West", "v-peak", "Maintenance & repairs", [L("Labor (hrs)", 7, 95.0)]),
    ]
    for i, (brand, region, vid, cat, lines) in enumerate(clean):
        # Roughly half of routine clean invoices have already been paid in the normal cycle.
        inv.append(_inv(f"INV-460{i:02d}", brand, region, _vendor(vid), cat, lines,
                        status="pending", paid=(i % 2 == 0), paid_ts="2026-06-24"))
    return inv
