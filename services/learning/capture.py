"""Self-learning capture (handoff §7, §6 learning).

Every human disposition (approve / reject lines / place hold / escalate / override) is written
to the ``dispositions`` table WITH the model version that produced the original call. That table
IS the training-label source for the periodic LoRA fine-tune (Phase 2). Capture is the
prerequisite and is built now; training/registry/promotion slot in behind it.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from libs.common import db
from libs.common.audit import AuditEvent, record


def record_disposition(flag_id: str, invoice_id: str, actor_id: str, action: str,
                       before: Any = None, after: Any = None,
                       model_version: str | None = None) -> dict:
    """Persist a disposition as a training label + an immutable audit row."""
    ts = dt.datetime.now(dt.timezone.utc).isoformat()
    db.execute(
        "INSERT INTO dispositions (flag_id, invoice_id, actor, action, before, after, "
        "model_version, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (flag_id, invoice_id, actor_id, action, db.dumps(before), db.dumps(after),
         model_version, ts),
    )
    record(AuditEvent("human", actor_id, f"disposition.{action}", invoice_id,
                      before=before, after=after, model_version=model_version))
    return {"flag_id": flag_id, "invoice_id": invoice_id, "action": action, "ts": ts}


def label_stats() -> dict[str, int]:
    """How many labels we've accumulated, by action — the training-set size."""
    rows = db.query("SELECT action, COUNT(*) AS c FROM dispositions GROUP BY action")
    return {r["action"]: r["c"] for r in rows}
