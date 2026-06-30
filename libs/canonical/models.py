"""Canonical data model (handoff §11). Money as float for the offline build (a real build
would use Decimal end-to-end for zero-variance reconciliation)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class InvoiceLine(BaseModel):
    item: str
    category: str | None = None
    qty: float
    unit_price: float
    amount: float
    flag: str | None = None  # set by detection ("+50% vs benchmark", "duplicate?", ...)


class Invoice(BaseModel):
    id: str
    brand: str
    region: str
    vendor_id: str
    vendor: str
    category: str
    amount: float
    tax: float = 0.0
    status: str = "pending"
    approver: str | None = None
    filed_ts: str | None = None
    lines: list[InvoiceLine] = Field(default_factory=list)


class Vendor(BaseModel):
    id: str
    name: str
    category: str
    contract: str = "off"  # 'off' | 'regional' | 'hq'
    region: str | None = None
    spend_ytd: float = 0.0
    vs_benchmark: float = 0.0  # avg unit cost vs HQ benchmark (e.g. +0.50 = +50%)


class Contract(BaseModel):
    category: str
    region: str | None = None
    scope: str = "hq"  # 'hq' | 'regional'
    hq_rate: float | None = None
