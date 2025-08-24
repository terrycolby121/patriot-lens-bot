"""Tweet posting helpers for singles and threads."""
from __future__ import annotations

import os
import time
import logging
from pathlib import Path
from typing import Optional, Tuple, List

import tweepy
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_CLIENTS: Optional[Tuple[tweepy.Client, tweepy.API]] = None


def _get_clients() -> Tuple[Optional[tweepy.Client], Optional[tweepy.API]]:
    """Create or return cached Tweepy clients."""
    global _CLIENTS
    if _CLIENTS is not None:
        return _CLIENTS
    if os.getenv("DRY_RUN") == "1":
        logger.info("DRY_RUN enabled; not creating Twitter clients")
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


def post_single(
    text: str,
    media_path: str | None = None,
    alt_text: str | None = None,
    in_reply_to_tweet_id: str | None = None,
) -> Optional[str]:
    """Post a single tweet with optional media.

    Returns the tweet ID if posted, else None (in dry-run)."""
    client, api = _get_clients()
    if os.getenv("DRY_RUN") == "1":
        logger.info("[DRY RUN] Tweet: %s", text)
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
    logger.info("Posted tweet %s", tweet_id)
    return tweet_id


def post_thread_from_file(thread_path: str) -> None:
    """Post a thread from a text file separated by '---' lines."""
    path = Path(thread_path)
    if not path.exists():
        raise FileNotFoundError(f"Thread file not found: {thread_path}")
    content = path.read_text(encoding="utf-8")
    parts = [p.strip() for p in content.split("\n---\n") if p.strip()]
    reply_to: Optional[str] = None
    for part in parts:
        reply_to = post_single(part, in_reply_to_tweet_id=reply_to)
        time.sleep(2)
