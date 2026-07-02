"""Control surface API (handoff §6 dashboard_api) — feeds the 8 designed screens.

RBAC region-scoping is enforced server-side: HQ sees all brands; a Regional President sees only
their region. Every list/KPI/flag/notification is filtered by the current role's region
(services/dashboard_api/scoping.py). Routes are grouped by domain under routers/ — this module
only builds the app, wires the lifespan, and mounts each router.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from libs.common import db
from services import bootstrap
from services.dashboard_api.routers import audit, demo, identity, invoices, notify, training, ui, vendors


@asynccontextmanager
async def lifespan(_app: FastAPI):
    db.init_db()
    if db.query_one("SELECT COUNT(*) AS c FROM invoices")["c"] == 0:
        bootstrap.seed_all()
    yield


app = FastAPI(title="Invoice Auditor", version="0.1.0", lifespan=lifespan)

for router_module in (identity, invoices, vendors, notify, training, audit, demo):
    app.include_router(router_module.router)

ui.mount_static(app)
app.include_router(ui.router)
