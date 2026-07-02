"""Demo-data reset — reseeds the whole store (invoices, flags, dispositions, notifications)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from libs.common.audit import AuditEvent, record
from services import bootstrap

router = APIRouter(tags=["demo"])


class DemoResetResponse(BaseModel):
    invoices: int
    flags: int
    vendors: int
    model_version_n: int
    auto_act_types: int
    notifications: int


@router.post("/api/demo/reset", response_model=DemoResetResponse)
def demo_reset():
    res = bootstrap.seed_all()
    record(AuditEvent("system", "demo", "reset", "portfolio", after=res))
    return res
