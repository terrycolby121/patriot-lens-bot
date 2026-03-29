"""Automated headline-tweet pipeline.

Called by scheduler.py for every time-slot post.  Each call:
  1. Fetches the latest political headlines from NewsAPI.
  2. Scores and deduplicates them.
  3. Picks the best article from a top-3 pool.
  4. Crafts copy in the requested format.
  5. Posts via the retry-wrapped Twitter client.
  6. Records the posted URL to prevent repeat posting.

Zero Twitter read endpoints are used.  Only POST /2/tweets.
"""
from __future__ import annotations

import logging
import os
import random
import re
from datetime import datetime, timezone

from dotenv import load_dotenv

from src.log_setup import setup_logging

setup_logging()
load_dotenv()

from composer import TweetConfig, craft_tweet, craft_thread_pair   # noqa: E402
from news_fetcher import fetch_top_articles                        # noqa: E402
from src.post_thread import post_single_with_retry                 # noqa: E402
from src.post_tracker import was_posted, mark_posted               # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scoring signals
# ---------------------------------------------------------------------------

_URGENCY_WORDS = frozenset(
    {"breaking", "just in", "confirmed", "alert", "massive", "unprecedented"}
)
_HEDGE_WORDS = frozenset({"may", "could", "might", "report says"})

_BEST_POOL_SIZE = 3   # tighter selection = higher average quality

# Tier 1: unambiguously US-political — pass immediately
_STRONG_US_POLITICAL = frozenset({
    "trump", "biden", "harris", "pelosi", "schumer", "mcconnell",
    "congress", "senate", "white house", "supreme court", "pentagon",
    "republican", "democrat", "gop", "maga", "america first",
    "executive order", "veto", "filibuster", "impeach", "electoral",
    "second amendment", "tariff", "doge", "fbi", "doj", "cia", "nsa",
    "border patrol", "ice agent", "daca", "obamacare",
})

# Tier 2: generic political terms — only pass when paired with a US location signal
_GENERAL_POLITICAL = frozenset({
    "protest", "rally", "election", "vote", "legislation", "government",
    "policy", "border", "immigration", "military", "spending", "budget",
    "tax", "inflation", "economy", "debt", "deficit", "gun control",
    "trade", "china", "iran", "ukraine", "israel", "nato",
    "poll", "approval", "resign", "indictment", "federal",
})

# US location signals used to validate tier-2 matches
_US_LOCATION_RE = re.compile(
    r"\bamerican[s]?\b|\bunited states\b|\bu\.s\.\b"
    r"|\bthe us\b|\bacross the us\b|\bin the us\b"
    r"|\bwashington\b|\bwhite house\b",
    re.IGNORECASE,
)


def _is_political(article: dict) -> bool:
    """Return True only for US-relevant political articles."""
    text = ((article.get("title") or "") + " " + (article.get("summary") or "")).lower()
    # Tier 1: strong US-specific keyword → immediate pass
    if any(kw in text for kw in _STRONG_US_POLITICAL):
        return True
    # Tier 2: generic political word + explicit US location reference → pass
    if any(kw in text for kw in _GENERAL_POLITICAL):
        return bool(_US_LOCATION_RE.search(text))
    return False


def _score_article(article: dict) -> float:
    """Score an article for engagement potential."""
    title = (article.get("title") or "").lower()
    summary = article.get("summary") or ""
    score = 0.0

    # Base signals
    score += len(summary) * 0.02
    if len(title) > 70:
        score += 0.4
    if any(ch.isdigit() for ch in title):
        score += 0.5

    # Urgency boost
    for word in _URGENCY_WORDS:
        if word in title:
            score += 1.5
            break

    # Recency boost: published within the last 2 hours
    published_at = article.get("published_at")
    if published_at:
        try:
            pub_time = datetime.fromisoformat(
                published_at.replace("Z", "+00:00")
            )
            if pub_time.tzinfo is None:
                pub_time = pub_time.replace(tzinfo=timezone.utc)
            age_hours = (
                datetime.now(timezone.utc) - pub_time
            ).total_seconds() / 3600
            if age_hours <= 2:
                score += 1.0
        except Exception:
            pass

    # Hedging language penalty
    for word in _HEDGE_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", title):
            score -= 0.5

    return score


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def post_scheduled_tweet(tweet_format: str = "single") -> None:
    """Fetch, score, compose, and post one tweet in the given format.

    Args:
        tweet_format: "single" | "question_cta" | "numbered_thread"
    """
    dry_run = os.getenv("DRY_RUN") == "1"
    logger.info(
        "Starting scheduled post",
        extra={"format_type": tweet_format, "dry_run": dry_run},
    )

    arts = fetch_top_articles(limit=10)
    if not arts:
        logger.warning("No articles fetched; skipping this slot")
        return

    # Score and filter
    ranked: list[tuple[float, dict]] = []
    for article in arts:
        title = article.get("title") or ""
        if not title:
            continue
        if not _is_political(article):
            logger.info("Skipping off-topic: %s", title)
            continue
        url = article.get("url") or ""
        if url and was_posted(url):
            logger.info("Skipping duplicate: %s", title)
            continue
        ranked.append((_score_article(article), article))

    if not ranked:
        logger.warning("No new articles after deduplication; skipping")
        return

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_pool = [a for _, a in ranked[:_BEST_POOL_SIZE]]
    chosen = random.choice(best_pool)

    title = chosen["title"]
    url = chosen.get("url") or ""
    summary = chosen.get("summary") or ""

    logger.info("Selected article: %s", title)

    try:
        if tweet_format == "numbered_thread":
            hook, context = craft_thread_pair(headline=title, summary=summary)
            tweet_id = post_single_with_retry(text=hook)
            if tweet_id and tweet_id != "0":
                post_single_with_retry(
                    text=context,
                    in_reply_to_tweet_id=tweet_id,
                )
            logger.info(
                "Posted thread",
                extra={
                    "article_title": title,
                    "tweet_chars": len(hook),
                    "format_type": "numbered_thread",
                    "dry_run": dry_run,
                },
            )
        else:
            text = craft_tweet(
                headline=title,
                summary=summary,
                tweet_format=tweet_format,
            )
            post_single_with_retry(text=text)
            logger.info(
                "Posted tweet",
                extra={
                    "article_title": title,
                    "tweet_chars": len(text),
                    "format_type": tweet_format,
                    "dry_run": dry_run,
                },
            )
    except Exception:
        logger.exception("post_scheduled_tweet failed for article: %s", title)
        return

    # Mark as posted only after a successful (or dry-run) attempt
    if url:
        mark_posted(url)


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    post_scheduled_tweet()
