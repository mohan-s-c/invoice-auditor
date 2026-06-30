"""Structured logging. ``silence()`` quiets audit noise in tests (rows still persist)."""
from __future__ import annotations

import logging

import structlog


def configure() -> None:
    structlog.configure(processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ])


def silence() -> None:
    logging.disable(logging.CRITICAL)
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL))
