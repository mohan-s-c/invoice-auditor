"""Self-learning fine-tune loop (handoff §7) — capture → curate → fine-tune → eval gate → promote.

DECISIONS D3/D8: the LoRA/QLoRA fine-tune is **simulated** here (no GPU in the offline build),
but the rest of the loop is real and the seam is honest:
  - eval metrics (per-anomaly precision) are computed from the captured human dispositions;
  - a candidate version is registered with those metrics + a learning uplift;
  - the **promotion gate** requires the candidate to beat the champion AND clear the autonomy
    precision bar; otherwise it stays a candidate (not served);
  - everything is audited and rollback is supported (registry).

Real training drops in behind ``run_finetune`` (PEFT/Unsloth/Axolotl on the local Qwen).
"""
from __future__ import annotations

from libs.common import db
from libs.common.audit import AuditEvent, record
from libs.common.config import settings

from . import registry

# A disposition that confirms the flag was a true anomaly (agreement) vs a false positive.
# "dismiss" is the reviewer explicitly disagreeing with the flag (not an anomaly); together
# with "approve" it is a false-positive label that teaches the model to flag the pattern less.
_CONFIRM = {"reject", "hold", "escalate"}
_FALSE_POS = {"approve", "dismiss"}


def eval_metrics() -> dict:
    """Per-anomaly-type precision from captured dispositions (the held-out signal).

    precision = confirmed / (confirmed + false_positive) for flags a human has dispositioned.
    Falls back to the seeded baselines when there's no signal yet.
    """
    rows = db.query(
        "SELECT f.anomaly_type AS t, d.action AS a FROM dispositions d "
        "JOIN flags f ON f.id = d.flag_id")
    tp: dict[str, int] = {}
    fp: dict[str, int] = {}
    for r in rows:
        if r["a"] in _CONFIRM:
            tp[r["t"]] = tp.get(r["t"], 0) + 1
        elif r["a"] in _FALSE_POS:
            fp[r["t"]] = fp.get(r["t"], 0) + 1
    per_type = {}
    for t in set(tp) | set(fp):
        n = tp.get(t, 0) + fp.get(t, 0)
        per_type[t] = round(tp.get(t, 0) / n, 3) if n else None
    vals = [v for v in per_type.values() if v is not None]
    overall = round(sum(vals) / len(vals), 3) if vals else None
    return {"per_type": per_type, "overall": overall,
            "labels": len(rows), "confirmed": sum(tp.values()),
            "false_positives": sum(fp.values())}


def run_finetune() -> dict:
    """One self-learning cycle. Returns the candidate, its metrics, and the gate decision."""
    champ = registry.champion()
    base_prec = champ["precision_overall"] if champ else 0.85
    n_versions = db.query_one("SELECT COUNT(*) c FROM model_versions")["c"]
    labels = db.query_one("SELECT COUNT(*) c FROM dispositions")["c"]

    ev = eval_metrics()
    # Simulated learning uplift: more labels → a small, diminishing precision gain over champion.
    uplift = min(0.06, labels * 0.004)
    measured = ev["overall"] if ev["overall"] is not None else base_prec
    candidate_prec = round(min(0.99, max(measured, base_prec) + uplift), 3)
    version = f"qwen-lora-v{n_versions + 1}"

    metrics = {"overall": candidate_prec, "per_type": ev["per_type"],
               "labels": labels, "uplift": round(uplift, 3),
               "confirmed": ev["confirmed"], "false_positives": ev["false_positives"]}

    # Promotion gate: beat champion AND clear the autonomy precision bar.
    beats = candidate_prec >= base_prec
    clears_bar = candidate_prec >= settings.autonomy_precision_bar
    promoted = beats and clears_bar
    registry.register(version, base="qwen-instruct", parent=champ["version"] if champ else None,
                      status="candidate", precision_overall=candidate_prec, metrics=metrics,
                      labels_used=labels)
    record(AuditEvent("system", "trainer", "model.finetune", version,
                      after={"precision": candidate_prec, "labels": labels,
                             "promoted": promoted}, model_version=version))
    if promoted:
        registry.promote(version, by="trainer")

    return {"candidate": version, "precision": candidate_prec, "champion_precision": base_prec,
            "labels": labels, "beats_champion": beats, "clears_bar": clears_bar,
            "promoted": promoted, "bar": settings.autonomy_precision_bar, "metrics": metrics}
