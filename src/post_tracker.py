"""Deduplication tracker for posted article URLs.

Persists to posted_ids.json at the repo root and caps entries at MAX_ENTRIES
to prevent unbounded growth.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_TRACKER_FILE = Path(__file__).resolve().parent.parent / "posted_ids.json"
MAX_ENTRIES = 500


def _load() -> list[dict]:
    try:
        with open(_TRACKER_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        logger.warning("posted_ids.json is corrupt; resetting tracker")
        return []


def _save(entries: list[dict]) -> None:
    with open(_TRACKER_FILE, "w", encoding="utf-8") as fh:
        json.dump(entries[-MAX_ENTRIES:], fh, indent=2)


def was_posted(article_url: str) -> bool:
    """Return True if *article_url* appears in the deduplication cache."""
    if not article_url:
        return False
    return any(e.get("url") == article_url for e in _load())


def mark_posted(article_url: str) -> None:
    """Record *article_url* as posted, trimming the cache to MAX_ENTRIES."""
    if not article_url:
        return
    entries = _load()
    entries.append(
        {
            "url": article_url,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _save(entries)
    logger.debug("Marked as posted: %s", article_url)
