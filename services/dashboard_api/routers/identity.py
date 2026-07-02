"""Health check + current-role identity (role is an in-memory demo selection, not real auth)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from libs.common import rbac
from services.training import registry

router = APIRouter(tags=["identity"])


class RoleInfo(BaseModel):
    id: str
    name: str
    scope: str
    region: str | None
    initials: str


class MeResponse(BaseModel):
    role: RoleInfo
    roles: list[RoleInfo]
    model_version: str


class RoleReq(BaseModel):
    role: str


class RoleResponse(BaseModel):
    role: RoleInfo


@router.get("/api/health")
def health():
    return {"status": "ok"}


@router.get("/api/me", response_model=MeResponse)
def me():
    return {"role": rbac.current_role(), "roles": rbac.list_roles(),
            "model_version": registry.champion_version()}


@router.post("/api/role", response_model=RoleResponse)
def set_role(req: RoleReq):
    try:
        return {"role": rbac.set_role(req.role)}
    except ValueError as e:
        raise HTTPException(400, str(e))
