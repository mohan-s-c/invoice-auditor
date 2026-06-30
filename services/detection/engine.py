"""Detection engine (handoff §6 detection, PRD §5 taxonomy).

Deterministic rules + simple baselines — exact and explainable, kept OUTSIDE the model
(handoff §7). Each anomaly carries a type, severity, confidence, recoverable $, a plain-English
rationale, and a recommended action. The model (agent) adds the natural-language "why" on top;
it does not replace these rules. Every flag records the model version for audit + training.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from libs.ap_client import seed
from libs.canonical.models import Contract, Invoice, Vendor

SEV_ORDER = {"medium": 0, "high": 1, "critical": 2}
SEV_PILL = {"medium": "blu", "high": "amb", "critical": "red"}

# Per-type base confidence (mirrors the mockup) + default recommended action.
_TYPE = {
    "Duplicate":        (0.97, "Auto-reject (rev.)", "critical"),
    "Off-contract":     (0.91, "Flag & route", "critical"),
    "Price overage":    (0.86, "Flag & route", "high"),
    "Rate variance":    (0.88, "Flag & route", "high"),
    "Threshold gaming": (0.83, "Escalate", "high"),
    "Qty outlier":      (0.74, "Review", "medium"),
    "New vendor":       (0.68, "Review", "medium"),
    "Tax / fee error":  (0.92, "Auto-reject (rev.)", "medium"),
}
# Category quantity norms for the qty-outlier baseline.
_QTY_NORM = {"Linens": 60, "Cleaning supplies": 60, "Maintenance & repairs": 20,
             "Landscaping": 12, "Pool service": 16}


@dataclass
class Anomaly:
    type: str
    severity: str
    confidence: float
    rationale: str
    recoverable: float = 0.0
    action: str = "Review"


@dataclass
class Result:
    anomalies: list[Anomaly] = field(default_factory=list)
    line_flags: dict[int, str] = field(default_factory=dict)  # line index -> pill label

    @property
    def flagged(self) -> bool:
        return bool(self.anomalies)

    @property
    def primary(self) -> Anomaly | None:
        return max(self.anomalies, key=lambda a: (SEV_ORDER[a.severity], a.confidence),
                   default=None)


def _benchmark(category: str, item: str) -> float | None:
    # Specific item benchmark only — a crude category default would false-positive on
    # legitimately expensive one-off line items (e.g. a $3,300 panel upgrade).
    return seed.BENCHMARKS.get((category, item))


def detect_all(invoices: list[Invoice], vendors: list[Vendor],
               contracts: list[Contract]) -> dict[str, Result]:
    """Run detection across the whole batch (needed for duplicate/split context)."""
    by_id = {v.id: v for v in vendors}
    hq_categories = {c.category for c in contracts if c.scope == "hq"}
    results = {inv.id: Result() for inv in invoices}

    for inv in invoices:
        res = results[inv.id]
        vendor = by_id.get(inv.vendor_id)

        # --- price overage (per line vs benchmark) ---
        for i, line in enumerate(inv.lines):
            bm = _benchmark(inv.category, line.item)
            if bm and line.unit_price > bm * 1.15:
                pct = round((line.unit_price / bm - 1) * 100)
                sev = "critical" if pct >= 45 else "high" if pct >= 25 else "medium"
                res.line_flags[i] = f"+{pct}% vs benchmark"
                res.anomalies.append(Anomaly(
                    "Price overage", sev, _TYPE["Price overage"][0],
                    f"{line.item} unit price ${line.unit_price:,.2f} vs benchmark "
                    f"${bm:,.2f} (+{pct}%).",
                    recoverable=round((line.unit_price - bm) * line.qty, 2),
                    action=_TYPE["Price overage"][1]))

        # --- qty outlier ---
        norm = _QTY_NORM.get(inv.category)
        for i, line in enumerate(inv.lines):
            if norm and line.qty > norm * 2.5:
                res.line_flags.setdefault(i, "qty outlier")
                res.anomalies.append(Anomaly(
                    "Qty outlier", "medium", _TYPE["Qty outlier"][0],
                    f"{line.item} qty {line.qty:g} is well above the category norm (~{norm}).",
                    action=_TYPE["Qty outlier"][1]))

        # --- duplicate (line matches an earlier invoice, same vendor+brand) ---
        for i, line in enumerate(inv.lines):
            for other in invoices:
                if other.id >= inv.id or other.vendor_id != inv.vendor_id or other.brand != inv.brand:
                    continue
                if any(o.item == line.item and abs(o.amount - line.amount) < 0.01
                       for o in other.lines):
                    res.line_flags[i] = f"duplicate of {other.id}?"
                    res.anomalies.append(Anomaly(
                        "Duplicate", "critical", _TYPE["Duplicate"][0],
                        f"{line.item} (${line.amount:,.2f}) matches {other.id} "
                        f"(same vendor, same brand).",
                        recoverable=line.amount, action=_TYPE["Duplicate"][1]))
                    break

        # --- off-contract / maverick ---
        if vendor and vendor.contract == "off" and inv.category in hq_categories:
            res.anomalies.append(Anomaly(
                "Off-contract", "critical", _TYPE["Off-contract"][0],
                f"{vendor.name} is not on the {inv.category} contract; an HQ national rate exists.",
                recoverable=round(inv.amount * max(vendor.vs_benchmark, 0) * 0.5, 2),
                action=_TYPE["Off-contract"][1]))

        # --- rate variance (vendor avg well above benchmark, if not already an overage) ---
        if vendor and vendor.vs_benchmark >= 0.25 and not any(
                a.type in ("Price overage", "Off-contract") for a in res.anomalies):
            res.anomalies.append(Anomaly(
                "Rate variance", "high", _TYPE["Rate variance"][0],
                f"{vendor.name} averages +{round(vendor.vs_benchmark * 100)}% vs the HQ rate.",
                action=_TYPE["Rate variance"][1]))

        # --- new vendor ---
        if vendor and vendor.spend_ytd < 5000:
            res.anomalies.append(Anomaly(
                "New vendor", "medium", _TYPE["New vendor"][0],
                f"{vendor.name} is a new/low-history vendor (YTD ${vendor.spend_ytd:,.0f}).",
                action=_TYPE["New vendor"][1]))

        # --- threshold gaming (just under approval limit, or split same-day same-vendor) ---
        thr = seed.APPROVAL_THRESHOLD
        siblings = [o for o in invoices if o.vendor_id == inv.vendor_id
                    and o.brand == inv.brand and o.filed_ts == inv.filed_ts and o.id != inv.id]
        just_under = thr * 0.9 <= inv.amount < thr
        split = just_under and any(thr * 0.9 <= o.amount < thr for o in siblings)
        if just_under:
            res.anomalies.append(Anomaly(
                "Threshold gaming", "high", _TYPE["Threshold gaming"][0],
                (f"${inv.amount:,.2f} sits just under the ${thr:,.0f} approval limit"
                 + ("; paired with a same-day split invoice." if split else ".")),
                action=_TYPE["Threshold gaming"][1]))

    return results
