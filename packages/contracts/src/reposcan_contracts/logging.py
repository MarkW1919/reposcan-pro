"""Structured logging configuration for RepoScan Pro services.

Call ``configure_logging(level, service_name)`` once at process startup — before
any other import that touches the logging machinery — to switch every logger
over to JSON-formatted output.

JSON format per line::

    {"ts": "2026-03-30T12:00:00.000Z", "level": "INFO", "svc": "api",
     "logger": "reposcan_api.app", "msg": "startup complete"}

All key names are short so log-shipping agents and jq filters stay compact.
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from datetime import datetime, timezone
from typing import Any


_LEVEL_MAP: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


class _JsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def __init__(self, service_name: str) -> None:
        super().__init__()
        self._svc = service_name

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"

        entry: dict[str, Any] = {
            "ts": ts,
            "level": record.levelname,
            "svc": self._svc,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        elif record.exc_text:
            entry["exc"] = record.exc_text

        # Merge any extra fields passed via ``extra=`` or ``LogRecord`` attrs
        for key, value in record.__dict__.items():
            if key.startswith("_rs_"):
                entry[key[4:]] = value

        return json.dumps(entry, default=str)


class _PlainFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    FMT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
    DATEFMT = "%H:%M:%S"

    def __init__(self) -> None:
        super().__init__(fmt=self.FMT, datefmt=self.DATEFMT)


def configure_logging(
    level: str = "info",
    service_name: str = "reposcan",
    json_output: bool | None = None,
) -> None:
    """Configure the root logger for the calling service.

    Args:
        level: Minimum log level string — ``"debug"``, ``"info"``,
            ``"warning"``, or ``"error"``.  Case-insensitive.
        service_name: Short identifier embedded in every JSON log line.
        json_output: Force JSON output (``True``) or plain text (``False``).
            When ``None`` (default), JSON is used when stdout is *not* a TTY
            so that terminals stay readable while log shippers get JSON.
    """
    numeric_level = _LEVEL_MAP.get(level.lower(), logging.INFO)

    if json_output is None:
        json_output = not sys.stdout.isatty()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    if json_output:
        handler.setFormatter(_JsonFormatter(service_name))
    else:
        handler.setFormatter(_PlainFormatter())

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Replace any existing handlers so there are no duplicates on re-call
    root.handlers.clear()
    root.addHandler(handler)

    # Quieten noisy third-party loggers that flood debug output
    for noisy in ("uvicorn.access", "httpx", "httpcore", "watchfiles"):
        logging.getLogger(noisy).setLevel(
            max(numeric_level, logging.WARNING)
        )


def get_logger(name: str) -> logging.Logger:
    """Return a standard logger with the given name.

    Wraps ``logging.getLogger`` so callers don't need to import ``logging``
    directly when they only need a named logger.
    """
    return logging.getLogger(name)
