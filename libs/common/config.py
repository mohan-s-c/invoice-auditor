"""Central settings (handoff §4). Offline-first defaults; see DECISIONS.md.

Mode/provider fields use ``Literal`` (not plain ``str``) so a typo'd env var (e.g.
``AP_MODE=rmap``) fails fast at process startup with a clear pydantic validation error,
instead of silently falling through to the default mode and misbehaving in production.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Local LLM (self-hosted Qwen). "offline" = deterministic, no GPU.
    llm_provider: Literal["offline", "oss"] = "offline"
    oss_model_base_url: str = "http://localhost:11434/v1"
    oss_model_name: str = "qwen2.5:7b"
    # GUARDRAIL: financial/PII never leaves to an external model unless explicitly enabled.
    allow_external_model: bool = False

    # AP / invoicing tool (separate from TRACK).
    ap_mode: Literal["mock", "api", "ramp"] = "mock"
    ap_base_url: str = ""
    ap_api_key: str = ""

    # Ramp ingestion (real pull requires OAuth client-credentials + egress; guarded).
    ramp_base_url: str = "https://api.ramp.com"
    ramp_client_id: str = ""
    ramp_client_secret: str = ""

    # Email notifications. "offline" = queue to the outbox, never send (default, safe).
    # GUARDRAIL: a real provider only sends when allow_external_email is explicitly true.
    notify_provider: Literal["offline", "graph", "smtp"] = "offline"
    allow_external_email: bool = False
    notify_from: str = "invoice-auditor@awayday.example"
    # Microsoft Graph (M365) — client-credentials.
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    # SMTP (Google Workspace / M365 / any) — app password or relay creds.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # State (SQLite, offline).
    db_path: str = str(REPO_ROOT / "invoice_auditor.db")

    # Autonomy: precision a per-anomaly type must sustain before auto-act unlocks.
    autonomy_precision_bar: float = 0.95
    max_auto_reject_value: float = 1000.0


settings = Settings()
