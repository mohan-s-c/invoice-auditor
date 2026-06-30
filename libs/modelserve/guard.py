"""Egress guard (handoff §10.3) — all inference runs on the LOCAL self-hosted Qwen.

Any attempt to call a non-local model endpoint hard-fails unless ``allow_external_model`` is
explicitly enabled. Invoices carry vendor/financial data; nothing leaves the boundary by default.
"""
from __future__ import annotations

from urllib.parse import urlparse

from libs.common.config import settings

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class EgressViolation(RuntimeError):
    ...


def is_local(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in _LOCAL_HOSTS or host.endswith(".local") or host == ""


def assert_local(url: str) -> None:
    if not is_local(url) and not settings.allow_external_model:
        raise EgressViolation(
            f"Refusing to send invoice data to non-local model endpoint {url!r} "
            f"(set ALLOW_EXTERNAL_MODEL=true to override)."
        )
