"""Ramp ingestion adapter (next-phase §8) — pulls bills from Ramp and maps them to canonical
Invoices, behind the same ``APClient`` Protocol as the mock.

Real pull needs OAuth client-credentials (RAMP_CLIENT_ID/SECRET) and network egress. To keep
the app runnable offline and never hard-fail a demo, this adapter FALLS BACK to the seed master
data when credentials are absent or any call fails — logging why. Vendor/contract master data
(needed for benchmarks + contract checks, which Ramp does not provide) always comes from the
configured master; only invoices/bills are pulled from Ramp.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

import structlog

from libs.canonical.models import Contract, Invoice, InvoiceLine, Vendor
from libs.common.config import settings

from . import seed

log = structlog.get_logger("ramp")


class RampAPClient:
    name = "ramp"

    # --- master data (not in Ramp) comes from the configured seed/master ---
    def vendors(self) -> list[Vendor]:
        return seed.VENDORS

    def contracts(self) -> list[Contract]:
        return seed.CONTRACTS

    # --- invoices/bills are pulled from Ramp ---
    def invoices(self) -> list[Invoice]:
        if not (settings.ramp_client_id and settings.ramp_client_secret):
            log.warning("ramp.no_credentials", msg="RAMP_CLIENT_ID/SECRET unset — using seed")
            return seed.build_invoices()
        try:
            bills = self._fetch_bills()
            return [self._map_bill(b) for b in bills]
        except Exception as e:  # never break the app on an integration hiccup
            log.warning("ramp.fetch_failed", error=str(e), msg="falling back to seed")
            return seed.build_invoices()

    def _token(self) -> str:
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "scope": "bills:read transactions:read",
        }).encode()
        req = urllib.request.Request(f"{settings.ramp_base_url}/developer/v1/token", data=data)
        # Ramp uses HTTP Basic with client id/secret for the token call.
        import base64
        cred = base64.b64encode(
            f"{settings.ramp_client_id}:{settings.ramp_client_secret}".encode()).decode()
        req.add_header("Authorization", f"Basic {cred}")
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["access_token"]

    def _fetch_bills(self) -> list[dict]:
        token = self._token()
        req = urllib.request.Request(
            f"{settings.ramp_base_url}/developer/v1/bills?page_size=100",
            headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read()).get("data", [])

    @staticmethod
    def _map_bill(b: dict) -> Invoice:
        """Map a Ramp bill payload to the canonical Invoice. Field paths are best-effort and
        depend on the Ramp entity/department config (brand/region live in those custom fields)."""
        amt = (b.get("amount") or {}).get("amount", b.get("amount", 0.0))
        vendor = (b.get("vendor") or {}).get("name") or b.get("vendor_name") or "Unknown vendor"
        lines = []
        for li in b.get("line_items", []) or []:
            qty = li.get("quantity", 1) or 1
            unit = (li.get("unit_price") or {}).get("amount") or li.get("unit_price") or 0.0
            la = (li.get("amount") or {}).get("amount") or li.get("amount") or round(qty * unit, 2)
            lines.append(InvoiceLine(item=li.get("memo") or li.get("description") or "Line item",
                                     category=(li.get("category_info") or {}).get("name"),
                                     qty=qty, unit_price=unit, amount=la))
        return Invoice(
            id=b.get("invoice_number") or b.get("id") or "RAMP-UNKNOWN",
            brand=b.get("brand") or b.get("entity_name") or "Unassigned",
            region=b.get("region") or b.get("department_name") or "Unassigned",
            vendor_id=(b.get("vendor") or {}).get("id") or "ramp-vendor",
            vendor=vendor, category=b.get("category") or "Uncategorized",
            amount=float(amt or 0.0), status="pending", paid=bool(b.get("paid")),
            paid_ts=b.get("paid_at"), approver=b.get("approver_name"),
            filed_ts=b.get("issued_at") or b.get("created_at"), lines=lines)
