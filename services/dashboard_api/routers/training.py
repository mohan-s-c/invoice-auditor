"""Autonomy ladder view + self-learning model registry (capture -> fine-tune -> eval -> promote)."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from libs.common.audit import AuditEvent, record
from libs.common.config import settings
from services.agent import autonomy
from services.learning.capture import label_stats
from services.training import registry, trainer

router = APIRouter(tags=["training"])


@router.get("/api/autonomy")
def autonomy_view():
    return {"autonomy": autonomy.table(),
            "routing": [
                {"severity": "Critical", "rule": "Real-time → Kyle + Regional President (push + email)"},
                {"severity": "High", "rule": "Real-time → Regional President · digest → Kyle"},
                {"severity": "Medium", "rule": "Daily digest"},
                {"severity": "Scope", "rule": "RP sees only their brands"}],
            "guardrails": [
                {"policy": "Money decisions & high-value rejections", "value": "🔒 Human approval"},
                {"policy": "Max auto-reject value", "value": "$1,000"},
                {"policy": "Financial / PII data", "value": "🔒 Self-hosted models"},
                {"policy": "Audit logging", "value": "● Always on"}]}


@router.get("/api/registry")
def registry_view():
    return {"champion": registry.champion(), "versions": registry.list_versions(),
            "eval": trainer.eval_metrics(), "labels": label_stats(),
            "bar": settings.autonomy_precision_bar}


class TrainingRunResponse(BaseModel):
    candidate: str
    precision: float
    champion_precision: float
    labels: int
    beats_champion: bool
    clears_bar: bool
    promoted: bool
    bar: float
    metrics: dict


@router.post("/api/training/run", response_model=TrainingRunResponse)
def training_run():
    """Run one self-learning cycle: dispositions → fine-tune (simulated) → eval gate → promote."""
    res = trainer.run_finetune()
    record(AuditEvent("system", "trainer", "training.run", res["candidate"],
                      after={"promoted": res["promoted"], "precision": res["precision"]},
                      model_version=res["candidate"]))
    return res


class RollbackResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rolled_back: bool
    champion: str | None = None
    from_version: str | None = Field(default=None, alias="from")
    reason: str | None = None


@router.post("/api/registry/rollback", response_model=RollbackResponse)
def registry_rollback():
    return registry.rollback(by="kyle-hq")
