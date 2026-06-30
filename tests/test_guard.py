import pytest

from libs.modelserve.guard import EgressViolation, assert_local, is_local


def test_local_endpoints_allowed():
    assert is_local("http://localhost:11434/v1")
    assert is_local("http://127.0.0.1:8000/v1")
    assert_local("http://localhost:11434/v1")  # no raise


def test_external_model_blocked_by_default():
    with pytest.raises(EgressViolation):
        assert_local("https://api.openai.com/v1")


def test_override_allows_external(monkeypatch):
    from libs.common.config import settings
    monkeypatch.setattr(settings, "allow_external_model", True)
    assert_local("https://api.openai.com/v1")  # no raise when explicitly enabled
