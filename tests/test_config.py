import pytest
from pydantic import ValidationError

from libs.common.config import Settings


def test_defaults_are_valid():
    s = Settings()
    assert s.llm_provider == "offline" and s.ap_mode == "mock" and s.notify_provider == "offline"


def test_bad_mode_value_fails_fast(monkeypatch):
    # A typo'd env var must raise at construction time, not silently fall through to a default
    # mode and misbehave later (e.g. AP_MODE=rmap quietly serving mock data in production).
    monkeypatch.setenv("AP_MODE", "rmap")
    with pytest.raises(ValidationError):
        Settings()


def test_valid_non_default_mode_is_accepted(monkeypatch):
    monkeypatch.setenv("AP_MODE", "ramp")
    monkeypatch.setenv("NOTIFY_PROVIDER", "smtp")
    s = Settings()
    assert s.ap_mode == "ramp" and s.notify_provider == "smtp"
