"""Auditor agent (handoff §6 agent) — triage, explain the "why", recommend an action, draft a
notification. Runs on the local Qwen (offline by default). It NEVER calls a money/hold tool
directly; it produces a recommendation routed to a human gate.
"""
from __future__ import annotations

from libs.canonical.models import Invoice
from libs.modelserve.provider import get_provider, model_version

from . import autonomy
from ..detection.engine import Result


def recommend(inv: Invoice, result: Result) -> dict:
    """Produce the agent recommendation for a flagged invoice."""
    primary = result.primary
    if primary is None:
        return {}
    recoverable = round(sum(a.recoverable for a in result.anomalies), 2)
    types = sorted({a.type for a in result.anomalies})
    level = autonomy.level_for(primary.type)

    prompt = (f"Invoice {inv.id} ({inv.vendor}, {inv.brand}) flagged for "
              f"{', '.join(types)}. Recommend a disposition for a controls analyst.")
    why = get_provider().complete(
        "You are an invoice controls analyst. Be concise and money-safe.", prompt)

    rec = ("Recommend a partial hold: keep clean lines; reject the flagged lines"
           + (f" (est. recoverable ${recoverable:,.0f})" if recoverable else "")
           + (". Move the vendor to the HQ contract." if "Off-contract" in types else "."))

    return {
        "action": primary.action,
        "confidence": round(primary.confidence, 2),
        "autonomy": level,
        "auto_act_allowed": autonomy.auto_act_allowed(primary.type, inv.amount),
        "recoverable": recoverable,
        "recommendation": rec,
        "narrative": why,
        "rationale": [a.rationale for a in result.anomalies],
        "anomaly_types": types,
        "gate": True,  # money decision — human approval required
        "model_version": model_version(),
    }
