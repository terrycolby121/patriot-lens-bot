"""Queue runner for scheduled tweets."""
from __future__ import annotations

import csv
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
import tweepy

from . import post_thread, quote_tweet

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

ROOT = Path(__file__).resolve().parent.parent
QUEUE_FILE = ROOT / "queue.csv"

REQUIRED_ENV = [
    "TW_CONSUMER_KEY",
    "TW_CONSUMER_SECRET",
    "TW_ACCESS_TOKEN",
    "TW_ACCESS_SECRET",
]


def _check_env() -> None:
    missing: List[str] = []
    for key in REQUIRED_ENV:
        val = os.getenv(key)
        if val:
            masked = val[:4] + "..." + val[-4:] if len(val) > 8 else "***"
            logger.info("%s=%s", key, masked)
        else:
            missing.append(key)
    if missing:
        logger.error("Missing env vars: %s", ", ".join(missing))
        raise SystemExit(1)


def _parse_single(content: str) -> Dict[str, str | None]:
    text = content
    media_path = None
    alt_text = None
    if "->" in content:
        text_part, media_part = content.split("->", 1)
        text = text_part.strip()
        media_part = media_part.strip()
        if "|ALT:" in media_part:
            media_path, alt_text = media_part.split("|ALT:", 1)
            media_path = media_path.strip()
            alt_text = alt_text.strip()
        else:
            media_path = media_part.strip()
    return {"text": text.strip(), "media": media_path, "alt": alt_text}


def run_queue() -> None:
    _check_env()
    if not QUEUE_FILE.exists():
        logger.info("No queue file found at %s", QUEUE_FILE)
        return

    now = datetime.now(timezone.utc)
    remaining: List[Dict[str, str]] = []

    with QUEUE_FILE.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            dt = datetime.fromisoformat(row["datetime_utc"].replace("Z", "+00:00"))
            if dt <= now:
                logger.info("Posting %s", row["type"])
                try:
                    if row["type"] == "single":
                        data = _parse_single(row["content"])
                        post_thread.post_single(data["text"], data["media"], data["alt"])
                    elif row["type"] == "thread":
                        path = ROOT / row["content"].strip()
                        post_thread.post_thread_from_file(str(path))
                    elif row["type"] == "quote":
                        url, text = row["content"].split("|", 1)
                        quote_tweet.post_quote(url.strip(), text.strip())
                    else:
                        logger.error("Unknown type %s", row["type"])
                        remaining.append(row)
                        continue
                except FileNotFoundError as e:
                    logger.error("Missing file: %s", e)
                    remaining.append(row)
                except tweepy.errors.TweepyException as e:
                    status = getattr(getattr(e, "response", None), "status_code", None)
                    if status in {401, 403, 429} or (status and 500 <= status < 600):
                        logger.error("Twitter API error %s: %s", status, e)
                    else:
                        logger.exception("Unexpected Twitter error: %s", e)
                    remaining.append(row)
                except Exception as e:
                    logger.exception("Failed to post: %s", e)
                    remaining.append(row)
            else:
                remaining.append(row)

    with QUEUE_FILE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["datetime_utc", "type", "content"])
        writer.writeheader()
        writer.writerows(remaining)


if __name__ == "__main__":
    run_queue()
