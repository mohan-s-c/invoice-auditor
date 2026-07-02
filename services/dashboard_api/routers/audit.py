"""Immutable audit trail read endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from libs.common.audit import trail

router = APIRouter(tags=["audit"])


@router.get("/api/audit")
def audit(limit: int = 60):
    return {"events": trail(limit=limit)}
