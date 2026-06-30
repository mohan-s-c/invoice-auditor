"""Model registry (handoff §7.6) — versioned local-Qwen models with a champion + rollback.

Every flag records the model version that produced it; the registry tracks which version is
**champion** (serving), retains prior versions for **instant rollback**, and stores eval metrics
per version. Promotion is gated by the trainer's eval (Section 7.5).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from libs.common import db
from libs.common.audit import AuditEvent, record


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def register(version: str, *, base: str, parent: str | None, status: str,
             precision_overall: float, metrics: dict, labels_used: int) -> None:
    db.execute(
        "INSERT OR REPLACE INTO model_versions (version, base, parent, status, "
        "precision_overall, metrics, labels_used, created_ts) VALUES (?,?,?,?,?,?,?,?)",
        (version, base, parent, status, precision_overall, db.dumps(metrics), labels_used, _now()),
    )


def champion() -> dict | None:
    r = db.query_one("SELECT * FROM model_versions WHERE status='champion' "
                     "ORDER BY created_ts DESC LIMIT 1")
    return dict(r) if r else None


def champion_version() -> str:
    c = champion()
    return c["version"] if c else "qwen-offline-v1"


def list_versions() -> list[dict]:
    return [dict(r) for r in db.query(
        "SELECT version, base, parent, status, precision_overall, labels_used, created_ts "
        "FROM model_versions ORDER BY created_ts DESC")]


def promote(version: str, by: str = "system") -> dict:
    """Make ``version`` the champion; the prior champion is retired (kept for rollback)."""
    prev = champion()
    if prev and prev["version"] != version:
        db.execute("UPDATE model_versions SET status='retired' WHERE version=?", (prev["version"],))
    db.execute("UPDATE model_versions SET status='champion' WHERE version=?", (version,))
    record(AuditEvent("system", by, "model.promote", version,
                      before={"champion": prev["version"] if prev else None},
                      after={"champion": version}, model_version=version))
    return {"champion": version, "previous": prev["version"] if prev else None}


def rollback(by: str = "system") -> dict:
    """Revert to the most recently retired version (instant rollback, handoff §7.7)."""
    cur = champion()
    prev = db.query_one("SELECT * FROM model_versions WHERE status='retired' "
                        "ORDER BY created_ts DESC LIMIT 1")
    if not prev:
        return {"rolled_back": False, "reason": "no prior version"}
    if cur:
        db.execute("UPDATE model_versions SET status='retired' WHERE version=?", (cur["version"],))
    db.execute("UPDATE model_versions SET status='champion' WHERE version=?", (prev["version"],))
    record(AuditEvent("system", by, "model.rollback", prev["version"],
                      before={"champion": cur["version"] if cur else None},
                      after={"champion": prev["version"]}, model_version=prev["version"]))
    return {"rolled_back": True, "champion": prev["version"],
            "from": cur["version"] if cur else None}


def metrics_of(version: str) -> dict[str, Any]:
    r = db.query_one("SELECT metrics FROM model_versions WHERE version=?", (version,))
    return db.loads(r["metrics"]) if r else {}
