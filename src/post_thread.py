"""Tweet posting helpers for singles and threads.

Adds exponential-backoff retry around every live API call and writes
unrecoverable failures to failed_queue.csv for manual review.
"""
from __future__ import annotations

import csv
import os
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, List

import tweepy
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_CLIENTS: Optional[Tuple[tweepy.Client, tweepy.API]] = None

# Retry config — override with MAX_RETRY_ATTEMPTS env var
_MAX_RETRIES = max(1, int(os.getenv("MAX_RETRY_ATTEMPTS", "3")))
_RETRY_DELAYS = [2, 4, 8]  # seconds between attempts

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FAILED_QUEUE_FILE = _REPO_ROOT / "failed_queue.csv"
_FAILED_QUEUE_FIELDS = ["timestamp_utc", "text", "error"]


# ---------------------------------------------------------------------------
# Client management
# ---------------------------------------------------------------------------

def _get_clients() -> Tuple[Optional[tweepy.Client], Optional[tweepy.API]]:
    """Create or return cached Tweepy clients."""
    global _CLIENTS
    if _CLIENTS is not None:
        return _CLIENTS
    if os.getenv("DRY_RUN") == "1":
        logger.info("DRY_RUN enabled; skipping Twitter client creation")
        _CLIENTS = (None, None)
        return _CLIENTS
    auth = tweepy.OAuth1UserHandler(
        os.environ["TW_CONSUMER_KEY"],
        os.environ["TW_CONSUMER_SECRET"],
        os.environ["TW_ACCESS_TOKEN"],
        os.environ["TW_ACCESS_SECRET"],
    )
    api = tweepy.API(auth)
    client = tweepy.Client(
        consumer_key=os.environ["TW_CONSUMER_KEY"],
        consumer_secret=os.environ["TW_CONSUMER_SECRET"],
        access_token=os.environ["TW_ACCESS_TOKEN"],
        access_token_secret=os.environ["TW_ACCESS_SECRET"],
    )
    _CLIENTS = (client, api)
    return _CLIENTS


# ---------------------------------------------------------------------------
# Failed-queue persistence
# ---------------------------------------------------------------------------

def _write_failed_queue(text: str, error: str) -> None:
    """Append a failed tweet to failed_queue.csv for manual review."""
    file_exists = _FAILED_QUEUE_FILE.exists()
    with open(_FAILED_QUEUE_FILE, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_FAILED_QUEUE_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "text": text,
                "error": error,
            }
        )
    logger.warning("Failed tweet written to %s", _FAILED_QUEUE_FILE)


# ---------------------------------------------------------------------------
# Core posting — no retry (used internally and in post_thread_from_file)
# ---------------------------------------------------------------------------

def post_single(
    text: str,
    media_path: str | None = None,
    alt_text: str | None = None,
    in_reply_to_tweet_id: str | None = None,
) -> Optional[str]:
    """Post a single tweet with optional media.  Returns tweet ID or None (dry run)."""
    client, api = _get_clients()

    if os.getenv("DRY_RUN") == "1":
        logger.info("[DRY RUN] Tweet (%d chars): %s", len(text), text)
        if media_path:
            logger.info("[DRY RUN] Media: %s (alt=%s)", media_path, alt_text)
        return "0"

    media_ids: Optional[List[str]] = None
    if media_path:
        media_path_obj = Path(media_path)
        if not media_path_obj.exists():
            raise FileNotFoundError(f"Media file not found: {media_path}")
        media = api.media_upload(filename=str(media_path_obj))
        if alt_text:
            api.create_media_metadata(media.media_id, alt_text)
        media_ids = [media.media_id]

    resp = client.create_tweet(
        text=text,
        media_ids=media_ids,
        in_reply_to_tweet_id=in_reply_to_tweet_id,
    )
    tweet_id = str(resp.data.get("id"))
    logger.info("Posted tweet %s (%d chars)", tweet_id, len(text))
    return tweet_id


# ---------------------------------------------------------------------------
# Retry wrapper — use this for all automated posts
# ---------------------------------------------------------------------------

def post_single_with_retry(
    text: str,
    media_path: str | None = None,
    alt_text: str | None = None,
    in_reply_to_tweet_id: str | None = None,
) -> Optional[str]:
    """Call post_single with exponential-backoff retry.

    Attempts up to MAX_RETRY_ATTEMPTS times with 2 / 4 / 8 second delays.
    On total failure, appends the tweet text to failed_queue.csv and returns None.
    In DRY_RUN mode the retry loop still executes (logs all attempts) but never
    sleeps or hits the real API.
    """
    delays = _RETRY_DELAYS[: _MAX_RETRIES - 1]  # one fewer delay than attempts
    last_error: Optional[Exception] = None

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            result = post_single(text, media_path, alt_text, in_reply_to_tweet_id)
            if attempt > 1:
                logger.info("Tweet succeeded on attempt %d", attempt)
            return result
        except Exception as exc:
            last_error = exc
            if attempt < _MAX_RETRIES:
                delay = delays[attempt - 1]
                logger.warning(
                    "Tweet attempt %d/%d failed (%s); retrying in %ds",
                    attempt,
                    _MAX_RETRIES,
                    exc,
                    delay,
                )
                time.sleep(delay)
            else:
                logger.error(
                    "All %d retry attempts failed: %s", _MAX_RETRIES, exc
                )

    _write_failed_queue(text, str(last_error))
    return None


# ---------------------------------------------------------------------------
# Thread helpers
# ---------------------------------------------------------------------------

def post_thread_from_file(thread_path: str) -> None:
    """Post top-level tweets from a file separated by '---' lines."""
    path = Path(thread_path)
    if not path.exists():
        raise FileNotFoundError(f"Thread file not found: {thread_path}")
    content = path.read_text(encoding="utf-8")
    parts = [p.strip() for p in content.split("\n---\n") if p.strip()]
    for part in parts:
        post_single(part)
        time.sleep(2)


def post_composed_single(
    headline: str,
    bullets: List[str],
    source: str,
    out_path: str,
) -> Optional[str]:
    """Craft a tweet via :mod:`composer`, render a card, and post it."""
    import composer  # type: ignore
    from . import make_card  # type: ignore

    summary = " ".join(bullets)
    text = composer.craft_tweet(headline, summary)
    make_card.make_card(headline, bullets, source, out_path)
    alt_text = f"{headline}. {' '.join(bullets[:3])} Source: {source}"
    return post_single_with_retry(text=text, media_path=out_path, alt_text=alt_text)
