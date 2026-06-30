"""Notification policy (next-phase §): when does an anomaly warrant an email, and to whom?

Deterministic and transparent — thresholds are versioned with the code for this MVP; a later
phase moves them into editable policy_rule records (mirrors the autonomy precision bar).
THRESHOLD VALUES ARE ASSUMED for now and are easy to tune here.

Rule: a flag notifies if its severity is high/critical, OR its dollar amount clears the
per-category threshold. Routing: the flag's region -> that Regional President; a critical
flag also copies the Operations head. Regions without an RP fall back to the Ops desk.
"""
from __future__ import annotations

# Per-spend-category dollar thresholds (assumed). Above this, a flag is emailed even if
# the severity alone wouldn't trigger it.
CATEGORY_DOLLAR_THRESHOLD = {
    "Maintenance & repairs": 2000.0,
    "Pool service": 1500.0,
    "Cleaning supplies": 1000.0,
    "Landscaping": 1000.0,
    "Linens": 750.0,
}
DEFAULT_DOLLAR_THRESHOLD = 1000.0
ALWAYS_NOTIFY_SEVERITY = {"critical", "high"}

# Region -> Regional President (assumed contacts; mirrors rbac roles where one exists).
REGION_CONTACTS = {
    "Mountain West": {"name": "Dana Reed", "email": "dana.reed@awayday.example",
                      "title": "Regional President — Mountain West"},
    "Gulf": {"name": "Marco Ruiz", "email": "marco.ruiz@awayday.example",
             "title": "Regional President — Gulf"},
    "Southeast": {"name": "Tina Park", "email": "tina.park@awayday.example",
                  "title": "Regional President — Southeast"},
    "Pacific NW": {"name": "Operations Desk — Pacific NW", "email": "ops.pnw@awayday.example",
                   "title": "Operations Desk (no RP assigned yet)"},
}
OPS_HEAD = {"name": "Operations Head", "email": "ops.head@awayday.example",
            "title": "Head of Operations"}


def threshold_for(category: str) -> float:
    return CATEGORY_DOLLAR_THRESHOLD.get(category, DEFAULT_DOLLAR_THRESHOLD)


def should_notify(flag: dict) -> tuple[bool, str]:
    """Return (notify?, human-readable reason) for a flag dict."""
    sev = (flag.get("severity") or "").lower()
    amount = float(flag.get("amount") or 0)
    cat = flag.get("category") or ""
    thr = threshold_for(cat)
    if sev in ALWAYS_NOTIFY_SEVERITY:
        return True, f"{sev} severity"
    if amount >= thr:
        return True, f"${amount:,.0f} ≥ ${thr:,.0f} threshold for {cat}"
    return False, f"below {cat} threshold (${thr:,.0f}) and not high/critical"


def recipients(flag: dict) -> list[dict]:
    """Who to email for this flag. 'to' = Regional President; 'cc' = Ops head on critical."""
    region = flag.get("region") or ""
    sev = (flag.get("severity") or "").lower()
    rp = REGION_CONTACTS.get(region, OPS_HEAD)
    out = [{**rp, "kind": "to"}]
    if sev == "critical" and rp["email"] != OPS_HEAD["email"]:
        out.append({**OPS_HEAD, "kind": "cc"})
    return out
