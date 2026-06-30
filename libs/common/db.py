"""Central persistence (DECISIONS D2) — SQLite via stdlib, the only place that opens the DB.

Tables: invoices + invoice_lines (canonical), vendors, contracts, flags (detection output),
dispositions (human decisions = training labels, handoff §11), and an append-only audit log
(every action with actor/target/before/after + model_version).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from typing import Any, Iterable

from libs.common.config import settings

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS vendors (
    id TEXT PRIMARY KEY, name TEXT, category TEXT,
    contract TEXT,          -- 'off' | 'regional' | 'hq'
    region TEXT, spend_ytd REAL, vs_benchmark REAL
);
CREATE TABLE IF NOT EXISTS contracts (         -- HQ/regional rate cards
    id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, region TEXT,
    scope TEXT, hq_rate REAL
);
CREATE TABLE IF NOT EXISTS invoices (
    id TEXT PRIMARY KEY, brand TEXT, region TEXT, vendor_id TEXT, vendor TEXT,
    category TEXT, amount REAL, tax REAL, status TEXT, approver TEXT,
    filed_ts TEXT, model_version TEXT
);
CREATE TABLE IF NOT EXISTS invoice_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_id TEXT, item TEXT, category TEXT,
    qty REAL, unit_price REAL, amount REAL, flag TEXT
);
CREATE TABLE IF NOT EXISTS flags (
    id TEXT PRIMARY KEY, invoice_id TEXT, brand TEXT, region TEXT, vendor TEXT,
    category TEXT, amount REAL, anomaly_type TEXT, severity TEXT, confidence REAL,
    recommended_action TEXT, recoverable REAL, rationale TEXT, model_version TEXT,
    status TEXT, created_ts TEXT
);
CREATE TABLE IF NOT EXISTS dispositions (      -- human decisions == training labels
    id INTEGER PRIMARY KEY AUTOINCREMENT, flag_id TEXT, invoice_id TEXT,
    actor TEXT, action TEXT, before TEXT, after TEXT, model_version TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, actor_id TEXT,
    action TEXT, target TEXT, before TEXT, after TEXT, model_version TEXT
);
"""

_TABLES = ("vendors", "contracts", "invoices", "invoice_lines", "flags",
           "dispositions", "audit")


def connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(settings.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        _local.conn = conn
        conn.executescript(SCHEMA)
        conn.commit()
    return conn


def init_db() -> None:
    connect()


def execute(sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
    conn = connect()
    cur = conn.execute(sql, tuple(params))
    conn.commit()
    return cur


def executemany(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    conn = connect()
    conn.executemany(sql, [tuple(r) for r in rows])
    conn.commit()


def query(sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
    return connect().execute(sql, tuple(params)).fetchall()


def query_one(sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
    return connect().execute(sql, tuple(params)).fetchone()


def dumps(value: Any) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def loads(value: str | None) -> Any:
    return json.loads(value) if value else None


def reset() -> None:
    conn = connect()
    for t in _TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
    conn.commit()
    conn.executescript(SCHEMA)
    conn.commit()
