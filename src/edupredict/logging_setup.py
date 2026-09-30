"""Logging configuration for EduPredict.

Provides a single idempotent :func:`setup_logging` entry point that every
process (web server or CLI) calls during bootstrap.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

from .config import Settings

__all__ = ["setup_logging", "get_logger"]

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_VALID_TARGETS = {"console", "file", "both", "none"}
_CONFIGURED = False


def setup_logging(settings: Settings) -> logging.Logger:
    """Configure the root logger from :class:`Settings`. Safe to call twice."""
    global _CONFIGURED
    cfg = settings.logging

    root = logging.getLogger()
    if _CONFIGURED:
        return root

    level = getattr(logging, cfg.level.upper(), None)
    if not isinstance(level, int):
        raise ValueError(
            f"Invalid log level {cfg.level!r}; use DEBUG, INFO, WARNING, ERROR or CRITICAL"
        )

    root.setLevel(level)
    for handler in list(root.handlers):
        root.removeHandler(handler)

    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    target = cfg.target.lower()
    if target not in _VALID_TARGETS:
        raise ValueError(
            f"Invalid logging target {cfg.target!r}; "
            f"use one of: {', '.join(sorted(_VALID_TARGETS))}"
        )

    if target in {"console", "both"}:
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(formatter)
        root.addHandler(stream)

    if target in {"file", "both"}:
        log_path: Path = settings.resolve(cfg.file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        rotating = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=cfg.max_bytes,
            backupCount=cfg.backup_count,
            encoding="utf-8",
        )
        rotating.setFormatter(formatter)
        root.addHandler(rotating)

    # Werkzeug's request log is very noisy at INFO during development.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    _CONFIGURED = True
    return root


def get_logger(name: str) -> logging.Logger:
    """Return a module logger, creating parent directories lazily."""
    return logging.getLogger(name)
