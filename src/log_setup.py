"""Structured JSON logging with rotating file output.

Call ``setup_logging()`` once at process startup (bot_auto.py, scheduler.py,
on_demand.py).  All loggers in the process then emit:
  - JSON lines to  logs/bot.log  (1 MB max, 3 rotating backups)
  - Human-readable lines to stderr
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import os
from pathlib import Path


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single JSON object."""

    # Structured fields that callers may attach via extra={}
    _EXTRA_FIELDS = ("article_title", "tweet_chars", "format_type", "dry_run")

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self._EXTRA_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def setup_logging() -> None:
    """Configure root logger: JSON rotating file + human-readable stderr."""
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    logs_dir = Path(__file__).resolve().parent.parent / "logs"
    logs_dir.mkdir(exist_ok=True)
    log_file = logs_dir / "bot.log"

    root = logging.getLogger()
    # Avoid adding duplicate handlers if called more than once
    if root.handlers:
        return
    root.setLevel(log_level)

    # --- rotating JSON file ---
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=1 * 1024 * 1024,  # 1 MB
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(_JsonFormatter())
    file_handler.setLevel(log_level)

    # --- stderr (human readable) ---
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    stream_handler.setLevel(log_level)

    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    # Silence noisy third-party loggers regardless of LOG_LEVEL
    for _noisy in ("httpcore", "httpx", "openai._base_client", "urllib3"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)
