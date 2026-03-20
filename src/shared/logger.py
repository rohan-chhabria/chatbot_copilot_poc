"""
InmateCopilot V1 — Structured Logging
======================================

Single logger factory for consistent log formatting across all modules.
Uses JSON-structured output in Lambda, human-readable locally.
"""

from __future__ import annotations

import logging
import sys

from src.shared.config import IS_LAMBDA, LOG_LEVEL

_CONFIGURED = False


def get_logger(name: str) -> logging.Logger:
    global _CONFIGURED

    if not _CONFIGURED:
        _configure_root()
        _CONFIGURED = True

    return logging.getLogger(name)


def _configure_root() -> None:
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if IS_LAMBDA:
        fmt = logging.Formatter(
            '{"time":"%(asctime)s","level":"%(levelname)s",'
            '"module":"%(name)s","message":"%(message)s"}'
        )
    else:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )

    handler.setFormatter(fmt)
    root.addHandler(handler)
