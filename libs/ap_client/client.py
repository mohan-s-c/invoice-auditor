"""AP / invoicing-tool integration (handoff §6, §8) — the ONLY place that talks to the AP tool.

Interface + a mock that serves the offline seed (header + line items). A real adapter against
the confirmed AP tool slots in behind the same ``APClient`` Protocol; until then, ``AP_MODE=mock``.
"""
from __future__ import annotations

from typing import Protocol

from libs.canonical.models import Contract, Invoice, Vendor
from libs.common.config import settings

from . import seed


class APClient(Protocol):
    def invoices(self) -> list[Invoice]: ...
    def vendors(self) -> list[Vendor]: ...
    def contracts(self) -> list[Contract]: ...


class MockAPClient:
    """Serves the offline seed. No external calls."""

    def invoices(self) -> list[Invoice]:
        return seed.build_invoices()

    def vendors(self) -> list[Vendor]:
        return seed.VENDORS

    def contracts(self) -> list[Contract]:
        return seed.CONTRACTS


class ApiAPClient:
    """Real adapter — implement once the AP tool's invoice API/webhook is confirmed (§8)."""

    def invoices(self) -> list[Invoice]:
        raise NotImplementedError("Blocked on AP-tool integration (handoff §8).")

    def vendors(self) -> list[Vendor]:
        raise NotImplementedError

    def contracts(self) -> list[Contract]:
        raise NotImplementedError


def get_client() -> APClient:
    if settings.ap_mode == "ramp":
        from .ramp import RampAPClient
        return RampAPClient()
    if settings.ap_mode == "api":
        return ApiAPClient()
    return MockAPClient()
