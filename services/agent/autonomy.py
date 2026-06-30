"""Autonomy ladder per anomaly type (handoff §10.7, settings screen).

L0 Assist → L1 Recommend → L2 Auto-flag → L3 Auto-act. Auto-act unlocks only at sustained
precision ≥ bar (low-value, reversible) and is reversible. This is the human control surface;
the agent reads the level to decide recommend vs auto.
"""
from __future__ import annotations

from libs.common.config import settings

AUTONOMY = [
    {"type": "Duplicate", "level": "L3 Auto-act", "precision": 0.98, "auto_max": 1000, "status": "on"},
    {"type": "Tax / fee error", "level": "L3 Auto-act", "precision": 0.99, "auto_max": 500, "status": "on"},
    {"type": "Off-contract", "level": "L2 Auto-flag", "precision": 0.91, "auto_max": None, "status": "promoting"},
    {"type": "Price overage", "level": "L2 Auto-flag", "precision": 0.86, "auto_max": None, "status": "on"},
    {"type": "Rate variance", "level": "L2 Auto-flag", "precision": 0.84, "auto_max": None, "status": "on"},
    {"type": "Threshold gaming", "level": "L1 Recommend", "precision": 0.79, "auto_max": None, "status": "learning"},
    {"type": "Qty outlier", "level": "L1 Recommend", "precision": 0.74, "auto_max": None, "status": "learning"},
    {"type": "New vendor", "level": "L1 Recommend", "precision": 0.70, "auto_max": None, "status": "learning"},
]
_BY_TYPE = {a["type"]: a for a in AUTONOMY}


def level_for(anomaly_type: str) -> str:
    return _BY_TYPE.get(anomaly_type, {}).get("level", "L1 Recommend")


def auto_act_allowed(anomaly_type: str, amount: float) -> bool:
    """Auto-act only for L3 types that clear the precision bar and the value cap."""
    a = _BY_TYPE.get(anomaly_type)
    if not a or not a["level"].startswith("L3") or a["status"] != "on":
        return False
    if a["precision"] < settings.autonomy_precision_bar:
        return False
    cap = a["auto_max"] or settings.max_auto_reject_value
    return amount <= cap


def table() -> list[dict]:
    return AUTONOMY
