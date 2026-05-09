"""
utils/logger.py
===============
Centralised logging configuration for the Jarvis platform.

Call ``setup_logger()`` once at application startup (inside ``main()``).
Every subsequent ``logging.getLogger(__name__)`` call across the codebase
will automatically inherit this configuration.

UI-clean design
---------------
The console handler is set to CRITICAL only — effectively silent during
normal operation.  All INFO/DEBUG/WARNING records go to the log file only,
so the terminal UI is never polluted by log noise.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# ── Formatting constants ──────────────────────────────────────────────────────

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-35s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── Third-party loggers that are too noisy ────────────────────────────────────

_QUIET_LOGGERS: tuple[str, ...] = (
    "httpx",
    "httpcore",
    "edge_tts",
    "asyncio",
    "urllib3",
    "groq",
)


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════


def setup_logger(
    level: int = logging.INFO,
    log_file: Path | None = None,
) -> None:
    """
    Configure the root logger.

    Console behaviour
    -----------------
    The console handler is pinned to ``CRITICAL`` regardless of *level*.
    This keeps the terminal completely clean for the UI layer.
    Only truly fatal errors (that would crash the process) are ever
    printed to stdout.

    File behaviour
    --------------
    When *log_file* is provided every record at *level* and above is
    written to that file with full timestamps and module paths — useful
    for debugging without cluttering the UI.

    Args:
        level:    Verbosity written to the log *file* (default: INFO).
        log_file: Destination path for the persistent log file.
                  Parent directories are created automatically.
                  Pass ``None`` to disable file logging entirely.
    """
    handlers: list[logging.Handler] = [
        _build_console_handler(),  # always present — silent except CRITICAL
    ]

    if log_file is not None:
        handlers.append(_build_file_handler(log_file, level))

    logging.basicConfig(
        level=logging.DEBUG,  # capture everything at the root
        format=_LOG_FORMAT,
        datefmt=_DATE_FORMAT,
        handlers=handlers,
        force=True,  # replace any previous basicConfig setup
    )

    # Suppress noisy third-party libraries even in the file
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


# ═══════════════════════════════════════════════════════════════════════════════
# Private helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _formatter() -> logging.Formatter:
    return logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)


def _build_console_handler() -> logging.StreamHandler:
    """
    Build a console handler that is silent unless something truly fatal happens.

    By setting the level to CRITICAL, normal INFO / WARNING / ERROR records
    never reach stdout.  The UI layer owns all terminal output.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.CRITICAL)  # ← silent under normal operation
    handler.setFormatter(_formatter())
    return handler


def _build_file_handler(path: Path, level: int) -> logging.FileHandler:
    """Build a file handler that captures all records at *level* and above."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(level)
    handler.setFormatter(_formatter())
    return handler
