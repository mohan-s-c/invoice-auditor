"""Immutable audit log (handoff §10.4) — actor, action, target, before/after, model_version."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Literal

import structlog

from libs.common import db

log = structlog.get_logger("audit")
Actor = Literal["human", "agent", "system"]


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


@dataclass
class AuditEvent:
    actor: Actor
    actor_id: str
    action: str
    target: str
    before: Any = None
    after: Any = None
    model_version: str | None = None
    ts: str = field(default_factory=_now)


def record(e: AuditEvent) -> None:
    log.info("audit", actor=e.actor, action=e.action, target=e.target)
    db.execute(
        "INSERT INTO audit (ts, actor, actor_id, action, target, before, after, model_version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (e.ts, e.actor, e.actor_id, e.action, e.target,
         db.dumps(e.before) if e.before is not None else None,
         db.dumps(e.after) if e.after is not None else None, e.model_version),
    )


def trail(target: str | None = None, limit: int = 300) -> list[dict[str, Any]]:
    rows = (db.query("SELECT * FROM audit WHERE target = ? ORDER BY id DESC LIMIT ?",
                     (target, limit)) if target
            else db.query("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)))
    out = []
    for r in rows:
        d = dict(r)
        d["before"], d["after"] = db.loads(d["before"]), db.loads(d["after"])
        out.append(d)
    return out
