"""Central settings (handoff §4). Offline-first defaults; see DECISIONS.md."""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Local LLM (self-hosted Qwen). "offline" = deterministic, no GPU.
    llm_provider: str = "offline"  # offline | oss
    oss_model_base_url: str = "http://localhost:11434/v1"
    oss_model_name: str = "qwen2.5:7b"
    # GUARDRAIL: financial/PII never leaves to an external model unless explicitly enabled.
    allow_external_model: bool = False

    # AP / invoicing tool (separate from TRACK).
    ap_mode: str = "mock"  # mock | api
    ap_base_url: str = ""
    ap_api_key: str = ""

    # State (SQLite, offline).
    db_path: str = str(REPO_ROOT / "invoice_auditor.db")

    # Autonomy: precision a per-anomaly type must sustain before auto-act unlocks.
    autonomy_precision_bar: float = 0.95
    max_auto_reject_value: float = 1000.0


settings = Settings()
