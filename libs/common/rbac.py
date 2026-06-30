"""RBAC region-scoping (handoff §10.5) — HQ sees all brands; a Regional President sees only
their region. Scoping is a first-class data-layer concern: every list/KPI/flag is filtered by
the current role's region. Role is an in-memory selection for the demo (a real build binds it
to the authenticated identity).
"""
from __future__ import annotations

ROLES = [
    {"id": "kyle-hq", "name": "Kyle Dwyer", "scope": "HQ · VC & Ops", "region": None, "initials": "KD"},
    {"id": "rp-mtnwest", "name": "Dana Reed", "scope": "RP · Mountain West",
     "region": "Mountain West", "initials": "DR"},
    {"id": "rp-gulf", "name": "Marco Ruiz", "scope": "RP · Gulf", "region": "Gulf", "initials": "MR"},
    {"id": "rp-southeast", "name": "Tina Park", "scope": "RP · Southeast",
     "region": "Southeast", "initials": "TP"},
]
_state = {"role": "kyle-hq"}


def current_role() -> dict:
    return next((r for r in ROLES if r["id"] == _state["role"]), ROLES[0])


def set_role(role_id: str) -> dict:
    if not any(r["id"] == role_id for r in ROLES):
        raise ValueError(f"unknown role {role_id}")
    _state["role"] = role_id
    return current_role()


def region_scope() -> str | None:
    """The region the current role may see; None = all (HQ)."""
    return current_role()["region"]


def visible(region: str) -> bool:
    scope = region_scope()
    return scope is None or region == scope


def list_roles() -> list[dict]:
    return ROLES
