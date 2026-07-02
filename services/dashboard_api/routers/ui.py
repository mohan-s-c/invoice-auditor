"""Serves the single-page dashboard UI (services/dashboard_api/static/index.html)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

router = APIRouter(tags=["ui"], include_in_schema=False)


@router.get("/")
def index():
    idx = STATIC_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    raise HTTPException(404, "UI not built")


def mount_static(app) -> None:
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
