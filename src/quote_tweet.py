"""Quote tweet helper."""
from __future__ import annotations

import os
import re
import logging
from typing import Optional

from dotenv import load_dotenv

from . import post_thread

load_dotenv()
logger = logging.getLogger(__name__)


def _extract_id(url: str) -> str:
    match = re.search(r"status/(\d+)", url)
    if not match:
        raise ValueError(f"Could not extract tweet ID from {url}")
    return match.group(1)


def post_quote(url: str, text: str) -> Optional[str]:
    """Post a quote tweet of the given URL with accompanying text."""
    tweet_id = _extract_id(url)
    client, _ = post_thread._get_clients()
    if os.getenv("DRY_RUN") == "1":
        logger.info("[DRY RUN] Quote tweet %s with text: %s", url, text)
        return "0"
    resp = client.create_tweet(text=text, quote_tweet_id=tweet_id)
    q_id = str(resp.data.get("id"))
    logger.info("Posted quote tweet %s", q_id)
    return q_id
